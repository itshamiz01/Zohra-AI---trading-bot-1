# Zohra Assistant Upgrade Report

Date: 2026-09-27. Project: `C:/Users/dell/Desktop/trading_bot`.

## Fixed / Added

- Added a Node.js routing/action layer around the existing Python dashboard.
  Twenty varied requests across TRADING, WRITING, TASK and CHAT classify correctly.
- Replaced the older HTTP chat paths that could bypass assistant permissions.
  Both dashboard text forms now use the same Node bridge.
- Added explicit, expiring, one-use, conversation-bound Confirm/Cancel proposals.
  File/to-do/app/browser actions cannot execute from the first request. Invalid
  paths, scripts, local/secret browser URLs, replay and risk overrides are denied.
- Added real new-file and to-do persistence, fixed Windows app launchers and a
  default-browser dispatcher. Failures preserve their actual error/status.
- Fixed read-only "open positions" queries being confused with opening a trade.
  Trading/dashboard data comes from local timestamped read models, not invented
  values; the new text layer does not send account observations to an outside LLM.
- Added structured action audits and protected local history: private action,
  Writer and backend turns are excluded from later unrelated model context.
- Built the Writer loader, four separately labeled modes, Anthropic adapter,
  source-line/quote validation and source-change detection. Private manuscript
  API sends require a separate confirmation specifying sources and provider.
- Left the original molecular face, its motion and female speech controls intact.

## Surface Mapping

| Surface / lane | Backend | Status |
| --- | --- | --- |
| Command Center text | `/api/v1/assistant/message` -> Node runtime | Verified |
| Voice tab text | Same endpoint and confirmation gate | Verified |
| Confirm / Cancel | `/api/v1/assistant/confirm` -> SQLite one-use claim | Verified |
| History / pending action | `/api/v1/assistant/history` | Verified |
| TRADING reads | Existing fleet telemetry reader, locally formatted | Verified; snapshots may be stale/unavailable |
| TRADING writes | No verified safe write adapter in this checkout | Blocked |
| TASK reads / public search | Existing dashboard readers / bounded search service | Connected |
| TASK file / to-do / app / browser actions | Node allowlisted executors, after confirmation | Gate/executor tests pass; real file verified in dashboard |
| CHAT | Existing configured conversation provider, safe history only | Real joke reply verified |
| WRITING | Node Writer Agent -> confirmed Anthropic Messages API | Code/contract tests pass; live acceptance pending |
| Existing voice | Existing voice gateway; mutations blocked | Preserved; Phase 3 upgrade not started |

Other dashboard tabs are unchanged by this upgrade. This is not a completed
whole-codebase audit or a claim that all legacy integrations are functional.

## Verification

- 181 focused tests passed: 96 Python + 43 Node runtime/Writer + 42 portrait/UI.
- Real dashboard file request: absent while pending; exact content saved after
  a separate Confirm; reload retained the conversation and consumed the proposal.
- Desktop/mobile layout checked; molecular canvas is visible and moving.
- SHA-256 comparison: all 219 protected trading/risk/face-data files unchanged.
- No trade was placed, no trading process was restarted, and the dashboard
  preview uses background trading and broker connection disabled.
- App/browser launch tests use injected launchers, not actual visible launches.
- Writer model responses in the tests are synthetic. They do not prove live
  continuity detection, prose quality, manuscript grounding or model latency.
- Existing legacy Google-generativeai/Redis warnings remain outside this scope.

## Remaining Gate

Phase 1 acceptance is met. Phase 2 needs the author's actual manuscript and
character-bible folder, plus locally configured `ANTHROPIC_API_KEY` and
`ANTHROPIC_MODEL`. Those are missing here. The Writer currently reports that
prerequisite instead of generating ungrounded book feedback.

Phase 3 must wait for that live Writer acceptance, as requested. Faster-whisper,
edge-tts, spoken confirmation and new full-duplex barge-in are NOT implemented yet.
The trading risk-gap closure described in the brief was not independently
verified here; trading writes remain disabled without changing its risk files.

Configuration and interface details: `assistant_runtime/README.md`.
Preview: `http://127.0.0.1:8011/dashboard`.
