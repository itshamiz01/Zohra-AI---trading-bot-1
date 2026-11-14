import {DatabaseSync} from 'node:sqlite';
import {randomUUID} from 'node:crypto';
import {mkdirSync, existsSync, lstatSync, realpathSync, writeFileSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const TOOL_IDS = JSON.parse(readFileSync(new URL('./tool-ids.json', import.meta.url), 'utf8'));
const CONTROLLED_TOOLS = new Set([...Object.values(TOOL_IDS.actions), ...TOOL_IDS.read_tools]);

export function cleanError(error) {
  const redact = value => String(value).replace(/(?:sk-|gsk_|AIza)[A-Za-z0-9_-]{20,}/g, '[secret redacted]')
    .replace(/\b(?:password|api[_-]?key|secret|authorization)\s*[:=]\s*\S+/gi, '[secret redacted]');
  return {code: redact(error.code || error.name || 'ERROR'), message: redact(error.message), stack: redact(error.stack || '')};
}

function browserUrl(value) {
  if (typeof value !== 'string' || value.length > 2000 || /[\s\\\x00-\x1f]/.test(value)) throw new TypeError('A public HTTP(S) URL is required');
  const url = new URL(value);
  const host = url.hostname.toLowerCase();
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      (url.port && !['80','443'].includes(url.port)) || !host.includes('.') || /:|^[\d.]+$|\.(?:localhost|local|internal|test)$/.test(host) ||
      [...url.searchParams.keys()].some(key => /password|secret|token|api[_-]?key|authorization/i.test(key))) throw Object.assign(new Error('Local addresses, credentials, and secret-bearing browser URLs are not permitted'), {code:'UNSAFE_URL'});
  return url.href;
}

export class ConfirmationGate {
  constructor(root, {now = Date.now, launch = null, writer = null, openBrowser = null, nativeControl = null, documents = null} = {}) {
    this.root = path.resolve(root);
    mkdirSync(this.root, {recursive: true});
    if (lstatSync(this.root).isSymbolicLink()) throw new Error('Assistant workspace cannot be a link');
    this.root = realpathSync(this.root);
    this.now = now;
    this.writer = writer;
    this.documents = documents || (request => {
      const cwd = path.dirname(fileURLToPath(new URL('../zohra.py', import.meta.url)));
      let output;
      try {
        output = execFileSync(process.env.ZOHRA_PYTHON_BINARY || 'python',
          ['-m','zohra.services.productivity.documents_cli'],
          {cwd, input:JSON.stringify(request), encoding:'utf8', timeout:30000, windowsHide:true,
            env:{...process.env,ZOHRA_ASSISTANT_WORKSPACE:this.root}});
      } catch (error) {
        if (!error.stdout) throw error;
        output = String(error.stdout);
      }
      const response = JSON.parse(output);
      if (!response.ok) throw Object.assign(new Error(response.error?.message || 'Document adapter failed'), {code:response.error?.code || 'DOCUMENT_ERROR'});
      return response.result;
    });
    this.nativeControl = nativeControl || (request => {
      const cwd = path.dirname(fileURLToPath(new URL('../zohra.py', import.meta.url)));
      let output;
      try {
        output = execFileSync(process.env.ZOHRA_PYTHON_BINARY || 'python',
          ['-m','zohra.services.automation.windows_controls_cli'],
          {cwd, input:JSON.stringify(request), encoding:'utf8', timeout:15000, windowsHide:true,
            env:{...process.env,ZOHRA_ASSISTANT_WORKSPACE:this.root}});
      } catch (error) {
        if (!error.stdout) throw error;
        output = String(error.stdout);
      }
      const response = JSON.parse(output);
      if (!response.ok) throw Object.assign(new Error(response.error?.message || 'Native adapter failed'), {code:response.error?.code || 'NATIVE_ERROR'});
      return response.result;
    });
    this.openBrowser = openBrowser || (url => {
      if (process.platform !== 'win32') throw Object.assign(new Error('Default-browser launching requires Windows'), {code:'UNSUPPORTED_OS'});
      execFileSync('powershell.exe', ['-NoProfile','-NonInteractive','-Command',
        '$ErrorActionPreference = "Stop"; Start-Process -FilePath $env:ZOHRA_ASSISTANT_URL'],
        {env:{...process.env,ZOHRA_ASSISTANT_URL:url}, timeout:10000, windowsHide:true});
      return {url,status:'dispatched_to_default_browser'};
    });
    this.launch = launch || (app => {
      if (process.platform !== 'win32') throw Object.assign(new Error('App launching requires Windows'), {code: 'UNSUPPORTED_OS'});
      const exe = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', app === 'notepad' ? 'notepad.exe' : 'calc.exe');
      const pid = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
        '$ErrorActionPreference = "Stop"; $p = Start-Process -FilePath $env:ZOHRA_ASSISTANT_APP -WindowStyle Normal -PassThru; $p.Id'],
        {env: {...process.env, ZOHRA_ASSISTANT_APP: exe}, timeout: 10000, windowsHide: true, encoding: 'utf8'}).trim();
      if (!/^[1-9]\d*$/.test(pid)) throw Object.assign(new Error('Windows did not return a launched process ID'), {code:'PROCESS_LAUNCH_FAILED'});
      return {app, status: 'launched', process_id: pid};
    });
    const database = path.join(this.root, 'assistant-runtime.db');
    if (existsSync(database) && lstatSync(database).isSymbolicLink()) throw new Error('Assistant database cannot be a link');
    this.db = new DatabaseSync(database);
    this.db.exec(`PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS confirmations(id TEXT PRIMARY KEY, session TEXT NOT NULL, lane TEXT NOT NULL,
        action TEXT NOT NULL, args TEXT NOT NULL, description TEXT NOT NULL, consequence TEXT NOT NULL,
        status TEXT NOT NULL, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
      CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, session TEXT, lane TEXT, action TEXT,
        status TEXT, error TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
      CREATE TABLE IF NOT EXISTS tool_controls(tool_id TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), updated TEXT NOT NULL);`);
  }
  close() { this.db.close(); }
  assertEnabled(toolId) {
    if (!toolId || this.db.prepare('SELECT enabled FROM tool_controls WHERE tool_id=?').get(toolId)?.enabled === 0) {
      throw Object.assign(new Error(`Owner revoked or did not register capability ${toolId || 'unknown'}`), {code:'TOOL_DISABLED'});
    }
  }
  audit(session, lane, action, status, error = null) {
    this.db.prepare('INSERT INTO audit(session,lane,action,status,error) VALUES(?,?,?,?,?)').run(session, lane, action, status, error ? JSON.stringify(cleanError(error)) : null);
  }
  filePath(relative) {
    if (typeof relative !== 'string' || relative.length > 200 || !/^[a-zA-Z0-9 _./-]+\.(?:txt|md)$/i.test(relative) || path.isAbsolute(relative) || relative.split(/[\\/]/).some(part => !part || /[. ]$/.test(part) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part))) {
      throw Object.assign(new Error('Only relative .txt/.md paths inside assistant_workspace/files are allowed'), {code: 'UNSAFE_PATH'});
    }
    const base = path.join(this.root, 'files');
    const target = path.resolve(base, relative);
    if (!target.startsWith(base + path.sep)) throw Object.assign(new Error('Path escapes the assistant workspace'), {code: 'UNSAFE_PATH'});
    let cursor = this.root;
    for (const part of path.relative(this.root, target).split(path.sep)) {
      cursor = path.join(cursor, part);
      if (existsSync(cursor) && lstatSync(cursor).isSymbolicLink()) throw Object.assign(new Error('Links and junctions are not writable'), {code: 'UNSAFE_PATH'});
    }
    return target;
  }
  validate(action, args) {
    if (!args || typeof args !== 'object' || Array.isArray(args)) throw new TypeError('Action arguments must be an object');
    if (action === 'export_document') {
      if (Object.keys(args).some(key => !['format','filename','title','content'].includes(key)) ||
          !['pdf','docx','xlsx'].includes(args.format) || typeof args.filename !== 'string' || args.filename.length > 120 ||
          !/^[A-Za-z0-9][A-Za-z0-9 _.-]*\.(?:pdf|docx|xlsx)$/.test(args.filename) ||
          !args.filename.toLowerCase().endsWith('.' + args.format) || /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(args.filename) ||
          typeof args.content !== 'string' || !args.content.trim() || Buffer.byteLength(args.content) > 100000 ||
          (args.title !== undefined && (typeof args.title !== 'string' || args.title.length > 180))) throw new TypeError('Validated document format, plain filename and non-empty content under 100 KB required');
      return {format:args.format,filename:args.filename,title:args.title ?? '',content:args.content};
    }
    if (action === 'configure_audio' || action === 'configure_brightness') {
      const audio = action === 'configure_audio';
      const allowed = audio ? ['volume','muted','device_id','previous_volume','previous_muted'] : ['brightness','monitor_id','previous_brightness'];
      if (Object.keys(args).some(key => !allowed.includes(key))) throw new TypeError('Unknown native control argument');
      const percent = value => Number.isInteger(value) && value >= 0 && value <= 100;
      if (audio) {
        const volume = args.volume ?? null, muted = args.muted ?? null;
        if ((volume === null) === (muted === null) || (volume !== null && !percent(volume)) || (muted !== null && typeof muted !== 'boolean')) throw new TypeError('Specify one validated master-volume percentage or mute boolean');
        if (['device_id','previous_volume','previous_muted'].some(key => Object.hasOwn(args,key))) {
          if (typeof args.device_id !== 'string' || !args.device_id || args.device_id.length > 300 ||
              typeof args.previous_volume !== 'number' || !Number.isFinite(args.previous_volume) || args.previous_volume < 0 || args.previous_volume > 100 || typeof args.previous_muted !== 'boolean') throw new TypeError('Incomplete audio device snapshot');
          return {volume,muted,device_id:args.device_id,previous_volume:args.previous_volume,previous_muted:args.previous_muted};
        }
        return {volume,muted};
      }
      if (!percent(args.brightness) || (args.monitor_id != null && (typeof args.monitor_id !== 'string' || !args.monitor_id || args.monitor_id.length > 300))) throw new TypeError('Validated brightness and monitor ID required');
      if (Object.hasOwn(args,'previous_brightness') && (!percent(args.previous_brightness) || !args.monitor_id)) throw new TypeError('Incomplete brightness device snapshot');
      return {brightness:args.brightness,monitor_id:args.monitor_id ?? null,...(Object.hasOwn(args,'previous_brightness') ? {previous_brightness:args.previous_brightness} : {})};
    }
    if (action === 'write_file') {
      this.filePath(args.path);
      if (typeof args.content !== 'string' || Buffer.byteLength(args.content) > 100000) throw new TypeError('File content must be text under 100 KB');
      return {path: args.path, content: args.content};
    }
    if (action === 'create_task') {
      if (typeof args.title !== 'string' || !args.title.trim() || args.title.length > 500) throw new TypeError('Task title must be 1 to 500 characters');
      return {title: args.title.trim()};
    }
    if (action === 'complete_task') {
      if (!Number.isSafeInteger(args.task_id) || args.task_id < 1) throw new TypeError('A positive task ID is required');
      return {task_id: args.task_id};
    }
    if (action === 'launch_app' && ['notepad', 'calculator'].includes(args.app)) return {app: args.app};
    if (action === 'open_browser') return {url:browserUrl(args.url)};
    if (action === 'set_tool_enabled') {
      if (!CONTROLLED_TOOLS.has(args.tool_id) || TOOL_IDS.protected.includes(args.tool_id) || typeof args.enabled !== 'boolean') {
        throw Object.assign(new Error('Only existing optional tools can be enabled or disabled. Security gates cannot be disabled.'), {code:'PERMISSION_DENIED'});
      }
      return {tool_id:args.tool_id, enabled:args.enabled};
    }
    if (action === 'writer_review' && this.writer && typeof args.prompt === 'string' && args.prompt.length <= 4000 &&
        ['LINE EDIT','DEVELOPMENTAL FEEDBACK','CONTINUITY CHECK','DRAFT'].includes(args.mode) && typeof args.model === 'string' &&
        Array.isArray(args.sources) && args.sources.length > 0 && args.sources.length <= 12 && Buffer.byteLength(JSON.stringify(args.sources)) <= 70000) {
      return {prompt:args.prompt, mode:args.mode, model:args.model, sources:args.sources};
    }
    throw Object.assign(new Error('This action is not permitted by the assistant bridge'), {code: 'PERMISSION_DENIED'});
  }
  pending(session) {
    const row = this.db.prepare("SELECT * FROM confirmations WHERE session=? AND status='pending' ORDER BY rowid DESC LIMIT 1").get(session);
    if (!row) return null;
    if (row.expires < this.now()) {
      this.db.prepare("UPDATE confirmations SET status='expired' WHERE id=?").run(row.id);
      return null;
    }
    return {id: row.id, lane: row.lane, tool_id:TOOL_IDS.actions[row.action], description: row.description, consequence: row.consequence, expires_at: new Date(row.expires).toISOString()};
  }
  invalidate(session) { this.db.prepare("UPDATE confirmations SET status='superseded' WHERE session=? AND status='pending'").run(session); }
  propose(session, lane, action, rawArgs) {
    let args = this.validate(action, rawArgs);
    this.assertEnabled(TOOL_IDS.actions[action]);
    let nativePreview = null;
    if (action === 'export_document') {
      nativePreview = this.documents({operation:'prepare',args});
      const prepared = this.validate(action,nativePreview.args);
      if (JSON.stringify(prepared) !== JSON.stringify(args) || typeof nativePreview.description !== 'string' || typeof nativePreview.consequence !== 'string') throw new TypeError('Document preview differs from the request');
    }
    if (['configure_audio','configure_brightness'].includes(action)) {
      // Device identity and previous settings come from a native read, never model-supplied fields.
      if (Object.keys(args).some(key => key.startsWith('previous_') || key === 'device_id')) throw new TypeError('Device snapshots are server-owned');
      nativePreview = this.nativeControl({operation:'prepare',action,args});
      args = this.validate(action,nativePreview.args);
      if (typeof nativePreview.description !== 'string' || typeof nativePreview.consequence !== 'string') throw new TypeError('Native preview is incomplete');
    }
    const description = action === 'set_tool_enabled' ? `${args.enabled ? 'Enable' : 'Disable'} assistant capability ${args.tool_id}.` : action === 'writer_review' ? `Send selected excerpts from ${args.sources.map(row => `${row.source}:${row.line_start}-${row.line_end}`).join(', ')} to Anthropic model ${args.model} for ${args.mode}.` : action === 'open_browser' ? `Request your default browser to open ${args.url}` : action === 'write_file' ? `Create files/${args.path} with the supplied ${Buffer.byteLength(args.content)} bytes of text.` : action === 'create_task' ? `Save the to-do: ${args.title}` : action === 'complete_task' ? `Mark task ${args.task_id} complete.` : `Open ${args.app} on this Windows computer.`;
    const consequence = action === 'set_tool_enabled' ? (args.enabled ? 'Allows this installed adapter under its existing permissions. Missing dependencies and confirmations remain mandatory.' : 'Blocks new uses and revokes pending approvals for this tool. Work already dispatched cannot be undone.') : action === 'writer_review' ? 'Shares these private source excerpts and your request with Anthropic and uses its paid API. Returns feedback only; no manuscript file is changed.' : action === 'open_browser' ? 'Opens a public page in your default browser. The site receives the URL request and may use your existing browser session. No form is submitted.' : action === 'write_file' ? 'Writes a new file inside assistant_workspace only. Existing files are never overwritten.' : action === 'launch_app' ? 'Starts a visible app. No commands, scripts, or trading settings will be changed.' : 'Changes your saved to-do list. It does not execute or schedule the task.';
    const approvedDescription = nativePreview?.description || description;
    const approvedConsequence = nativePreview?.consequence || consequence;
    const id = randomUUID(), expires = this.now() + 5 * 60 * 1000;
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.invalidate(session);
      this.db.prepare('INSERT INTO confirmations VALUES(?,?,?,?,?,?,?,?,?)').run(id, session, lane, action, JSON.stringify(args), approvedDescription, approvedConsequence, 'pending', expires);
      this.audit(session, lane, action, 'pending_confirmation');
      this.db.exec('COMMIT');
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
    return {lane, status: 'pending_confirmation', response: `${lane}: ${approvedDescription} ${approvedConsequence} Confirm or cancel before I proceed.`, pending: this.pending(session)};
  }
  listTasks() { return this.db.prepare('SELECT * FROM tasks ORDER BY id DESC LIMIT 100').all(); }
  execute(action, args, approval = null) {
    args = this.validate(action, args);
    this.assertEnabled(TOOL_IDS.actions[action]);
    if (action === 'export_document') {
      if (!approval) throw Object.assign(new Error('Separate document approval required'), {code:'CONFIRMATION_REQUIRED'});
      const data = this.documents({operation:'execute',args,approval});
      if (data?.verified !== true) throw Object.assign(new Error('Document output was not verified'), {code:'VERIFICATION_FAILED'});
      return data;
    }
    if (['configure_audio','configure_brightness'].includes(action)) {
      if (!approval) throw Object.assign(new Error('Separate native approval required'), {code:'CONFIRMATION_REQUIRED'});
      const data = this.nativeControl({operation:'execute',action,args,approval});
      if (data?.verified !== true) throw Object.assign(new Error('Native setting was not verified'), {code:'VERIFICATION_FAILED'});
      return data;
    }
    if (action === 'set_tool_enabled') {
      this.db.exec('BEGIN IMMEDIATE');
      try {
        this.db.prepare('INSERT INTO tool_controls VALUES(?,?,?) ON CONFLICT(tool_id) DO UPDATE SET enabled=excluded.enabled, updated=excluded.updated').run(args.tool_id, Number(args.enabled), new Date(this.now()).toISOString());
        if (!args.enabled) {
          const actions = Object.entries(TOOL_IDS.actions).filter(([, id]) => id === args.tool_id).map(([name]) => name);
          for (const name of actions) this.db.prepare("UPDATE confirmations SET status='revoked' WHERE action=? AND status='pending'").run(name);
        }
        this.db.exec('COMMIT');
      } catch (error) { this.db.exec('ROLLBACK'); throw error; }
      const enabled = Boolean(this.db.prepare('SELECT enabled FROM tool_controls WHERE tool_id=?').get(args.tool_id).enabled);
      if (enabled !== args.enabled) throw Object.assign(new Error('Saved tool policy failed verification'), {code:'VERIFICATION_FAILED'});
      return {tool_id:args.tool_id, enabled, verified:true};
    }
    if (action === 'write_file') {
      const target = this.filePath(args.path);
      mkdirSync(path.dirname(target), {recursive: true});
      this.filePath(args.path);
      writeFileSync(target, args.content, {encoding: 'utf8', flag: 'wx'});
      if (readFileSync(target, 'utf8') !== args.content) throw Object.assign(new Error('Saved file differs from approved content'), {code:'VERIFICATION_FAILED'});
      return {path: `files/${args.path}`, bytes: Buffer.byteLength(args.content), verified:true};
    }
    if (action === 'create_task') {
      const id = Number(this.db.prepare('INSERT INTO tasks(title) VALUES(?)').run(args.title).lastInsertRowid);
      if (this.db.prepare('SELECT title FROM tasks WHERE id=?').get(id)?.title !== args.title) throw Object.assign(new Error('Saved task failed verification'), {code:'VERIFICATION_FAILED'});
      return {task_id:id, title:args.title, verified:true};
    }
    if (action === 'complete_task') {
      if (!this.db.prepare("UPDATE tasks SET status='complete' WHERE id=? AND status='pending'").run(args.task_id).changes) throw Object.assign(new Error(`Pending task ${args.task_id} does not exist`), {code: 'TASK_NOT_FOUND'});
      if (this.db.prepare('SELECT status FROM tasks WHERE id=?').get(args.task_id)?.status !== 'complete') throw Object.assign(new Error('Task completion failed verification'), {code:'VERIFICATION_FAILED'});
      return {task_id: args.task_id, status: 'complete', verified:true};
    }
    if (action === 'writer_review') return this.writer(args);
    if (action === 'open_browser') return this.openBrowser(args.url);
    return this.launch(args.app);
  }
  confirm(session, id, decision) {
    if (typeof decision !== 'boolean') throw new TypeError('Confirmation decision must be explicit');
    this.db.exec('BEGIN IMMEDIATE');
    let row;
    try {
      row = this.db.prepare("SELECT * FROM confirmations WHERE id=? AND session=? AND status='pending'").get(id, session);
      if (!row || row.expires < this.now()) throw Object.assign(new Error('Confirmation is absent, expired, or already used'), {code: 'STALE_CONFIRMATION'});
      if (decision) this.assertEnabled(TOOL_IDS.actions[row.action]);
      this.db.prepare('UPDATE confirmations SET status=? WHERE id=?').run(decision ? 'executing' : 'cancelled', id);
      this.db.exec('COMMIT');
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
    if (!decision) { this.audit(session, row.lane, row.action, 'cancelled'); return {lane: row.lane, status: 'cancelled', response: `${row.lane}: Cancelled. Nothing was executed.`}; }
    const complete = data => {
      this.db.prepare("UPDATE confirmations SET status='complete' WHERE id=?").run(id);
      this.audit(session, row.lane, row.action, 'success');
      const dispatched = ['launch_app','open_browser'].includes(row.action);
      return {lane: row.lane, status: 'success', tool_id:TOOL_IDS.actions[row.action], verified:data.verified === true, data, response: data.response || `${row.lane}: ${dispatched ? 'Dispatched' : 'Completed'}. ${row.description}`};
    };
    const fail = error => {
      this.db.prepare("UPDATE confirmations SET status='failed' WHERE id=?").run(id);
      this.audit(session, row.lane, row.action, 'failed', error);
      const details = cleanError(error);
      return {lane: row.lane, status: 'failed', error: details, response: `${row.lane}: ${details.code}: ${details.message}`};
    };
    try {
      const data = this.execute(row.action, JSON.parse(row.args), {id:row.id,session});
      return data instanceof Promise ? data.then(complete).catch(fail) : complete(data);
    } catch (error) {
      return fail(error);
    }
  }
}
