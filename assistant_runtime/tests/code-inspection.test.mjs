import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {classify} from '../router.mjs';

test('explicit code inspection routes to the task lane before trading or writing keywords', () => {
  assert.deepEqual(classify('explain code "zohra/core/engine.py"'),
    {lane:'TASK',action:'code_inspect',args:{path:'zohra/core/engine.py',symbol:''}});
  assert.deepEqual(classify('explain function "register" in "zohra/services/tool_execution/registry.py"'),
    {lane:'TASK',action:'code_inspect',args:{path:'zohra/services/tool_execution/registry.py',symbol:'register'}});
  assert.equal(classify('inspect Python file "zohra/services/chat/assistant_orchestrator.py"').action,'code_inspect');
  assert.equal(classify('explain code "../.env"').action,'code_inspect');
});

test('code inspection is a named revocable read tool, not a write action', () => {
  const ids = JSON.parse(readFileSync(new URL('../tool-ids.json',import.meta.url),'utf8'));
  assert.ok(ids.read_tools.includes('coding.explain'));
  assert.ok(!Object.values(ids.actions).includes('coding.explain'));
});
