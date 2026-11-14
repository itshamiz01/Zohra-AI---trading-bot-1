# Zohra Verified PDF Inspection

Date: 2026-10-02. This is a narrow continuation of the universal upgrade, not completion of the whole PDF extraction agent or master roadmap. Brightness and protected trading/face files were left untouched.

## Delivered

- `document.pdf` is now an executable, read-only registry capability using local `pypdf`. It is restricted to PDFs already created and verified by Zohra in the same conversation. It does not accept an arbitrary filesystem path or upload a document to a model/cloud service.
- The existing Capability Center lists the new tool, shows a Read button beside each verified PDF, displays extracted page text, navigates by page and searches across the document with page-numbered snippets.
- Explicit text commands such as `read PDF "report.pdf" page 2` and `search PDF "report.pdf" for nebula` route through the same registered read-only capability. The existing voice-transcript path uses that text router; this is not a claim of live microphone/STT validation.
- Inputs are strict and bounded. Reads recheck the existing session-bound artifact record, safe path, regular-file status, byte count and SHA-256. Revoked capability, foreign session, missing page, changed file and invalid filename fail instead of returning content.
- Extracted output is bounded: first three pages for an unqualified read, 4,000 characters per displayed page, or one requested page; searches report a total match count and at most ten snippets. Scanned/image-only pages are identified as having no selectable text; OCR is not implemented.
- The tool contract marks extracted text private. The caller receives the result, but generic agent-task event subscribers receive a redacted result instead of document text.
- The Capability Center no longer replaces confirmation controls during its periodic refresh while an approval is pending. This was found during browser verification.
- Disabling `document.pdf` also removes previously displayed extracted text from the active panel; it cannot keep showing a stale private result.

## Wiring

| Frontend / command | Backend source | Actual behavior |
|---|---|---|
| Capability Center Read / page / Find in PDF | `GET /api/v1/assistant/pdf/inspect` | Session-bound local extraction or search, returned with page references |
| Capability Center inventory | `GET /api/v1/assistant/capabilities` | `document.pdf` availability, strict input contract, permission and revocation state |
| Command Center text | `POST /api/v1/assistant/message` -> Node classifier -> Python ToolExecutor | Exact filename/page or search request; no write confirmation needed for read-only inspection |
| Existing voice-transcript router | `voice_events` -> the same text request | Same read-only permission and result; live speech recognition not re-certified |
| Activity timeline | `GET /api/v1/assistant/activity` | Actual read successes/failures and measured durations |
| Original PDF download | Existing `GET /api/v1/assistant/documents/{artifact_id}` | Unchanged hash-verified download |

Implementation: `zohra/services/productivity/documents.py`, `zohra/services/tool_execution/catalog.py`, `zohra/services/chat/assistant_orchestrator.py`, `zohra/api/assistant_router.py`, `zohra/api/static/workspaces.js`, `zohra/api/dashboard.html`, `assistant_runtime/router.mjs`, `assistant_runtime/tool-ids.json`. Regression cases are in `zohra/tests/test_documents.py` and `assistant_runtime/tests/documents.test.mjs`.

## Evidence

**280 distinct focused checks passed on the final code: 183 Python + 97 Node/JavaScript.** This is not the entire repository suite or a penetration audit. The Python run reported one pre-existing deprecated Google client warning. Earlier partial reruns are not added to the total.

```powershell
python -m pytest zohra/tests/test_documents.py zohra/tests/test_tool_foundation.py zohra/tests/test_assistant_orchestrator.py zohra/tests/test_assistant_conversation.py zohra/tests/test_assistant_search.py zohra/tests/test_portrait_commands.py zohra/tests/test_voice_v6.py zohra/tests/test_architecture_v2.py zohra/tests/test_windows_v8.py zohra/tests/test_framework_v5.py -q -p no:cacheprovider --basetemp scratch/.pytest-pdf-private-final
# 183 passed, 1 warning, 257.60 seconds

node --test assistant_runtime/tests/runtime.test.mjs assistant_runtime/tests/documents.test.mjs assistant_runtime/tests/writer.test.mjs zohra/tests/test_face_effects.cjs zohra/tests/test_face_speech.cjs zohra/tests/test_portrait_capture.cjs
# 97 passed, 0 failed, 5.858 seconds
```

The tests include same-session page extraction, multi-page navigation, search/no-match distinction, validation, foreign-session/tampered-file refusal, capability revocation, private event redaction, local HTTP origin guard, direct text routing and simulated voice-transcript routing. They do not certify a live microphone or Android device.

Actual loopback dashboard check:

1. Proposed a new local PDF with exact content. It remained pending until separate confirmation.
2. Confirmed it. `pdf-inspection-20261002.pdf` was created and listed as a verified 1,695-byte artifact.
3. Clicked Read: title and both supplied lines appeared under **Page 1**. Activity marked `document.pdf` success and verified.
4. Searched for `nebula`: **1 match** with Page 1 snippet. The panel fit the 870px browser viewport without horizontal overflow (`scrollWidth=870`).
5. The read activity took 922.4ms and the search 74.96ms in that session. These are individual observed durations, not latency guarantees.
6. After the final server restart, the same saved PDF read and search succeeded again. The observed search was 83.52ms. The current dashboard uses the final code, not the earlier preview process.

At a 390px mobile viewport, the document width was 390px and the inspection panel 322.4px, with the match visible and no horizontal overflow. The temporary viewport override was reset.

Protected-file SHA-256 comparison: **219 checked, zero changed**, including the trading modules and original molecular face. No trades, brightness hardware operations, private uploads or external sends were performed.

Screenshots: `scratch/zohra-pdf-inspection-final-20261002.png`, `scratch/zohra-pdf-inspection-mobile-20261002.png`. The preview is bound to `127.0.0.1:8011` with background tasks disabled and paper mode; no MT5 trading was started.

## Still Outstanding

Reading an existing arbitrary user PDF, scanned-PDF OCR, table extraction, all-page export, semantic summarization and robust large-PDF indexing remain unfinished. Only previously generated, unmodified, session-owned PDFs are accepted. Loopback plus a conversation identifier is not strong account authentication or secure remote access. The user-requested broader Windows, Android, agent and workflow roadmap is still incomplete.

See the [feature matrix](zohra-integration-matrix.md) and [document creation report](zohra-documents-validation.md).
