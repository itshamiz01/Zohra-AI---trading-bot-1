# Zohra Universal Integration Matrix

Date: 2026-10-02. Scope: actual checkout, not an assumed Node-only V12 system.

**Status meanings:** Complete = the specified narrow capability was executed and checked; Partial = functioning pieces exist but the full requested scope/acceptance is unfinished; Blocked = requires missing credentials, dependencies, enrollment or hardware; Unsupported = not implemented/authorized through this assistant yet. Unsupported registry entries have no execution handler. No live trading or Android-device test was performed.

Evidence codes: **F** = foundation contract/validation/verification tests; **H** = real Node executor through isolated HTTP tests; **N** = Node confirmation/routing tests; **A** = avatar/voice regression tests; **L** = legacy architecture/Windows/framework tests; **D** = local document generation/read-back/approval/download tests. **UI** = actual dashboard verification. Counts and artifact paths are recorded in the [foundation](zohra-foundation-validation.md) and [document](zohra-documents-validation.md) reports. Unit mocks are not real-device evidence. Brightness is deferred at the user's request; no brightness hardware call was performed in the document increment.

## Foundation and Existing Assistant

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Architecture assessment | Shared | Existing architecture inspected; docs added | Repository | Read | Partial | Not Run | Relevant integration paths inspected; not every legacy file line-by-line |
| Registry/contracts | Shared | Extended existing ToolRegistry; `capabilities.list` | Pydantic | Read | Complete | Passed | F,H,N,D; 66 explicit contracts including unavailable blockers; not 66 completed features |
| Deterministic executor | Shared | Existing engine hardened; ToolExecutor alias | asyncio, Pydantic | Registry-owned | Complete | Passed | F,L; unverified handlers, malformed input/output and false verification blocked |
| Confirmation gate | Shared | Existing Node gate extended | Node 24, SQLite | Separate exact action approval | Complete | Passed | H,N; session binding, expiry, replay denial and revoke-before-confirm |
| Capability revocation | Shared | `security.configure` | Existing SQLite | Confirm | Complete | Passed | H,N; persists and invalidates pending tool approvals; cannot disable security gates |
| Activity/results/latency | Shared | Tool events; `/assistant/activity` | Existing SQLite | Local session read | Complete | Passed | F,H; actual measured durations, errors redacted, no raw file content in activity |
| Strong authorization | Windows/Shared | No Windows Hello/passcode/paired-device factor | Enrollment/provider | Strong factor | Blocked | Not Run | Loopback is not strong authentication; high-risk tools blocked |
| General chat | Shared | Existing configured provider; `chat.respond` | Existing LLM account | Read | Partial | Passed | Existing conversation tests; provider configuration/service availability still applies |
| Public search | Web | Existing ddgs; `web.search` | ddgs/network | Public read | Partial | Passed | Real snippets/source links; not comprehensive full-page verification |
| Backend updates | Shared | `backend.system/trading/research/memory/learning/agents` | Existing read models | Read | Complete | Passed | H; timestamped source snapshots, no order or engine start |
| New text note | Shared | `files.create` | Node/filesystem | Confirm | Complete | Passed | H,N; actual .txt/.md read-back, new files only under assistant workspace |
| To-do list | Shared | `tasks.list/create/complete` | Existing SQLite | Writes confirm | Complete | Passed | H,N; real records; not reminders or scheduled automation |
| Notepad/Calculator dispatch | Windows | `windows.launch` | Native Windows/Node | Confirm | Partial | Passed | Injected launcher tests; dispatch is not proof of visible UI opening |
| Browser dispatch | Windows/Web | `browser.open` | Default browser | Confirm | Partial | Passed | Fixed public URL, injected launcher; no DOM/loaded-page verification |
| Writer Agent | Shared | Existing Writer; `writer.review` | Approved books, Anthropic key/model | Private upload confirm | Blocked | Passed | Synthetic grounded contract fixtures; live manuscripts/provider acceptance pending |

## Windows System and Security

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Secure file vault | Windows | Missing; `vault.manage` | AES-GCM, Argon2id | Cryptographic auth + strong factor | Unsupported | Not Run | No authenticated vault/import/recovery; legacy XOR is not a vault |
| Volume/app volume/mute/output | Windows | Native master adapter; `system.audio`, `windows.audio` | Core Audio/pycaw/comtypes | Confirm exact output-bound change | Partial | Passed | Native master volume/mute adapter and read-back integrated; application volume/output switching unfinished; no audio hardware change in document increment |
| Brightness/display controls | Windows | Native WMI adapter; `system.display`, `windows.display` | Native hardware API/pywin32 | Confirm | Blocked | Not Run in this increment | User requested deferral after hardware issues; no brightness read/write/reset in document increment; not certified complete |
| Power manager | Windows | Legacy command helper; `windows.power` | User session/API | Strong confirmation | Unsupported | Passed | F,L deny unsafe execution; countdown/cancel not implemented |
| Defender scanner | Windows | Dispatch helper; `windows.defender` | Defender | Scan authorization | Partial | Not Run | No verified protection/signature/remediation/history pipeline |
| Persistent scheduling | Shared | In-memory scheduler; `automation.schedule` | Persistent scheduler/timezone store | Confirm; each job retains tool policy | Partial | Not Run | APScheduler missing; no durable cron/retry/dependency jobs |
| CPU/RAM/process/uptime monitor | Windows | New native adapter; `system.processes` | Installed psutil | Read | Complete | Passed | F,H,UI; real processes and 100ms system CPU sample; per-process CPU is cumulative time |
| Kill unresponsive process | Windows | Unsafe/unverified legacy path; `windows.terminate` | PID identity/UI state | Action-specific confirmation | Unsupported | Passed | F,L deny unverified calls; no process terminated |
| Network status/local IP/interfaces | Windows | New native adapter; `system.network` | Installed psutil | Read | Complete | Passed | F,H; real interfaces/counters; not public IP or an internet speed test |
| Wi-Fi/latency/speed management | Windows | Legacy helpers; `network.manage` | Native networking/permitted lookup | Writes confirm | Unsupported | Not Run | No scan/connect/disconnect or measured speed test |
| Biometric voice lock | Windows | Profiles/parser; `security.voice` | Verifier, liveness, second factor | Enrollment | Blocked | Passed | Existing voice tests; missing extractor/liveness denies sensitive voice access |
| Safe system cleaner | Windows | Simulated legacy helper; `storage.clean` | Verified preview/storage policy | Confirm approved deletions | Unsupported | Passed | F,L block legacy handlers; fixed savings must not be treated as actual cleanup |

## Screen, Vision and Media

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Screen comprehension/OCR | Windows | Capture/OCR helpers; `vision.screen` | UIA, OCR/model | Explicit screen permission | Partial | Not Run | Universal authorization/semantic UI pipeline missing; OCR engine availability varies |
| Camera vision | Windows | Existing OpenCV helper; `vision.camera` | Camera/model | Visible camera consent | Partial | Not Run | Not integrated as an authorized universal tool; no camera enabled in tests |
| Screenshot manager | Windows | Existing mss/PIL; `vision.screenshot` | Capture library | Private file write confirm | Partial | Not Run | Universal region/monitor/save gate and privacy protections incomplete |
| Spotify | Web/Windows | Missing; `media.spotify` | OAuth/account/API | Playback confirmation | Blocked | Not Run | No connected provider/account |
| Wallpaper | Windows | Simulated helper; `windows.wallpaper` | Native wallpaper API | Confirm | Unsupported | Not Run | No verified setter/restore |
| Cursor/typing/drag/shortcuts | Windows | PyAutoGUI helper; `desktop.input` | UIA/verified target | Action preview/interrupt | Partial | Not Run | Semantic target verification and uniform authorization missing |
| YouTube media/transcripts | Web | Learning agent; `media.youtube` | Authorized browser/transcript | Playback confirm | Partial | Not Run | Not a verified player or full transcript service |
| Notepad writer | Windows | New notes + app dispatch | `files.create`, `windows.launch` | Confirm | Partial | Passed | H,N; actual notes exist; Notepad UI editing/dictation/save workflow not verified |
| Smart scrolling | Windows | Simulated helper; `desktop.scroll` | UIA/intended window | Confirm | Unsupported | Not Run | No verified target/scroll-until-visible |

## Productivity, Conversion and Development

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Research reports/export | Shared/Web | Search + report classes; `research.report`; separate `documents.create` | Sources/document engines | Save confirm | Partial | Passed for export only | D,UI; actual supplied-content exports work; source-grounded synthesis and multistep research workflow unfinished |
| Local PDF creation/download | Shared | New `documents.create` | reportlab/pypdf/Node | Separate exact confirmation | Complete for Western text | Passed | D,UI; actual PDF created, parser read-back, visual page QA and download hash match; complex-script/Hindi PDF explicitly unsupported |
| Local Word creation/download | Shared | New `documents.create` | python-docx/Node | Separate exact confirmation | Partial | Passed | D,UI; actual DOCX and Hindi paragraph read-back; page rendering blocked by missing bundled LibreOffice |
| New Excel workbook/download | Shared | New `documents.create` | openpyxl/Node | Separate exact confirmation | Complete for rectangular CSV/JSON creation | Passed | D,UI; actual XLSX, typed values, literal formula text, read-back and rendered QA; no existing-workbook changes |
| Public scraping | Web | Missing universal adapter; `web.extract` | HTTP parser/browser | Permitted public access | Unsupported | Not Run | Restrictions/pagination/table extraction not integrated |
| Website builder | Shared | Missing; `website.build` | Isolated project/build tools | Approved writes | Unsupported | Not Run | No sandbox/preview/validation pipeline |
| Image generation | Shared | Missing configured adapter; `image.generate` | Local model/GPU or approved provider | Confirm optional paid/upload use | Blocked | Not Run | No installed authorized model/provider |
| PDF extraction | Shared | `document.pdf` reads Zohra-generated, verified, same-session PDFs | pypdf; existing artifact store | Local read with session and revocation checks | Partial | Passed | D,UI; actual page text and page-numbered search, bounded previews, hash checks; arbitrary existing PDFs, OCR, tables, full export/summary unfinished |
| Excel assistant | Shared | New-workbook creation only; `documents.create`; broader `document.excel` unavailable | openpyxl/pandas | Backup + write confirm | Partial | Passed for creation only | D,UI; openpyxl installed; workbook-preserving edits, formulas, charts and backup/rollback unfinished |
| Email drafts/send | Web | Existing class; `email.manage` | Configured OAuth/SMTP | Separate send approval | Blocked | Not Run | No verified connected account/attachments/scheduling pipeline |
| WhatsApp | Web/Mobile | Missing; `whatsapp.manage` | Official or user-mediated account | Send approval | Blocked | Not Run | No private protocol bypass or unsolicited messaging |
| Format conversions/batches | Shared | Missing universal adapter; `document.convert` | Format-specific engines | New output confirm | Unsupported | Not Run | New document creation is not conversion; office conversion/fidelity/batch pipeline missing |
| Coding patches/rollback | Shared | Missing assistant tool; `coding.patch` | Isolated workspace/VCS | Approved patch | Unsupported | Not Run | No production self-modification |
| VS Code integration | Windows | CLI present, tool missing; `coding.vscode` | VS Code | App action confirm | Partial | Not Run | Executable presence is not diagnostics integration |
| Script execution | Shared | Missing constrained tool; `coding.run` | Sandbox/resource limits | Strong approval | Unsupported | Passed | F,N deny arbitrary shell/script actions |
| Source-grounded explanation | Shared | `coding.explain`: local Python AST/module/function/class inspection | Scoped source loader | Local read | Partial | Passed | Actual line references, module hash, revocation and private-event tests; no code execution/upload; other languages and semantic reasoning unfinished |
| Unit-test generation | Shared | Missing assistant adapter; `coding.test` | Scoped test runners | Writes/execution approval | Unsupported | Not Run | Repository tests are run by development tooling, not autonomous Zohra |
| Docs/preferences/compiler config | Shared | Missing; `coding.preferences` | Official docs/workspace store | Writes confirm | Unsupported | Not Run | No per-workspace preference/command registry |

## Intelligence, Agents and Workflows

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Smart form filler | Windows/Web | Missing; `forms.fill` | Semantic fields/authorized data | Preview + submit approval | Unsupported | Not Run | No credential/payment-memory retrieval |
| Shopping comparison/tracking | Web | Search only; `shopping.compare` | Current merchant sources | Read; no purchases | Partial | Not Run | No complete shipping/warranty/price-alert verification |
| Live/video summarization | Shared | Learning parser only; `video.summarize` | Authorized transcript/frames | Media permission | Partial | Not Run | No incremental live pipeline or complete-video guarantee |
| Market information | Shared | Existing trading read snapshots; `market.information` | Timestamped data providers | Read only | Partial | Passed | H; separate `backend.trading` works; broader markets/alerts not integrated |
| Dynamic choices | Shared | Routing/source clarification; `choice.resolve` | Persisted workflow choices | User selection | Partial | Passed | N,Writer fixtures; no universal choice workflow |
| Daily briefings | Shared | Missing; `briefing.daily` | Calendar/email/weather/accounts | Authorized reads/save | Blocked | Not Run | Connected sources missing |
| Master Orchestrator | Shared | Existing four-lane text router | Existing Node/Python | Central policy | Partial | Passed | H,N; not general multistep universal planning |
| Windows System Agent | Windows | Read tools + existing automation agent | Native adapters | Tool policy | Partial | Passed | F,L; unverified actions blocked |
| Android Agent | Android | Missing; `android.agent` | Android app/device | Device-local permissions | Unsupported | Not Run | No app/device |
| Vision Agent | Shared | Existing specialist/helpers | Vision models | Capture consent | Partial | Not Run | Universal tool integration incomplete |
| Research Agent | Web | Existing specialist and real snippet search | Public sources | Read/save policy | Partial | Passed | Search tests, not full-report acceptance |
| Coding Agent | Shared | Missing universal implementation | Isolated source/test tools | Patch approval | Unsupported | Not Run | No unrestricted project changes |
| Productivity Agent | Shared | Writer/tasks/notes/local documents | Accounts/document tools | Action-specific gate | Partial | Passed | H,N,D,UI; actual exports integrated; larger research/email/attachment workflows incomplete |
| Memory Agent | Shared | Existing lifecycle/vector memory | Existing SQLite/optional vector store | Authorized read/write | Partial | Passed | Existing backend read coverage; retention/correction UI incomplete |
| Security Agent | Shared | Deterministic executor/gate | Registry/policy | Enforced outside LLM | Partial | Passed | F,H,N; strong auth/account sessions still blocked |
| Performance Agent | Shared | Native monitor and actual event durations | psutil/event store | Read | Partial | Passed | F,H; no autonomous optimizer or end-to-end voice benchmark |
| DAG/retries/cancel/resume | Shared | Existing workflows; `workflow.manage` | Durable workflow state | Each underlying tool gate | Partial | Passed | L; unsafe retry stopped; persistent cancel/resume/verification unfinished |
| Multi-agent parallel context | Shared | Existing framework/message bus/locks | Agent adapters | Per-tool policy | Partial | Passed | L; isolated framework tests, not all live agents |
| Memory inspection/correction/deletion | Shared | Existing memory views/store | Existing databases | Approved mutations | Partial | Not Run | Universal retention/context isolation UI unfinished |
| Credential isolation/injection defense | Shared | Fixed tool allowlists, schema validation, redacted history | Deterministic boundaries | No model authority | Partial | Passed | F,H,N; not a completed penetration/security audit |

## Avatar, Mobile and Cross-Device

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Avatar expression states | Web | Existing molecular portrait/states | Three.js | Local UI | Partial | Passed | A; richer expression catalog remains unfinished |
| Lip synchronization | Web | Existing bounded audio-amplitude lips | Audio analysis | Playback | Complete | Passed | A; original geometry retained, not photoreal viseme reconstruction |
| Motion/blink/eye tracking | Web | Existing bounded drift/effects | Dedicated render loop | Local UI | Partial | Passed | A; complete expression/head/eye system not implemented |
| Gestures/snap/clap/dismiss | Web | Existing sound/gesture controls | MediaPipe/microphone/camera | Explicit input consent | Partial | Passed | A; low-risk portrait toggles, no high-risk gesture approval |
| Adjustable avatar quality/performance | Web | Existing responsive render loop | Browser GPU | Local UI | Partial | Passed | A; broader device benchmarks/quality presets incomplete |
| Voice multilingual/wake/interruption | Web/Windows | Existing STT/TTS/WebSocket + shared document routing | Configured speech services | Microphone opt-in; writes confirm | Partial | Passed | A,D; voice transcripts use the same document approval gate in tests; actual microphone/STT/barge-in/latency acceptance still outstanding |
| Android anti-theft | Android | Missing | Kotlin/sensors/admin enrollment | Visible enrollment | Unsupported | Not Run | No covert tracking or privileged admin claims |
| Android wake-word service | Android | Missing | Local wake model/foreground permissions | Microphone consent | Unsupported | Not Run | No background-restriction bypass |
| Android live voice/camera | Android | Missing | Supported live API/CameraX | Explicit AV consent | Unsupported | Not Run | No actual device/provider validation |
| Android calls/SMS | Android | Missing | Telecom/contacts/default roles | Explicit permissions/send approval | Unsupported | Not Run | No unrestricted call interception |
| Android WhatsApp | Android | Missing | Supported intents/account | User-mediated sends | Unsupported | Not Run | No private chat collection |
| Android toggles | Android | Missing | Supported native settings APIs | Local permission | Unsupported | Not Run | Restricted actions must use settings panels |
| Android accessibility | Android | Missing | Explicit service enrollment | Deterministic approved navigation | Unsupported | Not Run | No unrestricted accessibility agent |
| Android SOS/GPS | Android | Missing | Contacts/location enrollment | Visible consent/cancel | Unsupported | Not Run | No emergency or covert location action executed |
| Android camera/selfie | Android | Missing | CameraX/device | Visible camera permission | Unsupported | Not Run | No actual device testing/toolchain |
| Secure pairing/identity/revocation | Shared | Missing; `devices.pair` | Keystore/authenticated transport | Strong enrollment | Blocked | Passed | H denies remote spoofed localhost Host; pairing not implemented |
| Cross-device transfer/results | Shared | Missing; `devices.transfer` | Registered devices/encryption | Specific transfer approval | Blocked | Not Run | No device or receipt-verification pipeline |

## Frontend and System Validation

| Feature | Platform | Implementation / Tool ID | Dependencies | Permission | Status | Tests | Evidence / Limitations |
|---|---|---|---|---|---|---|---|
| Preserved dashboard/face/chat | Web | Existing dashboard | Existing assets | Local UI | Complete | Passed | A,UI; greeting/division boxes not restored |
| Capability Center | Web | Existing-nav view extended with documents, PDF and Python source inspection | `/assistant/capabilities`, `/documents`, `/confirm`, `/pdf/inspect`, `/code/inspect` | Local read; writes confirm | Complete for delivered tools | Passed | H,D,UI; truthful states, exact proposals, verified document results and bounded code structure view |
| Activity timeline | Web | New activity panel/polling | `/assistant/activity` | Local session read | Complete | Passed | H,UI; actual pending/cancel/result history |
| Automation Center | Web | Existing workflow view | `/automation` | Underlying action policy | Partial | Not Run | Not a persistent schedule manager or uniform write gate |
| Security Center | Web | Capability controls + loopback boundary | Strong auth future | Permission review | Partial | Passed | H,UI; account/device session management missing |
| Memory Center | Web | Existing memory view | `/memory` | Read | Partial | Not Run | No full correction/deletion/retention UI acceptance |
| Device Center | Web | Missing | Device pairing | Registered identities | Unsupported | Not Run | No Android connectivity |
| Agent Activity Panel | Web | Existing agents view | `/agents` | Read | Partial | Not Run | Does not yet show every requested specialized live agent |
| Lazy loading/resource queues | Shared | Existing async/background pieces | Runtime libraries | Tool policy | Partial | Passed | New monitor is on-demand; complete resource scheduling/camera/audio benchmarks unfinished |
| Controlled improvements/rollback | Shared | Existing dirty Git checkout preserved | VCS/sandbox | Explicit production approval | Partial | Not Run | No self-modification or unauthorized commit performed |
| End-to-end A: maintenance | Windows | Monitor implemented, cleanup blocked | Native monitor + approved cleaner | Read then delete approval | Partial | Passed | F,H monitor only; no cleanup savings fabricated |
| End-to-end B: coding | Shared | Not integrated as assistant workflow | Patch/test sandbox | Approved patch | Unsupported | Not Run | Development tests do not certify autonomous coding |
| End-to-end C: research/PDF | Shared | Search + separate verified local exports | Source synthesis/document engines | Save approval | Partial | Passed for PDF only | D,UI; real supplied-content PDF created/downloaded; full source-grounded research-to-PDF workflow not certified |
| End-to-end D: screen error | Windows | Capture pieces | UIA/OCR/model | Screen consent | Partial | Not Run | Not tested through universal authorized interface |
| End-to-end E: transfer | Shared/Android | Missing devices | Pairing/transport | Specific approval | Blocked | Not Run | No phone/test device |
| End-to-end F: scheduled briefing | Shared | Missing persistent source workflow | Scheduler/accounts | Job policy | Blocked | Not Run | No autonomous jobs created |
| End-to-end G: voice/gesture | Web/Windows | Existing avatar/voice pieces | Audio/camera | Input consent | Partial | Passed | A; no new live spoken financial/state write acceptance |

The full master roadmap is not complete. The verified foundation, real monitoring tools, local document creation, same-session PDF inspection and local Python source inspection are incremental deliveries; remaining entries must meet their own real execution and device/account acceptance before their status changes. This matrix has 108 tracked entries: 16 Complete in their stated narrow scope, 51 Partial, 13 Blocked and 28 Unsupported; **92 remain unfinished**. Latest focused regression evidence: 201 Python + 99 Node/JavaScript checks passed, not the whole repository suite. See the [code inspection validation](zohra-code-inspection-validation.md).
