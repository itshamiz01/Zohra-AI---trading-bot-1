import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {AssistantRuntime} from '../runtime.mjs';
import {classify} from '../router.mjs';

test('document content is data and requests choose exactly one TASK lane', () => {
  for (const [kind,format] of [['PDF','pdf'],['Word document','docx'],['Excel workbook','xlsx']]) {
    const result = classify(`create ${kind} "report.${format}" with Close trades and edit my chapter`);
    assert.equal(result.lane,'TASK'); assert.equal(result.action,'export_document');
    assert.equal(result.args.format,format); assert.equal(result.args.content,'Close trades and edit my chapter');
  }
  assert.equal(classify('pdf "memo.pdf" banao with Test text').action,'export_document');
  assert.equal(classify('create a PDF').status,'needs_context');
});

test('verified PDF read and search commands route to one read-only action', () => {
  assert.deepEqual(classify('read PDF "report.pdf"'), {lane:'TASK',action:'pdf_inspect',args:{filename:'report.pdf',page:null,query:''}});
  assert.deepEqual(classify('inspect PDF "report.pdf" page 2'), {lane:'TASK',action:'pdf_inspect',args:{filename:'report.pdf',page:2,query:''}});
  assert.deepEqual(classify('search PDF "report.pdf" for comet'), {lane:'TASK',action:'pdf_inspect',args:{filename:'report.pdf',page:null,query:'comet'}});
});

test('only the separate approved document action dispatches and requires verified output', t => {
  const root = mkdtempSync(path.join(os.tmpdir(),'zohra-documents-'));
  const calls = [];
  const runtime = new AssistantRuntime(root,{documents:request => {
    calls.push(request);
    return request.operation === 'prepare' ? {args:request.args,description:'Create exact document',consequence:'New local file'} : {verified:true,artifact_id:'test'};
  }});
  t.after(()=>runtime.close());
  const send = text => runtime.request({session_id:'test',text});
  const proposal = send('create PDF "report.pdf" with Test and confirm');
  assert.equal(proposal.pending.tool_id,'documents.create');
  assert.deepEqual(calls.map(row=>row.operation),['prepare']);
  assert.equal(send('confirm').verified,true);
  assert.equal(calls[1].approval.id,proposal.pending.id);
  assert.equal(send('confirm').status,'failed');
  assert.throws(()=>runtime.gate.execute('export_document',calls[0].args),/approval required/);
  assert.throws(()=>runtime.gate.propose('test','TASK','export_document',{...calls[0].args,filename:'../escape.pdf'}),/Validated document/);
  runtime.gate.documents = request => request.operation === 'prepare' ? {args:request.args,description:'Create document',consequence:'New file'} : {verified:false};
  send('create PDF "unverified.pdf" with Text');
  assert.equal(send('confirm').error.code,'VERIFICATION_FAILED');
});

test('document preview cannot substitute content and revocation cancels pending exports', t => {
  const root = mkdtempSync(path.join(os.tmpdir(),'zohra-documents-'));
  const runtime = new AssistantRuntime(root,{documents:request => ({args:request.args,description:'Create document',consequence:'New file'})});
  t.after(()=>runtime.close());
  const proposal = runtime.request({session_id:'test',text:'create Word "memo.docx" with Private note'});
  runtime.request({session_id:'owner',text:'disable tool documents.create'});
  runtime.request({session_id:'owner',text:'confirm'});
  assert.throws(()=>runtime.request({session_id:'test',operation:'confirm',confirmation_id:proposal.pending.id,decision:true}),/already used/);
  runtime.request({session_id:'owner',text:'enable tool documents.create'});
  runtime.request({session_id:'owner',text:'confirm'});
  runtime.gate.documents = request => ({args:{...request.args,content:'substituted'},description:'Create document',consequence:'New file'});
  assert.throws(()=>runtime.request({session_id:'test',text:'create PDF "memo.pdf" with Original'}),/differs from the request/);
});
