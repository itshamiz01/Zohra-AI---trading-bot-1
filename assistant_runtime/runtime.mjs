import {classify} from './router.mjs';
import {ConfirmationGate, cleanError} from './gate.mjs';
import {WriterAgent} from './writer.mjs';
import path from 'node:path';

export class AssistantRuntime {
  constructor(root, options = {}) {
    this.writer = options.writer || new WriterAgent(process.env.ZOHRA_WRITER_ROOT || path.join(root, 'manuscripts'));
    this.gate = new ConfirmationGate(root, {...options, writer: args => this.writer.run(args)});
  }
  close() { this.gate.close(); }
  request(input) {
    const {session_id: session, operation = 'message'} = input;
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(session || '')) throw new TypeError('Invalid conversation session');
    if (operation === 'classify') return classify(input.text);
    if (operation === 'pending') return {pending: this.gate.pending(session)};
    if (operation === 'invalidate') { this.gate.invalidate(session); return {status:'invalidated'}; }
    if (operation === 'tasks') {
      const tasks = this.gate.listTasks();
      return {tasks, pending_count:tasks.filter(row => row.status === 'pending').length};
    }
    if (operation === 'writer_sources') return {sources:this.writer.context.files()};
    if (operation === 'report') {
      if (!['TRADING', 'WRITING', 'TASK', 'CHAT'].includes(input.lane) ||
          !['success', 'failed', 'needs_context', 'cancelled'].includes(input.status)) throw new TypeError('Invalid audit result');
      this.gate.audit(session, input.lane, input.action, input.status, input.error);
      return {status: 'recorded'};
    }
    if (operation === 'confirm') {
      if (typeof input.decision !== 'boolean') throw new TypeError('Confirmation decision must be explicit');
      return this.gate.confirm(session, input.confirmation_id, input.decision);
    }
    if (operation !== 'message' && operation !== 'propose') throw new TypeError('Unknown bridge operation');
    if (operation === 'propose') { this.gate.invalidate(session); return this.gate.propose(session, 'TASK', input.action, input.args); }
    const text = typeof input.text === 'string' ? input.text.trim() : input.text;
    if (/^(?:confirm|yes|haan|\u0939\u093e\u0901|cancel|no|nahi)$/i.test(text || '')) {
      const pending = this.gate.pending(session);
      if (!pending) {
        this.gate.audit(session, 'TASK', 'confirm', 'failed', Object.assign(new Error('No pending action'), {code:'NO_PENDING_ACTION'}));
        return {lane: 'TASK', status: 'failed', response: 'TASK: There is no pending action to confirm.', error: {code: 'NO_PENDING_ACTION', message: 'No pending action'}};
      }
      return this.gate.confirm(session, pending.id, /^(?:confirm|yes|haan|\u0939\u093e\u0901)$/i.test(text));
    }
    const route = classify(text);
    if (route.status === 'invalid') { this.gate.audit(session, null, 'invalid', 'failed'); return route; }
    this.gate.invalidate(session);
    if (['write_file', 'export_document', 'create_task', 'complete_task', 'launch_app', 'open_browser', 'set_tool_enabled', 'configure_audio', 'configure_brightness'].includes(route.action)) return this.gate.propose(session, route.lane, route.action, route.args);
    if (route.action === 'blocked_trading_write') {
      this.gate.audit(session, 'TRADING', route.action, 'blocked');
      return {...route, status: 'blocked', response: 'TRADING: Risk-control health and a safe write adapter are unverified in this checkout. Trading writes and risk overrides are blocked, even after confirmation.'};
    }
    if (route.action === 'list_tasks') {
      const tasks = this.gate.listTasks();
      this.gate.audit(session, route.lane, route.action, 'success');
      return {...route, status: 'success', data: tasks, response: 'TASK: ' + (tasks.length ? tasks.map(row => `#${row.id} [${row.status}] ${row.title}`).join('\n') : 'Your to-do list is empty.')};
    }
    if (route.action === 'writer') {
      try { return this.gate.propose(session, 'WRITING', 'writer_review', this.writer.prepare(text, route.mode)); }
      catch (error) {
        const status = ['CONFIGURATION_REQUIRED','CONTEXT_REQUIRED','AMBIGUOUS_SOURCE'].includes(error.code) ? 'needs_context' : 'failed';
        this.gate.audit(session, 'WRITING', 'writer', status, error);
        const details = cleanError(error);
        return {...route, status, response:`WRITING: ${details.code}: ${details.message}`, error:details};
      }
    }
    this.gate.audit(session, route.lane, route.action, route.status || 'routed');
    return {...route, status: route.status || 'routed'};
  }
}
