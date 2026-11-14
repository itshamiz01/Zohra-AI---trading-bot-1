# Zohra Local Documents: Implementation and Validation

Date: 2026-09-27. Workspace: `C:/Users/dell/Desktop/trading_bot`.

This is an incremental delivery of the universal upgrade, not completion of the master roadmap. Brightness was left aside as requested: no brightness hardware read, write or reset was performed in this increment. Trading, broker, strategy, risk and original molecular-face files were not modified.

## What Was Missing and What Changed

The assistant had confirmed text-note creation but no registered, verified PDF/Word/Excel creation path. The new `documents.create` capability produces real local files from supplied content through the existing Node confirmation bridge. It is available in the existing Capability Center and shared conversation routing, without replacing the frontend, providers, voice or architecture.

- PDF: A4 text documents with escaped markup, wrapping and parser read-back.
- Word: DOCX paragraphs and optional title, preserving supplied Unicode text, including Hindi.
- Excel: new XLSX workbooks from rectangular CSV or JSON rows, with typed JSON values, header styling, column widths, frozen header and filters. Strings starting with `=` are literal text, not executable formulas.
- Exact filename, content and format are validated before proposing an action. A separate confirmation is required; a proposal creates no output file.
- Outputs are create-only inside `assistant_workspace/files/documents`. Existing files cannot be overwritten. Unsafe names, path escapes, links and hardlinks are denied.
- Confirmation is session-bound, expiring, single-use and rechecked against capability revocation. A caller-supplied approval boolean cannot execute a write.
- Completion requires byte and format-specific read-back verification. Artifact metadata and SHA-256 hashes persist in the existing assistant database.
- File listing and downloads require the originating conversation session. Downloads recheck size, path and hash; changed files are refused. There is no automatic upload.
- A heavy chat/provider import was removed from the fixed document subprocess by extracting the existing redaction helpers into `security/redaction.py`; their existing behavior remains covered by regression tests.
- Dashboard polling preserves the document draft and does not steal focus while the form is being edited. Local Lucide icons avoid a new external icon dependency.

Example explicit request: `create PDF "report.pdf" with Approved report text.` Incomplete requests ask for context. This is document creation from supplied content, not an arbitrary research/planning agent or a format-conversion service.

## File-Level Integration

| Files | Responsibility |
|---|---|
| `zohra/services/productivity/documents.py` | Strict inputs, builders, confirmation claims, read-back, artifact persistence and safe downloads |
| `zohra/services/productivity/documents_cli.py` | Fixed JSON prepare/execute subprocess; no arbitrary shell commands |
| `assistant_runtime/router.mjs`, `runtime.mjs`, `gate.mjs`, `tool-ids.json` | Shared intent routing and immutable separate approval for `export_document` |
| `zohra/services/tool_execution/catalog.py` | Register `documents.create`, dependencies and proposal-only execution boundary |
| `zohra/services/chat/assistant_orchestrator.py` | Capability preflight, session locking, private conversation history and redacted activity |
| `zohra/api/assistant_router.py` | Guarded proposal, artifact listing and verified downloads |
| `zohra/api/static/workspaces.js`, `dashboard.html`, `static/icons/` | Existing Capability Center form, pending confirmation, results and download links |
| `zohra/security/redaction.py`, `services/chat/assistant_tools.py` | Lightweight shared redaction, preserving existing helper imports |
| Root `requirements.txt` | Free local document dependencies; no provider or paid service added |
| `zohra/tests/test_documents.py`, `assistant_runtime/tests/documents.test.mjs` | Actual file, schema, permission, confirmation, download and shared-routing tests |

The registry now contains **66 declared contracts**, including explicitly unavailable capabilities with no execution handler. A contract count is not a completed-feature count.

## Frontend to Backend Map

| Surface | Backend source | Verified behavior |
|---|---|---|
| Capability Center inventory | `GET /api/v1/assistant/capabilities` | Real capability/dependency/permission state; `documents.create` is registered |
| Document form | `POST /api/v1/assistant/documents` | Validate exact document arguments and return a pending approval; no premature write |
| Shared Confirm / Cancel controls | `POST /api/v1/assistant/confirm` | Existing single-use Node gate executes or cancels the exact proposal |
| Created-file list | `GET /api/v1/assistant/documents?session_id=...` | Persisted verified artifacts for this session, retained after reload |
| File download links | `GET /api/v1/assistant/documents/{artifact_id}?session_id=...` | Confined, session-bound, hash-verified attachment download |
| Command Center text | `POST /api/v1/assistant/message` | Explicit creation commands enter the same registry and confirmation gate |
| Voice transcript handling | Existing `voice_events` through `/api/v1/voice/stream` | Same routing and approval in transcript tests; live microphone acceptance not certified here |
| Activity timeline | `GET /api/v1/assistant/activity` | Pending, canceled, verified success and actual errors; measured durations |

This map certifies the added document paths, not every legacy tab or every requested OS/device action. The broader tab map and explicit remaining statuses are in the foundation report and integration matrix.

## Automated Evidence

**275 distinct focused checks passed: 179 Python + 96 Node/JavaScript.** This is not the entire repository suite or a security penetration audit. Follow-up reruns are not added to that total.

```powershell
python -m pytest zohra/tests/test_documents.py zohra/tests/test_tool_foundation.py zohra/tests/test_assistant_orchestrator.py zohra/tests/test_assistant_conversation.py zohra/tests/test_assistant_search.py zohra/tests/test_portrait_commands.py zohra/tests/test_voice_v6.py zohra/tests/test_architecture_v2.py zohra/tests/test_windows_v8.py zohra/tests/test_framework_v5.py -q -p no:cacheprovider --basetemp scratch/.pytest-document-regressions
# 179 passed, 2 warnings, 259.18 seconds

node --test assistant_runtime/tests/runtime.test.mjs assistant_runtime/tests/documents.test.mjs assistant_runtime/tests/writer.test.mjs zohra/tests/test_face_effects.cjs zohra/tests/test_face_speech.cjs zohra/tests/test_portrait_capture.cjs
# 96 passed, 0 failed, 4.284 seconds on the final run
```

The first document test run found two failures: JSON objects could fall through to CSV parsing, and a generic executor test lacked the required configured document permission. JSON validation was fixed; the test was corrected without weakening permissions. Later numeric bounds were hardened to reject unsafe/oversized spreadsheet numbers without overflow.

After the redaction extraction, 114 focused Python checks passed again. The final document-only run passed all 33 checks after the numeric validation adjustment. Existing Google Generative AI and Redis deprecation warnings remain; no provider migration is claimed.

Coverage includes actual three-format generation, parser read-back, literal formula protection, Hindi Word content, explicit unsupported PDF text errors, no-write previews, cancellation, expiry/replay/wrong-session/modified-argument/revocation rejection, path/link controls, download ownership/tampering, origin checks and shared voice-transcript confirmation. Mocked speech is not real microphone/STT validation.

## Actual Dashboard and Artifact Checks

- Created `zohra-ui-documents-20260927.pdf` through the form: output absent before the separate Confirm button, then verified as 2,000 bytes and one page.
- Created `zohra-ui-documents-20260927.docx`: 36,870 bytes; English and Hindi paragraph read-back matched approved text.
- Created `zohra-ui-documents-20260927.xlsx`: 5,277 bytes, four rows and three columns; number `42`, boolean `true` and literal `=1+2` survived workbook read-back.
- Reload retained the same session and all three file links. No approval remained pending at the end.
- Clicked the actual PDF download link. Downloaded and stored files had the same SHA-256: `898F57152E6BE5FC0DEC37291FEFABEB322E94EB86BF19514D3B71D71E52D8E1`.
- Desktop 1280x720 and mobile 390x844 were inspected. Document width matched each viewport, with no horizontal overflow; controls remained inside the mobile viewport. The editor retained focus through activity polling.
- PDF rendered to a page image and was visually inspected: readable title/body, wrapping, margins and escaped markup. XLSX was imported and rendered for visual inspection; values and formulas were separately verified with openpyxl.
- DOCX page rendering could not run because LibreOffice `soffice.exe` is absent from the bundled renderer environment. Paragraph/content verification passed, but Word page layout is **not visually certified**.

Real outputs are under `assistant_workspace/files/documents/`. UI evidence: `scratch/zohra-documents-desktop.png`, `scratch/zohra-documents-mobile.png`. PDF/Excel visual checks: `scratch/zohra-document-pdf-page-1.png`, `scratch/zohra-document-excel.png`.

Observed activity durations after removing the heavy import: Word proposal 3,051.52ms / confirmed execution 4,623.2ms; Excel proposal 4,356.68ms / confirmed execution 6,115.81ms. These are individual observations, not averages, a guaranteed latency target or STT benchmarks.

## Limitations and Next Work

- PDF currently supports Western/cp1252 text. Unsupported scripts fail explicitly; use Word for Hindi. Complex-script PDF shaping/font integration is unfinished.
- New workbooks only: existing-workbook edits, backups/rollback, formulas, charts and broader spreadsheet assistance remain unfinished.
- PDF extraction, OCR, conversions, source-grounded research synthesis and email attachment/send workflows are separate unfinished capabilities. Creating an export does not complete those workflows.
- Full writer acceptance still needs approved actual manuscripts and the configured provider. Live voice, strong authentication, OAuth accounts, persistent schedules, Android and cross-device pairing remain unverified or blocked as detailed in the matrix.
- Session-bound local downloads are not Windows Hello or secure remote device authentication. No public remote command service was exposed.
- No microphone/camera permission, private upload, external send, trading execution, brightness operation, shutdown or cleanup deletion was performed in this increment.

Protected-file SHA-256 comparison: **219 checked, zero changed**. No unrelated dirty work was reverted or committed.

Safe preview: `http://127.0.0.1:8011/dashboard`, loopback only, background services and MT5 connections disabled. It is not the production trading launcher.

See [architecture](zohra-universal-architecture.md), [feature matrix](zohra-integration-matrix.md) and [historical foundation validation](zohra-foundation-validation.md). The complete master roadmap remains in progress.
