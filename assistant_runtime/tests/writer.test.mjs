import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, symlinkSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {WriterAgent, ManuscriptContext, validateOutput} from '../writer.mjs';
import {AssistantRuntime} from '../runtime.mjs';

// Synthetic fixtures validate the contract, not the author's books or live model quality.
function fixture(t, output = null) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'zohra-writer-'));
  const manuscripts = path.join(root, 'manuscripts');
  mkdirSync(path.join(manuscripts, 'characters'), {recursive:true});
  writeFileSync(path.join(manuscripts, 'characters', 'mara.md'), "Mara's eyes are grey, never blue.\nMara is left-handed.");
  writeFileSync(path.join(manuscripts, 'chapter-01.md'), "Mara's blue eyes followed the unopened letter.\nShe waited in the doorway.");
  const calls = [];
  const writer = new WriterAgent(manuscripts, {apiKey:'fixture-key', model:'fixture-model', transport:async (url, options) => {
    calls.push({url, options});
    return new Response(JSON.stringify({stop_reason:'end_turn', content:[{type:'text',text:JSON.stringify(output)}]}), {status:200});
  }});
  const runtime = new AssistantRuntime(root, {writer});
  t.after(() => runtime.close());
  return {root, manuscripts, writer, runtime, calls};
}
const bible = {source:'characters/mara.md', line_start:1, line_end:1, quote:"Mara's eyes are grey, never blue."};
const chapter = {source:'chapter-01.md', line_start:1, line_end:1, quote:"Mara's blue eyes followed the unopened letter."};
const continuity = {mode:'CONTINUITY CHECK', findings:[{verdict:'contradiction', detail:"The chapter says blue eyes, but the character bible fixes Mara's eyes as grey.", evidence:[bible, chapter]}]};

test('context contains real selected source lines and separate bible/manuscript roles', t => {
  const {writer} = fixture(t);
  const plan = writer.prepare('Continuity check chapter-01.md', 'CONTINUITY CHECK');
  assert.equal(plan.sources.length, 2);
  assert.equal(plan.sources[0].kind, 'bible');
  assert.equal(plan.sources[1].line_start, 1);
  assert.match(plan.sources[1].text, /blue eyes/);
  assert.ok(plan.sources.every(row => /^[a-f0-9]{64}$/.test(row.hash)));
});

test('private manuscript transmission waits for its own separate confirmation', async t => {
  const {runtime, calls} = fixture(t, continuity);
  const proposal = runtime.request({session_id:'test', text:'Continuity check chapter-01.md'});
  assert.equal(proposal.status, 'pending_confirmation');
  assert.match(proposal.pending.description, /Anthropic model fixture-model/);
  assert.match(proposal.pending.consequence, /private.*paid API/);
  assert.equal(calls.length, 0);
  const result = await runtime.request({session_id:'test', text:'confirm'});
  assert.equal(result.status, 'success');
  assert.match(result.response, /WRITING: CONTINUITY CHECK/);
  assert.match(result.response, /contradiction/);
  assert.match(result.response, /characters\/mara.md:1-1/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://api.anthropic.com/v1/messages');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.model, 'fixture-model');
  assert.equal(body.tools, undefined);
  assert.match(body.system, /dark[ -]romance/);
  assert.match(body.messages[0].content, /grey, never blue/);
  assert.match(body.messages[0].content, /blue eyes/);
  assert.throws(() => runtime.request({session_id:'test', operation:'confirm', confirmation_id:proposal.pending.id, decision:true}), /already used/);
});

test('continuity contradictions require actual quotes from both source kinds', t => {
  const {writer} = fixture(t);
  const plan = writer.prepare('Continuity check chapter-01.md', 'CONTINUITY CHECK');
  assert.equal(validateOutput(continuity, plan).findings[0].verdict, 'contradiction');
  assert.throws(() => validateOutput({...continuity, findings:[{...continuity.findings[0], evidence:[chapter]}]}, plan), /both bible and manuscript/);
  assert.throws(() => validateOutput({...continuity, findings:[{...continuity.findings[0], evidence:[{...bible, quote:'invented'}, chapter]}]}, plan), /invented quotation/);
});

test('line edits and developmental feedback are visibly different and grounded', async t => {
  const line = fixture(t, {mode:'LINE EDIT', edits:[{evidence:chapter,
    replacement:"Mara's grey eyes followed the unopened letter.", reason:'Restores the eye colour established in the character bible.'}]});
  const dev = fixture(t, {mode:'DEVELOPMENTAL FEEDBACK', findings:[{aspect:'pacing', assessment:'works',
    detail:'The unopened letter withholds the reveal and sustains tension before the doorway pause.', evidence:[chapter]}]});
  const edit = await line.writer.run(line.writer.prepare('Line edit chapter-01.md', 'LINE EDIT'));
  const feedback = await dev.writer.run(dev.writer.prepare('Developmental feedback chapter-01.md', 'DEVELOPMENTAL FEEDBACK'));
  assert.match(edit.response, /Original:.*\nEdit:.*\nReason:/);
  assert.match(feedback.response, /pacing \(works\)/);
  assert.ok(!feedback.response.includes('Edit:'));
  assert.equal(readFileSync(path.join(line.manuscripts,'chapter-01.md'),'utf8'), chapter.quote + '\nShe waited in the doorway.');
});

test('drafts retain grounding and do not write manuscript files', async t => {
  const {writer, manuscripts} = fixture(t, {mode:'DRAFT', passage:"Mara's grey eyes stayed on the sealed letter. She left it unopened between them.", grounding:[bible]});
  const result = await writer.run(writer.prepare('Draft a scene', 'DRAFT'));
  assert.match(result.response, /WRITING: DRAFT/);
  assert.match(result.response, /Grounding:/);
  assert.match(readFileSync(path.join(manuscripts, 'chapter-01.md'), 'utf8'), /blue eyes/);
});

test('wrong modes, vague praise, invented source lines, and truncated output are rejected', async t => {
  const {writer} = fixture(t);
  const plan = writer.prepare('Continuity check chapter-01.md', 'CONTINUITY CHECK');
  assert.throws(() => validateOutput({mode:'LINE EDIT'}, plan), /mode/);
  assert.throws(() => validateOutput({...continuity, findings:[{detail:'This is great.'}]}, plan), /specific assessment/);
  assert.throws(() => validateOutput({...continuity, findings:[{...continuity.findings[0], evidence:[{...chapter, line_start:999,line_end:999}]}]}, plan), /unavailable line/);
  writer.transport = async () => new Response(JSON.stringify({stop_reason:'max_tokens',content:[]}));
  await assert.rejects(() => writer.run(plan), /max_tokens/);
});

test('changed manuscript after proposal fails before any external transmission', async t => {
  const {runtime, manuscripts, calls} = fixture(t, continuity);
  runtime.request({session_id:'test', text:'Continuity check chapter-01.md'});
  writeFileSync(path.join(manuscripts,'chapter-01.md'), 'Changed chapter');
  const result = await runtime.request({session_id:'test', text:'yes'});
  assert.equal(result.error.code, 'SOURCE_CHANGED');
  assert.equal(calls.length, 0);
});

test('missing configuration and missing real context do not fabricate reviews', t => {
  const {writer, root} = fixture(t);
  writer.apiKey = '';
  assert.throws(() => writer.prepare('Line edit chapter-01.md','LINE EDIT'), /Configure ANTHROPIC/);
  assert.throws(() => new ManuscriptContext(path.join(root,'missing')).files(), /actual manuscript/);
});

test('source selection asks for the chapter when ambiguous and rejects traversal/links', t => {
  const {writer, manuscripts, root} = fixture(t);
  writeFileSync(path.join(manuscripts, 'chapter-02.md'), 'Another chapter.');
  assert.throws(() => writer.prepare('Line edit my chapter','LINE EDIT'), /Name the chapter filename/);
  assert.throws(() => writer.context.read('../outside.md'), /approved/);
  const outside = mkdtempSync(path.join(os.tmpdir(), 'zohra-writer-outside-'));
  writeFileSync(path.join(outside,'private.md'), 'Private outside text');
  symlinkSync(outside, path.join(manuscripts,'linked'), 'junction');
  assert.throws(() => writer.context.read('linked/private.md'), /junctions/);
  symlinkSync(manuscripts, path.join(root,'linked-root'), 'junction');
  assert.throws(() => new ManuscriptContext(path.join(root,'linked-root')).files(), /cannot be a link/);
});

test('provider errors report their actual status and never switch models or retry a consumed confirmation', async t => {
  const {writer, runtime} = fixture(t);
  let attempts = 0;
  writer.transport = async () => { attempts++; return new Response('Provider rate limit; api_key=private-test-key', {status:429}); };
  runtime.request({session_id:'test', text:'Line edit chapter-01.md'});
  const result = await runtime.request({session_id:'test', text:'confirm'});
  assert.equal(result.status, 'failed');
  assert.equal(result.error.code, 'ANTHROPIC_HTTP_429');
  assert.ok(!result.response.includes('private-test-key'));
  assert.equal(attempts, 1);
});

test('duplicate chapter basenames require a full relative path', t => {
  const {writer, manuscripts} = fixture(t);
  mkdirSync(path.join(manuscripts,'another-book'));
  writeFileSync(path.join(manuscripts,'another-book','chapter-02.md'),'Another chapter.');
  mkdirSync(path.join(manuscripts,'third-book'));
  writeFileSync(path.join(manuscripts,'third-book','chapter-02.md'),'A different chapter.');
  assert.throws(() => writer.prepare('Line edit chapter-02.md','LINE EDIT'), /full relative path/);
});

test('requests to mix writer response modes require clarification', t => {
  const {runtime} = fixture(t);
  const result = runtime.request({session_id:'test',text:'Line edit and continuity check chapter-01.md'});
  assert.equal(result.status, 'clarify');
  assert.equal(runtime.gate.pending('test'), null);
});
