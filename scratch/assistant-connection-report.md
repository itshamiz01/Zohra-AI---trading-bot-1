# Zohra Conversation Connection

Scope: conversational assistant and the latest dashboard cleanup. This is not a claim that the earlier whole-codebase audit is complete.

## Fixed

- The face click previously played a fixed greeting. Talk now captures real speech and sends it to the conversational assistant; typed messages use the same connection without microphone permission.
- Sound remains separate, for snap/clap and dismissal controls. Hiding the portrait stops conversation playback and Talk, while Sound can remain enabled.
- Conversation IDs now survive reconnection and page reload. Recent messages are stored separately from trading data.
- Broad keyword-based security checks blocked harmless account questions. The new service uses a hard tool allowlist: engine access is read-only, and model output cannot grant financial or operating-system permissions.
- The configured OpenRouter free model returned 404. Only the assistant now falls back to the same provider's free router, without editing shared settings or switching to a paid model. Reference: https://openrouter.ai/openrouter/free
- Outgoing speech is not recaptured as a fresh user request.
- General conversation, questions, and jokes use the same AI as voice and text. Available work gets a spoken acknowledgement before its tool runs, followed by the actual result; unsupported work is not silently sent to legacy trading controls.
- Added real public web/news search through the maintained DDGS library. The previous Wikipedia/mock-fallback agent is not used by this assistant. Results include source links and reported publication/retrieval dates; failures remain explicit. Queries/results are bounded, news recency is checked, and obvious credentials/private contact identifiers are rejected.
- Search sources persist with each assistant reply and appear in an expandable tray in both conversation views. URLs are kept out of female speech. Search excerpts are explicitly distinguished from full-page reading or independent verification.
- Backend observations now use structured secret redaction rather than rewriting serialized JSON, which could previously corrupt observations.
- Another typed message can interrupt an active response. Stop reply cancels playback/reasoning without hiding the face or turning Talk off. Status stays Speaking while audio plays instead of incorrectly displaying Listening.
- Removed the five requested command-center summary boxes. Their sidebar tabs and backend views remain. Conversation is below the portrait on desktop and mobile, not over the face or duplicated in the right sidebar.

## Conversation To Backend Mapping

| Capability | Source |
| --- | --- |
| Speech and typed conversation | `/api/v1/voice/stream`: STT -> AssistantBrain -> existing female TTS and lip analyser |
| Public web/news search | `AssistantBrain -> search_web -> DDGS` public Bing/Brave or Bing/Yahoo search; sources streamed over the same connection and saved in AssistantStore |
| System updates | `get_system_telemetry`, also used by `/api/v1/os/telemetry` |
| Trading/account updates | `get_trading_telemetry`, timestamped fleet snapshots also used by `/api/v1/os/telemetry`; unavailable/stale values remain explicit |
| Research | `research_snapshot`, `/api/v1/research` |
| Memory search | `memory_snapshot`, `/api/v1/memory` |
| Learning | `learning_snapshot`, `/api/v1/learning` |
| Registered agents | `agent_snapshot`, `/api/v1/agents` |
| Personal to-do items | `AssistantStore.manage_tasks`, user-created records in `LOG_DIR/assistant.db`; no seeded demo tasks |

## Verification

- 83 Python tests and 41 Node tests passed (124 total), covering conversation persistence, tool restrictions, task storage, text input, origin/session validation, formation, lips, search privacy/failures, source history, acknowledgement ordering, playback status, stopping replies, and the summary-box removal.
- Real provider tests produced new answers, recalled the test nickname, and called the backend system-update tool.
- A generated spoken request to tell a joke passed through real speech recognition, new AI reasoning, and female voice synthesis. Voice diagnostics selected Microsoft Zira Desktop. This is not a live hardware microphone test.
- Real public search returned official NASA source links, a newly generated female-voice answer, and preserved sources through history reload. Acknowledgement audio was emitted before the search tool executed.
- SHA256 comparison: all 219 protected source/assets unchanged, including trading engines, strategies, brokers, core/configuration code, entrypoints, and original face particle data.
- Preview runs at http://127.0.0.1:8011/dashboard with background workers disabled, standalone MT5 connection off, and paper execution. No trades were placed.

## Limits

This conversation connection does not place or close trades, change risk settings, send payments/emails, control the operating system, or schedule background reminders. Existing verified controls remain unchanged. Saving a to-do is not executing it. The conversation provider still needs network access and available quota. Hardware microphone/snap/clap performance needs a user test; the audio verification used a generated clip, not the user's live microphone.

Voice is turn-based, not full-duplex: speaker output is excluded from capture to prevent echo. Stop reply or a new typed message interrupts it. Public search can be rate-limited, sources are search excerpts rather than fetched full articles, and model summaries can still be mistaken. Free-model routing can affect latency and answer quality. The assistant search dependency is pinned separately in `zohra/services/chat/requirements.txt` (`ddgs==9.16.0`); no existing dependency versions were changed. Library reference: [DDGS repository](https://github.com/deedy5/ddgs).
