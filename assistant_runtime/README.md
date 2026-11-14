# Zohra Assistant Layer

This Node.js 24+ layer wraps the existing Python/FastAPI dashboard. It does not
replace, import, or edit the trading executor. No npm dependencies are required.
Python invokes a short-lived Node process over JSON stdin/stdout; Node owns the
intent classifier, action permissions, confirmation records, Writer Agent, and
structured SQLite audit. Python supplies existing read-only dashboard readers
and the already-configured conversational/public-search service.

## Phase Status

1. Text routing and confirmation: implemented and exercised with 20 routing
   cases, real file/to-do persistence, raw failures, replay/expiry/session tests,
   HTTP integration, and a dashboard file creation before/after confirmation.
2. Writer Agent: implementation and synthetic contract tests are available.
   Live acceptance is NOT met: the author's manuscripts, character bibles,
   Anthropic key, and model have not been supplied/configured in this checkout.
   Synthetic provider responses do not prove a real model detects continuity
   contradictions or produces useful edits for the author's books.
3. Voice upgrade: NOT started. Existing female speech/portrait controls remain;
   legacy task writes are blocked and task listing reads the confirmed task store.
   The new faster-whisper/edge-tts pipeline, shared spoken confirmation and
   full-duplex barge-in must wait until Phase 2 acceptance is demonstrated.

## Confirmation Contract

All assistant file writes, task mutations, app/browser launches and private
manuscript API sends produce `pending_confirmation`. Each proposal states the
exact action, destination/source lines where relevant, and consequences. A
separate Confirm/Cancel click or whole typed `confirm`/`yes` resolves it.

- Bound to one conversation and an immutable action plan; expires after five minutes.
- A new unrelated request supersedes the old proposal. History reads do not.
- Atomically claimed before execution; concurrent confirmation/replay is denied.
- An interrupted execution is never automatically replayed. A missing response
  may mean its outcome is unknown; inspect history/output instead of assuming it
  did not run. App/browser dispatch is not proof a webpage loaded or an app worked.
- No model tool call can grant a permission or confirm its own proposal.
- A third risk-override request does not bypass anything. The draft's contradictory
  third-override exception is intentionally not implemented.
- The older HTTP chat routes use this same bridge. The legacy speech connection
  cannot mutate tasks, files, the OS or the trading engine.

Allowed actions: new `.txt`/`.md` files inside `assistant_workspace/files`, own
SQLite to-do creation/completion, fixed Notepad/Calculator launch, public HTTP(S)
default-browser launch, and grounded Anthropic Writer requests. Existing files
are never overwritten. Absolute paths, traversal, Windows device names, links,
junctions, arbitrary scripts/commands and secret-bearing/local browser URLs fail.
These are to-dos, not scheduled reminders or autonomous execution.

Read-only account/dashboard queries are locally formatted, timestamped and retain
stale/unavailable fields. Their private observations are not sent to an external
LLM by the new text layer. Ordinary chat/public search reuse the existing provider;
private action/Writer history and older unclassified history remain local and are
excluded from that unrelated provider's conversation context.
public search returns snippets, not full-page verification. No new OpenAI account,
billing or ChatGPT-subscription integration was added.

## Writer Configuration

Configure `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and `ZOHRA_WRITER_ROOT` in the
project's existing `.env` or process environment, then restart the dashboard.
Keep the key local. Choose a model available in your Anthropic account; there is
no invented default, automatic model switch, or unapproved paid retry.

The source root should contain ONE book. Supported sources are UTF-8 `.txt` and
`.md`; character files belong in `characters/` or have `bible` in their filename.
Other formats require an explicit text import before use. For multiple chapters,
name the source filename in the request. Never point this root at a broad personal
folder, a credentials folder, or the entire desktop.

Writer modes have different enforced structures:

| Mode | Output |
| --- | --- |
| LINE EDIT | Original quotation, replacement, specific reason, source lines |
| DEVELOPMENTAL FEEDBACK | Named structural/pacing/character aspect, assessment, quoted evidence |
| CONTINUITY CHECK | Contradiction/consistent/uncertain, explanation and evidence; contradictions require bible AND manuscript citations |
| DRAFT | New passage and explicit grounding; no automatic manuscript write |

The loader selects bounded, line-numbered excerpts by request and chapter terms.
It does not read the entire book into every model call and cannot promise an
exhaustive full-book continuity review. The model must state uncertainty when
context is insufficient. Source hashes are rechecked after confirmation. Invalid
JSON, mixed modes, invented quotations, missing evidence and truncated output
fail rather than appearing as successful feedback.

The provider adapter calls the official
[Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create).
Only the confirmed source plan and writing request are sent. No executable tools
are supplied to the Writer model. A call is capped at 2,200 output tokens with a
25-second request timeout. Real HTTP/provider errors are surfaced and audited.
The confirmation database contains private pending source excerpts and must stay
local; `assistant_workspace/` is ignored by Git.

## API Mapping

| Frontend action | Backend |
| --- | --- |
| Command Center typed conversation | POST `/api/v1/assistant/message` -> Node classifier/gate |
| Voice tab typed conversation | Same POST endpoint; no microphone needed |
| Confirm / Cancel | POST `/api/v1/assistant/confirm` -> session-bound Node gate |
| Reload conversation / pending action | GET `/api/v1/assistant/history` |
| Writer source inventory | GET `/api/v1/assistant/writer/sources` -> approved local text metadata |
| Available capabilities / phase | GET `/api/v1/assistant/capabilities` |
| Legacy HTTP conversation / stream | `/api/v1/chat/message`, `/api/v1/chat/stream` -> same Node bridge |
| Trading status | Existing timestamped fleet telemetry reader, read-only |
| System / memory / research / learning / agents | Existing dashboard read models, no executor |
| Public search | Existing bounded public-search service, with sources |
| Existing spoken conversation | Existing voice gateway, read-only until Phase 3 |

The rest of the dashboard tabs are unchanged by this upgrade. This is not a claim
that the entire legacy repository has been audited or every integration works.

## Outstanding Acceptance

- Author supplies actual chapter and bible paths and locally configures Anthropic.
- Validate a real continuity contradiction, distinct line-edit/developmental
  outputs and genre-matched drafting with those sources and the live model.
- Only then add CPU-only faster-whisper push-to-talk, edge-tts/SAPI fallback,
  shared voice routing/confirmation and measured barge-in/latency tests.
- Trading writes remain disabled until a verified read/write adapter and actual
  risk-control health checks are available. The claim in the supplied brief that
  risk gaps are closed was not independently verified in this Python checkout.
  No trading/risk files are modified to resolve that mismatch.

Tests: `node --test assistant_runtime/tests/*.test.mjs`; the companion FastAPI,
portrait and existing conversation regression suites live in `zohra/tests/`.
Windows app/browser execution is tested with injected launchers; a disposable
file action was additionally exercised through the actual dashboard.
