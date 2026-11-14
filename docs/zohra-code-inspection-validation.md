# Local Project Code Inspection

Date: 2026-10-02. This is one scoped increment of the universal roadmap, not completion of the Coding Agent.

## Delivered

- `coding.explain` inspects an explicitly named `.py` file under this project's `zohra/` tree. It reports module definitions or the structure of a selected class, function or `Class.method`, with actual line references and a file hash.
- The same read-only adapter is available through Capability Center, the local `/api/v1/assistant/code/inspect` endpoint, typed requests such as `explain function "processes" in "zohra/services/tool_execution/catalog.py"`, and the existing voice-transcript router. No separate voice decision path was added.
- Python's `ast` parses the source without importing or executing it. The output contains structural facts, not source literals or a generated claim about runtime behavior. No source is uploaded to an LLM or sent to a new provider.
- Input is limited to project-relative Python paths. Canonical containment, link/junction rejection, UTF-8 parsing, a 128 KB read bound, strict symbol validation, loopback/origin checks, capability revocation and private event redaction are enforced.

## Verification

- The new tests inspect actual project modules, functions, classes and methods; test malicious paths, missing/invalid symbols, links, oversized files and syntax errors; and confirm that top-level source code is not run.
- HTTP, text and simulated voice-transcript routes use the same tool. A revoked tool is denied, and the shared event bus receives a redacted result instead of code-inspection details.
- Focused regression: **201 Python passed** and **99 Node/JavaScript passed**. The Python run reported one existing `google.generativeai` deprecation warning; this module does not use that provider. This is a focused suite, not a whole-repository certification.
- Live dashboard: Capability Center showed `coding.explain` as Available, inspected `processes()` in the actual project, displayed `zohra/services/tool_execution/catalog.py:157-174` and a verified activity event. At a 390 px mobile viewport, the page and code panel had no horizontal overflow. [Screenshot](../scratch/zohra-code-inspection-20261002.png).
- The protected baseline of 219 trading/face files matched exactly after this increment. No brightness hardware read or change, trade, code execution, source upload, or new paid API call was made.

## Still Open

This is **partial** Code Explanation Engine coverage. JavaScript/TypeScript/C++/Kotlin parsing, semantic algorithm or execution-flow explanation, diagnostics, source search across unknown files, patching and test generation are not delivered here. Source metadata is not a proof that a function behaves correctly at runtime. Android, external-account and other roadmap blockers remain unchanged. Brightness and trading engine files were not changed.
