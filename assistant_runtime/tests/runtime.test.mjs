import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, existsSync, writeFileSync, mkdirSync, symlinkSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {AssistantRuntime} from '../runtime.mjs';
import {classify} from '../router.mjs';

const requests = {
  TRADING: ['Show open positions', 'What is daily P&L?', 'Show account balance', 'Give me risk status', 'Recent trading performance'],
  WRITING: ['Line edit my chapter', 'Developmental feedback on my novel', 'Continuity check the character bible', 'Draft a scene', 'Write a publisher query'],
  TASK: ['Search NASA news', 'Show CPU usage', 'List my tasks', 'Open Notepad', 'write file "memo.txt" with Trading notes'],
  CHAT: ['Hello Zohra', 'Tell me a joke', 'What is recursion?', 'How was your day?', 'Thanks for the help'],
};
for (const [lane, texts] of Object.entries(requests)) for (const text of texts) {
  test(`routes ${lane}: ${text}`, () => assert.equal(classify(text).lane, lane));
}
function fixture(t, options = {}) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'zohra-runtime-'));
  const runtime = new AssistantRuntime(root, options);
  t.after(() => runtime.close());
  return {root, runtime, send: text => runtime.request({session_id:'test', text})};
}
test('mixed lanes clarify; file content is data, not another instruction', () => {
  assert.equal(classify('Close positions and edit my chapter').status, 'clarify');
  assert.equal(classify('write file "memo.txt" with close all trades').lane, 'TASK');
});

test('capability controls persist, revoke pending approvals and cannot disable security', t => {
  const {root, runtime, send} = fixture(t);
  const pending = send('write file "revoked.txt" with no write');
  const control = runtime.request({session_id:'security', text:'disable tool files.create'});
  assert.equal(control.status, 'pending_confirmation');
  assert.equal(runtime.request({session_id:'security', text:'confirm'}).data.enabled, false);
  assert.throws(() => runtime.request({session_id:'test', operation:'confirm', confirmation_id:pending.pending.id, decision:true}), /already used/);
  assert.equal(existsSync(path.join(root,'files','revoked.txt')), false);
  assert.throws(() => send('write file "another.txt" with no write'), /revoked/);
  assert.throws(() => send('disable tool security.configure'), /cannot be disabled/);
  assert.throws(() => send('enable tool trading.write'), /cannot be disabled/);
  runtime.request({session_id:'security', text:'enable tool files.create'});
  assert.equal(runtime.request({session_id:'security', text:'confirm'}).data.verified, true);
  assert.equal(send('write file "verified.txt" with checked content').status, 'pending_confirmation');
  assert.equal(send('confirm').data.verified, true);
  assert.equal(readFileSync(path.join(root,'files','verified.txt'),'utf8'), 'checked content');
});

test('new monitoring requests route without competing voice logic', () => {
  for (const [text, action] of [['What can you do?', 'capability_inventory'], ['Show running processes', 'process_status'],
      ['Network status', 'network_status'], ['computer slow kyun hai', 'process_status'], ['tools dikhao', 'capability_inventory']]) {
    assert.equal(classify(text).action, action);
    assert.equal(classify(text).lane, 'TASK');
  }
});

test('unsupported device commands never fall through to conversational success claims', () => {
  for (const text of ['Open Spotify', 'Take a screenshot', 'Send an email',
      'Delete the folder', 'Restart my computer', 'kholo app', '\u092b\u094b\u0932\u094d\u0921\u0930 \u0921\u093f\u0932\u0940\u091f \u0915\u0930\u094b']) {
    assert.equal(classify(text).lane, 'TASK');
    assert.equal(classify(text).status, 'unsupported');
  }
});

test('native volume, mute and brightness have one exact action and no partial matching', () => {
  for (const [text,action,args] of [
    ['Set my volume to 40%','configure_audio',{volume:40}], ['Mute my computer','configure_audio',{muted:true}],
    ['Unmute','configure_audio',{muted:false}], ['Set screen brightness to 10%','configure_brightness',{brightness:10}],
    ['volume 25 karo','configure_audio',{volume:25}], ['brightness 30 kar do','configure_brightness',{brightness:30}],
    ['\u0906\u0935\u093e\u091c 25 \u0915\u0930\u094b','configure_audio',{volume:25}],
  ]) {assert.equal(classify(text).action,action); assert.deepEqual(classify(text).args,args);}
  assert.equal(classify('show volume').action,'audio_status');
  assert.equal(classify('display status').action,'display_status');
  for (const text of ['set volume to 40% and delete files','mute and close trades','increase brightness']) assert.ok(!['configure_audio','configure_brightness'].includes(classify(text).action));
});

test('native changes wait for an exact approval, cannot replay, and reject unverified results', t => {
  const calls = [];
  const {runtime, send} = fixture(t,{nativeControl:input => {
    calls.push(input);
    if (input.operation === 'prepare') return {args:{volume:input.args.volume,muted:null,device_id:'test-speaker',previous_volume:50,previous_muted:false},description:'Set test-speaker volume to 40%.',consequence:'Changes master volume from 50%.'};
    return {verified:true,after:{volume:40}};
  }});
  const proposal = send('set volume to 40%');
  assert.equal(proposal.status,'pending_confirmation');
  assert.deepEqual(calls.map(x=>x.operation),['prepare']);
  assert.equal(send('confirm').verified,true);
  assert.equal(calls[1].approval.id,proposal.pending.id);
  assert.equal(calls[1].approval.session,'test');
  assert.equal(send('confirm').status,'failed');
  assert.equal(calls.length,2);
  assert.throws(()=>runtime.gate.execute('configure_audio',{volume:40}),/approval required/);
  assert.throws(()=>send('set volume to 101%'),/validated/);
  runtime.gate.nativeControl = input => input.operation === 'prepare' ? {args:{volume:40,muted:null,device_id:'test-speaker',previous_volume:50,previous_muted:false},description:'Set volume',consequence:'Change'} : {verified:false};
  send('set volume to 40%');
  assert.equal(send('confirm').error.code,'VERIFICATION_FAILED');
});

test('native device snapshots cannot be supplied by a model and revocation blocks execution', t => {
  const {runtime,send} = fixture(t,{nativeControl:input => ({args:{volume:40,muted:null,device_id:'test-speaker',previous_volume:50,previous_muted:false},description:'Set volume',consequence:'Change'})});
  assert.throws(()=>runtime.gate.propose('test','TASK','configure_audio',{volume:40,device_id:'injected',previous_volume:50,previous_muted:false}),/server-owned/);
  const pending = send('set volume to 40%');
  runtime.request({session_id:'security',text:'disable tool windows.audio'});
  runtime.request({session_id:'security',text:'confirm'});
  assert.throws(()=>runtime.request({session_id:'test',operation:'confirm',confirmation_id:pending.pending.id,decision:true}),/already used/);
});
test('a real file does not exist before a separate confirmation and is written exactly once', t => {
  const {root, runtime, send} = fixture(t);
  const proposal = send('write file "notes.txt" with approved text');
  assert.equal(proposal.status, 'pending_confirmation');
  const target = path.join(root, 'files', 'notes.txt');
  assert.equal(existsSync(target), false);
  assert.equal(send('confirm').status, 'success');
  assert.equal(readFileSync(target, 'utf8'), 'approved text');
  assert.throws(() => runtime.request({session_id:'test', operation:'confirm', confirmation_id:proposal.pending.id, decision:true}), /already used/);
});
test('confirmation cannot be included in the same write utterance', t => {
  const {root, send} = fixture(t);
  assert.equal(send('write file "memo.txt" with test and confirm').status, 'pending_confirmation');
  assert.equal(existsSync(path.join(root, 'files', 'memo.txt')), false);
});
test('cancel and unrelated turns invalidate an old proposal', t => {
  const {runtime, send} = fixture(t);
  let proposal = send('add task call a friend');
  assert.equal(send('cancel').status, 'cancelled');
  assert.equal(runtime.gate.listTasks().length, 0);
  proposal = send('add task call a friend');
  send('Hello');
  assert.throws(() => runtime.gate.confirm('test', proposal.pending.id, true), /absent/);
});
test('confirmation expires and cannot move between sessions', t => {
  let now = 1000;
  const {runtime, send} = fixture(t, {now: () => now});
  const proposal = send('add task call a friend');
  assert.throws(() => runtime.gate.confirm('someone-else', proposal.pending.id, true), /absent/);
  now += 300001;
  assert.equal(runtime.gate.pending('test'), null);
  assert.throws(() => runtime.gate.confirm('test', proposal.pending.id, true), /expired/);
});
test('actual executor errors are reported and recorded, not converted to success', t => {
  const {root, runtime, send} = fixture(t);
  mkdirSync(path.join(root, 'files'));
  writeFileSync(path.join(root, 'files', 'existing.txt'), 'preserve');
  send('write file "existing.txt" with replacement');
  const result = send('confirm');
  assert.equal(result.status, 'failed');
  assert.equal(result.error.code, 'EEXIST');
  assert.match(result.response, /EEXIST/);
  assert.equal(readFileSync(path.join(root, 'files', 'existing.txt'), 'utf8'), 'preserve');
  const audit = runtime.gate.db.prepare("SELECT * FROM audit WHERE status='failed'").get();
  assert.equal(JSON.parse(audit.error).code, 'EEXIST');
});
test('path traversal, absolute paths, scripts, and links are rejected before proposal', t => {
  const {root, runtime} = fixture(t);
  for (const name of ['../engine.py', '../escape.txt', '/outside.txt', 'C:/Windows/a.txt', 'run.ps1', 'a/../b.txt', 'NUL.txt', 'CON.md', 'COM1/test.txt', 'folder./a.txt', 'folder /a.txt']) {
    assert.throws(() => runtime.gate.propose('test','TASK','write_file',{path:name, content:'test'}), /relative|escapes/);
  }
  mkdirSync(path.join(root, 'files'));
  const outside = mkdtempSync(path.join(os.tmpdir(), 'zohra-outside-'));
  symlinkSync(outside, path.join(root, 'files', 'linked'), 'junction');
  assert.throws(() => runtime.gate.propose('test','TASK','write_file',{path:'linked/a.txt',content:'test'}), /Links/);
});
test('to-do changes and app launches wait for confirmation', t => {
  const launches = [];
  const {runtime, send} = fixture(t, {launch: app => { launches.push(app); return {app}; }});
  send('add task read a chapter');
  assert.equal(runtime.gate.listTasks().length, 0);
  assert.equal(send('confirm').status, 'success');
  send('complete task 1');
  assert.equal(runtime.gate.listTasks()[0].status, 'pending');
  send('confirm');
  assert.equal(runtime.gate.listTasks()[0].status, 'complete');
  send('Open Calculator');
  assert.deepEqual(launches, []);
  send('confirm');
  assert.deepEqual(launches, ['calculator']);
});
test('trading writes and arbitrary commands stay denied, including repeated requests', t => {
  const {runtime, send} = fixture(t);
  for (let i=0;i<3;i++) assert.equal(send('Close all trades').status, 'blocked');
  assert.throws(() => runtime.gate.propose('test','TRADING','place_trade',{}), /not permitted/);
  assert.throws(() => runtime.gate.propose('test','TASK','launch_app',{app:'powershell'}), /not permitted/);
});

test('read-only open positions and stop-loss queries are not mistaken for write commands', t => {
  const {send} = fixture(t);
  for (const text of ['Show open positions', 'Do I have open trading positions?', 'What is my stop-loss risk?']) {
    assert.equal(send(text).action, 'backend_update');
  }
  for (const text of ['Open a trade', 'Can you open a trade?', 'Show open positions and then open a trade', 'Modify risk to 1%']) {
    assert.equal(send(text).status, 'blocked');
  }
});

test('browser requests use an exact confirmed URL and deny local/secret addresses', t => {
  const opened = [];
  const {send, runtime} = fixture(t, {openBrowser:url => { opened.push(url); return {status:'dispatched_to_default_browser'}; }});
  assert.equal(send('Open https://www.nasa.gov/').status, 'pending_confirmation');
  assert.deepEqual(opened, []);
  send('confirm');
  assert.deepEqual(opened, ['https://www.nasa.gov/']);
  for (const url of ['javascript:alert(1)', 'file:///secret', 'http://127.0.0.1:8011/', 'https://user:password@example.org/', 'https://example.org/?token=secret', 'http://2130706433/']) {
    assert.throws(() => runtime.gate.propose('test','TASK','open_browser',{url}), /public|not permitted/);
  }
});
