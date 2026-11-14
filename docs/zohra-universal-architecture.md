# Zohra Universal Upgrade: Architecture and Integration Assessment

Inspected checkout: `C:/Users/dell/Desktop/trading_bot`, 2026-09-27.
This is a staged implementation report, not a claim that the entire master brief is complete.

## 1. Existing architecture

- **Backend:** Python FastAPI, `zohra/api/app.py`, modular REST routers, voice WebSocket, optional service loading. The supplied Node-only V12 description does not match this checkout; no migration is justified.
- **Frontend:** existing `dashboard.html`, vanilla `static/workspaces.js`, Three.js particle portrait, face-effects/speech helpers. No React replacement is needed. The original face geometry and design remain unchanged.
- **Assistant:** `services/chat/assistant_orchestrator.py` calls the existing Node 24 JSON-stdin bridge. Four text lanes, durable single-use confirmations, approved file creation, to-dos, Notepad/Calculator and public-browser dispatch already exist. General conversation uses existing configured provider adapters, not a new paid subscription.
- **Voice:** one existing browser microphone pipeline, voice WebSocket, configured STT, Windows female SAPI output, progressive sentence playback, interruption handling and sound/portrait commands. It is turn-based, not a verified full-duplex live service. Local faster-whisper and edge-tts packages are installed; their presence does not prove model/provider readiness.
- **Trading:** Python engines, brokers, strategies, HIE/intelligence, account telemetry and risk gateways. Assistant reads existing snapshots only. Risk health is not certified by this upgrade. No trading engine, strategy, broker or risk-control file is changed.
- **Storage:** existing trading SQLite/PostgreSQL adapters, assistant message SQLite, Node `assistant_workspace/assistant-runtime.db`, lifecycle memory and optional vector stores. Existing databases are retained. New controls/history are additive tables in the existing Node database; passwords and tokens do not belong there.
- **Tools:** a Python `ToolRegistry` and `ToolExecutionEngine` already existed, but only stored handlers, trusted caller-supplied policy fields, and could report simulated handlers as completed. The upgrade extends these classes rather than introducing another executor service.
- **Automation:** two existing workflow implementations, an in-memory scheduler, an approval queue and a Windows helper collection. Several helpers are placeholders. Existing workflow report writing is not uniformly confirmed. These are not certified as secure universal automation.
- **Agents/plugins:** existing framework with DAGs, agent messages, resource locks and specialist classes. Some research/MCP/browser paths are simulated. Plugin loading can execute local code; it is not a sandbox or an authenticated remote plugin boundary.
- **Vision:** mss/PIL capture, OCR, OpenCV camera and chart-pixel helpers exist. OCR/vision dependency availability varies. The capture API is not yet an authorized universal screen agent, and screenshot privacy must be addressed before cloud vision.
- **Android/cross-device:** no Android manifest, Gradle project or Kotlin application found. No registered-device pairing, authenticated command transport or verified file transfer found.
- **Authentication:** new assistant endpoints are local-loopback/same-origin only. This is not Windows Hello, vault cryptographic authentication or remote device pairing. High-risk tools remain blocked. Legacy endpoint security is not globally certified by these checks.
- **Native controls:** subsequent native master-audio/WMI adapters extend the existing bridge with device-bound previews and read-back. Application audio/output switching remains unfinished. Brightness is deferred at the user's request and was not read, changed or reset in the document increment.
- **Documents:** independent local PDF/DOCX/XLSX builders use the same separate confirmation gate. Outputs are create-only, parser-verified, persisted in the existing assistant database and exposed through confined session-bound downloads. A later read-only `document.pdf` adapter extracts pages and searches only those verified, same-session PDFs. No arbitrary PDF ingestion, OCR, research synthesis, existing-workbook editing or general conversion completion is implied.
- **Developer reading:** `coding.explain` adds bounded, local Python AST inspection of an explicitly named project file or symbol. It returns source line references without executing code or uploading private source. Multi-language parsing and semantic code explanations remain unfinished.

## 2. Existing / missing feature inventory

See [integration matrix](zohra-integration-matrix.md), [historical foundation report](zohra-foundation-validation.md), [document creation validation](zohra-documents-validation.md), [PDF inspection validation](zohra-pdf-inspection-validation.md) and [code inspection validation](zohra-code-inspection-validation.md). They cover every named capability group, actual tests and tab wiring, including unsupported Android and external-account features. Declarative unsupported registry entries have **no execution handler**; they are visible blockers, not fake implementations. The current catalog declares 66 contracts; availability, not the count, determines what can execute.

Working pieces to reuse: dashboard/avatar, STT/TTS, conversational provider adapters, public search with real snippets, timestamped backend read models, assistant persistence, Node immutable confirmation gate, Python registry/event bus, agent framework, psutil telemetry, existing document parsers when dependencies are present.

Missing foundations: strong authenticated sessions for high-risk actions, broader native controls, scoped filesystem mutations beyond new notes/documents, persistent authorized scheduling, credential storage/OAuth, constrained script execution, complete workflow cancellation/resume, real-device Android implementation and pairing.

## 3. Proposed modular architecture

```text
Existing dashboard / existing voice WebSocket
    -> existing assistant routing + shared persona
    -> server-owned capability contracts and permission checks
    -> existing confirmation bridge for state changes
    -> Python ToolExecutor / registered device adapter
    -> actual service result -> verification -> redacted audit -> UI

Future Android agent
    -> authenticated pairing and encrypted transport
    -> device-local permission checks
    -> the same capability contracts, never arbitrary remote shell
```

The registry, not an LLM or a speaker name, determines input types, platform, dependencies, risk, timeout and availability. The confirmation bridge retains exact approved arguments, expiry, session binding and one-time execution. Disabled capabilities are checked again before execution; pending approvals for revoked write tools are invalidated. Mandatory security controls cannot be disabled through tool commands.

The Python executor cannot execute an unverified legacy handler. State-changing Python handlers without a trusted proposal-only bridge remain pending, regardless of caller flags. No simulated UAC approval or fail-open elevation fallback is accepted. A bridge handler may create an approval preview only; completion must come from the separate confirmation gate.

Private `document.pdf` output is returned to the requesting conversation but redacted from the shared agent-task event payload. Its source remains confined to the existing session-bound, hash-verified artifact store; text is not forwarded to a provider for extraction/search.

`coding.explain` uses the same private-event boundary. It reads only explicit, bounded `zohra/` Python paths, checks canonical containment and links, and reports static structural facts with line references. It does not import, run, edit or upload project code.

Independent monitoring reads are local and do not upload process/network data to a language model. Read snapshots are not guarantees about future state. Dispatching an app/browser request is not proof that its UI loaded successfully.

## 4. File-level integration plan

| Files | Integration |
|---|---|
| `services/tool_execution/registry.py` | Server-owned contracts, strict schemas, capability states, existing registry interface |
| `services/tool_execution/engine.py` | Preserve public executor API; enforce contracts, risk, timeouts, output validation and verification; block unverified/elevation paths |
| `services/tool_execution/state.py` | Existing workspace database: tool controls and redacted execution history |
| `services/tool_execution/catalog.py` | Adapt working backend/search/Node services; native process/network readers; enumerate explicit unsupported capabilities |
| `assistant_runtime/tool-ids.json` | Shared stable IDs for Python/Node adapters; no credentials or executable model instructions |
| `assistant_runtime/gate.mjs` | Confirmed capability controls, pending revocation, final policy check, file/task read-back verification |
| `assistant_runtime/router.mjs` | Capability/process/network requests and explicit enable/disable commands |
| `services/chat/assistant_orchestrator.py` | Registry preflight, preserved routing/confirmation, local monitoring answers, execution measurements/history |
| `services/chat/assistant_tools.py` | Reasoning/voice registry discovery and permission checks; retain existing read tools |
| `api/assistant_router.py` | Local capability inventory, confirmed controls, execution history; reject remote peers |
| `api/dashboard.html`, `static/workspaces.js` | Existing nav extended with Capability Center, availability/filtering/contracts, confirmation controls and activity polling |
| `tests/test_tool_foundation.py`, runtime tests | Contract, deny/revoke, actual monitoring, errors, confirmation and interface regressions |
| `services/productivity/documents.py`, `documents_cli.py` | Strict local PDF/Word/Excel creation, exact approval claims, parser read-back and hash-verified artifact downloads |
| `security/redaction.py`, `services/chat/assistant_tools.py` | Lightweight shared redaction helpers; avoid loading the chat/provider stack in fixed document subprocesses |
| `api/assistant_router.py`, `static/workspaces.js` | `/documents` proposal/list/download routes and existing Capability Center form/results, using shared `/confirm` |
| `tests/test_documents.py`, `assistant_runtime/tests/documents.test.mjs` | Actual three-format files, no-write proposals, confirmation/replay/revocation, ownership/tampering and shared transcript routing |

Future integration points: extend native adapters under `services/automation`, authorized capture under `services/vision`, extraction/conversion/email adapters under independent productivity modules, persistent job adapters around existing workflows, and a separate `android/` project only after pairing contracts are defined. Protected trading modules are read-only dependencies. Document claims and artifact records are additive tables in the existing `assistant-runtime.db`, not a new database service.

## 5. Dependencies and permissions

Installed probes: FastAPI, Pydantic, psutil, OpenCV, mss, Pillow, PyAutoGUI, pywin32, pycaw, cryptography, faster-whisper, edge-tts, python-docx, ddgs, Playwright and MediaPipe. Node and VS Code executables are present.

The document increment installed free local reportlab, pypdf and openpyxl into the existing project Python; python-docx was already present. Root requirements declare these dependencies. Installed document libraries are not proof of complete extraction, editing or conversion tools.

Missing probes remain: Argon2, APScheduler, PyMuPDF, Java, Gradle, adb, Tesseract and LibreOffice executables. DOCX paragraph verification passed, but page rendering is blocked by missing LibreOffice in the bundled QA environment. PDF complex-script shaping is not integrated; unsupported text fails explicitly rather than producing corrupt Hindi glyphs. No new paid service is introduced. Writer still needs the actual approved books plus Anthropic key/model and live acceptance validation.

Current permissions: local read observations; action-specific confirmation for notes/documents/tasks/app/browser/native controls and capability changes; no unrestricted shell, no trade writes, no elevation, no vault unlock, no external message sending, no remote control. Voice/gesture identity alone never grants high-risk access. Device/account permissions will need independent enrollment and revocation. Brightness remains outside the current work.

## 6. Implementation sequence

1. Foundation: extend registry/executor, block unsafe legacy paths, preserve the confirmation gate, expose real availability/history, run unit/HTTP/UI regressions.
2. Windows: extend master-audio controls and read-only Defender/network diagnostics; then approved process/cleanup previews and cancelable power controls. Brightness is deferred. Vault requires cryptographic authentication before import/export.
3. Productivity/development: approved new PDF/Word/Excel creation is delivered; next extend scoped extraction/backups, sourced reports, OAuth drafts and constrained coding workspace. Sends and arbitrary scripts remain separately authorized.
4. Intelligence/workflows: source-grounded reports, persisted dependencies/cancel/resume, verified step results, scheduling that cannot bypass authorization.
5. Multimodal: reuse current face/audio loop; authorized screen/camera/gesture adapters, benchmark actual latency and CPU. Do not replace the face.
6. Android: Kotlin app, Keystore identity, supported permission/foreground-service/CameraX APIs; actual device validation required.
7. Cross-device: authenticated pairing, encrypted transport, scoped routing, local enforcement, receipt verification, revocation.
8. Full validation: security/performance/real-device workflows A-G. Report partial and blocked results honestly.

## Assessment limitations

Repository structure, relevant integration files and capability implementations were inspected. This is **not** a completed line-by-line audit of every legacy/trading file, nor a complete security review. Trading source remains protected. Synthetic writer/provider/launcher tests are not live author-book, account or Android-device acceptance. Unsupported hardware, missing accounts and missing toolchains remain explicit blockers.

Validation practices follow the existing Pydantic API and [strict validation documentation](https://docs.pydantic.dev/latest/concepts/strict_mode/). SQLite connections are explicitly closed; transactions alone do not close connections, as documented by [Python sqlite3](https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager).
