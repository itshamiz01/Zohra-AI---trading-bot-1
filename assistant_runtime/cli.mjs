import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {AssistantRuntime} from './runtime.mjs';
import {cleanError} from './gate.mjs';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const chunks = [];
let size = 0, runtime, input;
try {
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > 200000) throw new Error('Assistant bridge input exceeds 200 KB');
    chunks.push(chunk);
  }
  input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  runtime = new AssistantRuntime(process.env.ZOHRA_ASSISTANT_WORKSPACE || path.join(project, 'assistant_workspace'));
  const result = await runtime.request(input);
  process.stdout.write(JSON.stringify(result));
} catch (error) {
  const details = cleanError(error);
  if (runtime) runtime.gate.audit(input?.session_id || 'bridge', null, input?.operation || 'request', 'failed', error);
  process.stdout.write(JSON.stringify({status: 'failed', error: details, response: `${details.code}: ${details.message}`}));
  process.exitCode = 1;
} finally { runtime?.close(); }
