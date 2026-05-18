# Lexa AI Handoff

This file is the compact entry point for AI agents working in the Lexa repo.

Do not scan the whole repository first. Read this file, identify the task, then use targeted `rg` searches.

## Repo

- Path: `C:\Users\admin\OneDrive\Desktop\lexa\lexa-ai`
- Backend: Python FastAPI in `backend/`
- Frontend: Electron + modular Vanilla JS in `frontend/`
- Tests: `tests/`
- Main backend app: `backend/main.py`
- MCP config: `mcp_servers.json`

## Current Product State

Lexa is already feature-rich:

- chat with Groq, OpenAI, Gemini, and local model support;
- agent loop and tool execution;
- SQLite memory/search;
- MCP registry and client;
- plugins and workflows;
- productivity tools;
- voice, vision/OCR, browser automation, and PC-control foundations;
- Electron UI.

The main work is not adding many new features. The main work is finishing, stabilizing, and making Lexa trustworthy.

## Personal OS Integration

Personal OS lives at:

```text
C:\Users\admin\OneDrive\Desktop\OS
```

Lexa is configured with a `personal_os` MCP server in `mcp_servers.json`.

Personal OS MCP tools currently available when connected:

- `os_read_file`
- `os_read_raw_file`
- `os_write_draft`
- `os_check_task`
- `os_list_drafts`
- `os_view_draft`
- `os_draft_history`
- `os_list_directory`
- `os_query_index`
- `os_graph_index`

Lexa also exposes a narrow endpoint for raw inbox extraction:

```text
POST /personal-os/raw-inbox/extract
```

Implementation:

- `backend/router_personal_os.py`
- registered in `backend/main.py`
- tests in `tests/test_router_personal_os.py`

Lexa now has a Personal OS cockpit in the Electron frontend:

- sidebar view key: `personal-os`
- frontend module: `frontend/src/personal_os.js`
- backend endpoints:
  - `GET /personal-os/status`
  - `GET /personal-os/drafts`
  - `GET /personal-os/drafts/view`
  - `GET /personal-os/drafts/review`
  - `POST /personal-os/drafts/decision`
  - `POST /personal-os/drafts/apply`
  - `GET /personal-os/diagnostics`
  - `GET /personal-os/query`
  - `GET /personal-os/files/read`
  - `GET /personal-os/graph`
  - `GET /personal-os/context-pack`
  - `GET /personal-os/lexa-code-loop`
  - `POST /personal-os/raw-inbox/submit`
  - `GET /personal-os/raw-inbox/status`

`GET /personal-os/status` returns `capabilities` and `missing_tools` for draft queue, review packet, audit history, context browser, graph, and explicit apply.
The cockpit renders these as a compact diagnostic strip with missing-tool hints.
The cockpit status cards use an all-drafts queue read for non-smoke totals, so `Pending`, `Approved`, `Rejected`, and `Invalid` stay accurate even when the visible draft list is filtered.
The backend omits the `approvals` argument for `approval=all`; sending `null` to `os_list_drafts` is invalid MCP input.
`GET /personal-os/diagnostics` returns the cockpit readiness state (`ready`, `attention`, or `blocked`), deterministic checks, all-draft counts, and the underlying MCP status payload.
Diagnostics now include a `system-storage` check based on free space on the Lexa drive. It warns below 1 GiB free and blocks below 100 MiB free, so the cockpit and Chat can surface `ENOSPC` risk before npm/build/log writes fail.
`POST /personal-os/raw-inbox/submit` writes untrusted text to `06_Inbox/Raw/`, then runs the raw-inbox worker in one-shot mode for that file. The worker creates review drafts through MCP/SDK (`os_read_raw_file` and `os_write_draft`); it does not write stable memory.
`GET /personal-os/raw-inbox/status` runs the worker `--status` command without writing OS files. It reports processor availability and raw-inbox failure state for the cockpit preflight.

If the in-memory MCP registry cache is stale and `personal_os` is reported unknown, Personal OS routes reload `mcp_servers.json` and retry the connection once.
If a Personal OS MCP tool call fails because the existing client is stale or disconnected, the router disconnects `personal_os`, reconnects it, and retries the same tool call one time before surfacing the error.
If a cockpit refresh fails anyway, the frontend now renders an explicit offline/blocked diagnostics payload, clears stale draft actions, and shows the MCP error in the queue instead of leaving an old connected status visible. In that offline state, the `NEXT` card prioritizes reconnect/refresh guidance and stays inert rather than routing to the all-drafts queue as if there were an invalid draft to inspect.

Draft list and draft view use read-only MCP tools. Draft approve/reject/apply actions route through the Personal OS SDK CLI boundary and should be treated as explicit human review actions. Apply remains narrow and SDK-gated: already-approved raw-inbox session drafts targeting `05_Memory/Session/` only.

Approval actions include a Review Assist guard. If the loaded draft is blocked by deterministic approval checks, Lexa requires an explicit human override flag before it calls the SDK CLI. Reject actions are not blocked by this guard.

`GET /personal-os/drafts/review` builds the Draft Detail review packet. It returns the draft, deterministic Review Assist, Approval checklist status, audit history from `os_draft_history`, related Markdown context, optional inferred SDK target, and a capped unified diff when the target can be inferred. The Cockpit renders this before the raw draft body.

Review Assist is read-only and deterministic. It flags checks as ready, attention, or blocked, but does not approve or reject drafts.

The Cockpit enables its Apply button only when the review packet reports an approved SDK-apply-supported draft. Lexa Chat and Agent Mode do not expose automatic apply tools.

The cockpit also includes a read-only Context Browser and Context Map view. Index reads, exact tag search, Markdown file reads, and map generation route through `os_query_index`, `os_read_file`, and `os_graph_index`.
The Context Browser also has a Context Pack action. It builds a compact read-only packet from `os_query_index`, bounded `os_read_file` previews, and an optional `os_graph_index` summary. Smoke artifacts are hidden by default.
The Context Browser now also has a Code Loop action backed by `GET /personal-os/lexa-code-loop`. It bundles OS diagnostics, raw-inbox worker status, Lexa-relevant draft decisions, and a bounded Context Pack into an editable Chat prompt for the next small Lexa code improvement. It is read-only and does not auto-send the prompt.
The Code Loop cockpit view shows the diagnostic summary, Context Map health, prompt size, clickable Lexa-relevant draft decisions, and clickable evidence files before the prompt. Draft rows load the draft review packet; evidence-file rows open the source Markdown through MCP. Code Loop draft rows and generated prompts are attention-sorted: invalid/conflict/missing first, then pending, then approved/rejected. When the Code Loop reports pending drafts, its Pending metric card is clickable and loads the Pending review queue. Code Loop offers both `Chat` and `Agent` handoff buttons; `Agent` prepares a clipped `/agent ...` prompt without auto-sending it. The compact Code Loop payload includes Context Map error summaries, and the generated prompt includes a `Context Map Health` section so agents treat the map as navigation evidence rather than the product.
The standalone Context Map now renders partial graph payloads when nodes are present and the payload reports `ok=false`, `error`, or `detail`. It labels partial payloads, shows the error count, and only blocks rendering for true graph failures with no nodes. The view prioritizes navigation over a raw network visual: Important Files and Hubs render first as clickable rows, the Relationship Preview comes after them, visible nodes/edges are capped tightly for readability, and the full counts remain visible in the summary. Tag hubs in the Hubs list are actionable: clicking one fills the Tag field and runs the existing exact tag search. Manual tag input now normalizes visible `#tag` and `tag:name` forms before Context Browser, Context Pack, and Code Loop calls; the HTTP router applies the same normalization for direct `/personal-os/query`, `/context-pack`, and `/lexa-code-loop` calls. Tags that normalize to empty, such as `#!!!`, are rejected instead of silently broadening the query; the cockpit also blocks those invalid tags before firing Context Browser, Context Pack, or Code Loop requests.
Current graph health note: the `00_System/SDK/os-sdk/README.md` frontmatter gap was fixed after human approval of `06_Inbox/Drafts/2026-05-16_os_sdk_readme_frontmatter_fix_draft.md`. The live `00_System` graph probe now returns `ok: true` with 0 errors.

The draft queue includes a local search box over the currently loaded rows. It filters client-side only and does not trigger additional MCP reads.
The active Draft Queue row is visually marked with a left accent and exposes `aria-current`, so the selected draft remains clear after refreshes and local filtering.
The Draft Queue also has a Find action. It loads all non-smoke drafts, applies the same local matcher as the queue search, opens a single match directly, or leaves multiple matches visible for human selection. Pressing Enter in the draft search field triggers the same Find action; normal typing still filters the currently loaded queue locally.
Manual Personal OS Refresh preserves the currently selected draft when it is still present; automatic interval refresh stays non-invasive and skips while a draft is selected. If local search is active and refresh returns no visible matches, Lexa leaves the detail panel empty instead of silently selecting a hidden draft from the unfiltered queue.
Empty queue and no-match states also reset the Draft Detail title and approve/reject/apply actions through a shared clear helper, avoiding stale review controls.
After draft decisions, the status area remains useful with zero pending drafts by showing approved/rejected counts separately from the active list filter. The empty Pending filter explicitly states that the review queue is free. The Health status card is backed by `/personal-os/diagnostics`, not by UI-only inference.
The status area includes a visible `SYNC` card that shows `LIVE` and the last successful cockpit refresh time, so stale frontend state is easier to recognize after code or backend changes.
The status area also includes a `NEXT` card. It prioritizes invalid queue states over pending drafts, except for explicit offline diagnostics where reconnect/refresh guidance wins. When a pending draft path is present in the loaded queue, the `NEXT` card opens that draft through the existing read-only review flow. When pending drafts exist but the current queue filter hides them, `NEXT` switches the queue back to Pending, clears local search, and loads the review queue. When invalid draft or queue-error counts are nonzero, `NEXT` loads the all-drafts queue so the error state can be inspected.
If diagnostics are `blocked` for a non-queue reason such as critical low disk space, the `NEXT` card stays inert and shows the diagnostic `nextAction` instead of opening a pending review flow. Storage warnings also keep the `NEXT` card inert and surface the storage detail before pending-review guidance, so low-disk risk is not hidden behind a draft-review shortcut. Invalid queue states still route to all drafts for inspection.
The `Pending`, `Approved`, and `Rejected` status metric cards are clickable when their counts are nonzero; they switch the Draft Queue to the matching approval filter and clear local search.
The `Invalid` status metric card is clickable when its count is nonzero; it loads the all-drafts queue because invalid is a queue/error state rather than a normal approval filter.
Actionable Personal OS metric cards are real buttons with native button chrome reset, so keyboard focus remains visible while card styling stays consistent.
The Draft Queue has a New Raw action that checks `/personal-os/raw-inbox/status`, briefly reports available local processors and worker failure count, offers only available local processors in the dialog, submits raw text through `/personal-os/raw-inbox/submit`, then refreshes the pending review queue.

When a Markdown file is read in the Context Browser, the UI can place that context into Lexa Chat as an editable prepared prompt. It does not auto-send the prompt.
When a Context Pack is loaded, the UI can place the bounded packet into Lexa Chat as an editable prepared prompt. It does not auto-send the prompt.
When a Code Loop briefing is loaded, the UI can place the generated code-improvement prompt into Lexa Chat as an editable prepared prompt. It does not auto-send the prompt.
Failed Context Browser, Context Pack, and Code Loop renders clear the shared query handoff state, including cached match lists, so stale Chat/Agent handoff payloads cannot survive behind an error screen. Draft-detail empty states escape dynamic messages before rendering, so MCP or queue errors cannot inject HTML into the cockpit empty-state surface.
All Personal OS to Chat handoffs now use a shared prompt placement helper in `frontend/src/personal_os.js`. It clips below the configured chat input limit with reserved headroom, focuses the chat input, and tells the user when a prompt was compacted.

When a draft review is loaded, the Cockpit can also place a compact bounded review packet into Lexa Chat as an editable prepared prompt. It includes draft metadata, Review Assist checks, Approval checklist state, Apply boundary, audit history, related context, target diff, and draft body, capped below Lexa's chat message limit. It does not auto-send the prompt.

The draft detail view shows the Chat Review prompt size before handoff, including whether the prompt was compacted.
Personal OS cockpit errors are centrally clipped before rendering in empty states or toast notifications, so long MCP transport or validation payloads do not overwhelm the UI. FastAPI/Pydantic validation detail arrays are formatted into readable `location: message` rows instead of collapsing to a generic fallback, and the Personal OS router tests lock the live 422 shapes for invalid query params and missing draft paths. The shared `posClip()` helper keeps the `[truncated]` marker inside the requested length limit, so bounded UI fields stay truly bounded. The preload bridge routes Personal OS HTTP responses through `personalOsJson()`, so HTTP errors, malformed error bodies, malformed success bodies, validation detail arrays, request IDs, and offline Personal OS status/draft fallbacks become bounded `{ ok: false, error, httpStatus, requestId }`-style payloads instead of throwing raw JSON parse errors into the renderer. Renderer error clipping reserves room for `Request ID`, normalizes it to one line, clips oversized IDs, and now enforces custom narrow render limits even when a request ID suffix is present, so log-correlation IDs remain visible without becoming another oversized error surface. The Draft Queue renderer understands both legacy `errors[]` payloads and direct `{ ok: false, error }` payloads, and clears stale draft detail state when queue loading fails.

In Electron runtime, the main process restarts the spawned backend after an unexpected backend child exit, guarded by `app.isQuitting` and a child identity check. Normal app quit still kills the owned backend without restarting it. If port 8000 already serves a Lexa `/health` response without an `instance_token`, Electron now recognizes it as a tokenless Lexa backend, treats it as backend-ready, and reuses it in dev mode instead of warning that a non-Lexa process owns the port. The Electron health probe has a bounded response body and idempotent completion, so a strange process on port 8000 cannot grow the healthcheck buffer or resolve the probe multiple times. Tray tooltip/menu text is ASCII-safe (`Lexa AI - Lokaler KI-Assistent`, `Lexa AI oeffnen`) so Windows console/packaging encodings cannot surface mojibake in visible tray UI. Backend startup/reuse logs also use ASCII-safe separators, keeping dev console output readable under Windows codepage variance.

Lexa Chat also has stable read-only Personal OS tool wrappers registered in `backend/tool_registry.py` and executed via `backend/personal_os_actions.py`. Chat-facing map output now uses `Personal OS Context Map`, degree-ranked `Important files`, and degree-ranked `Hubs` with link counts, and the tool descriptions/Context Pack summaries use Context-Map language while preserving the internal `personal_os_graph` tool name for compatibility:

- `personal_os_diagnostics`
- `personal_os_raw_inbox_status`
- `personal_os_query`
- `personal_os_read_file`
- `personal_os_graph`
- `personal_os_context_pack`
- `personal_os_lexa_code_loop`
- `personal_os_list_drafts`
- `personal_os_view_draft`
- `personal_os_review_draft`
- `personal_os_draft_history`

These wrappers route through `/companion/execute` and then into the Personal OS MCP server or read-only worker-status boundary. `personal_os_lexa_code_loop` returns the same read-only OS-backed Lexa code-improvement prompt used by the cockpit. Chat/Companion tag parameters normalize visible `#tag` and `tag:name` forms before exact-tag OS calls, matching the cockpit, and reject empty or backend-incompatible normalized tags with a direct `Invalid tag filter` error. `personal_os_list_drafts` accepts an optional local `query` filter over loaded draft titles, paths, approval state, tags, source, and memory level. `personal_os_view_draft`, `personal_os_review_draft`, and `personal_os_draft_history` accept either an exact `draftPath` or a unique title/path `query`, resolving the query through `os_list_drafts` with smoke artifacts hidden by default. `personal_os_review_draft` reuses the same deterministic review-packet builder as the cockpit, including Review Assist, related context, audit history, target comparison, and apply hint. Automatic chat wrappers intentionally do not expose Personal OS write, task-check, approve, reject, apply, or raw-submit actions.
`personal_os_diagnostics` and `personal_os_raw_inbox_status` are whitelisted as read-only and can report readiness through Chat/Agent Mode without confirmation.

Lexa Agent Mode also supports these read-only wrappers through the async bridge in `backend/agent_loop.py`; normal Companion commands still execute in the threadpool.

Operational note: during the 2026-05-16 loop, `npm run validate` failed before running the OS validator because npm could not write its log with `ENOSPC` while `C:` reported 0 bytes free. The validator itself passed when run directly as `node dist\validate.js`. Generated Python test caches under the Lexa and OS workspaces were removed afterward, freeing about 136 MB. Old files under `AppData\Local\Temp` older than 24 hours were then removed, freeing about 646 MB. A single stale Temp extraction directory named `bcbfb88f-e5f2-4bb2-8f0c-8311cc511eb1_Premiere.Pro.2026.rar.eb1` was later removed from `AppData\Local\Temp`, freeing about 4.1 GB. Live diagnostics then reported `system-storage` as ok with about 4.0 GiB free.

This endpoint returns summary/tags only and avoids normal chat history and tool-loop behavior.

Chat input guard note: `frontend/src/chat.js` validates too-long messages and backend-offline state before setting `isLoading=true`, so a rejected send cannot leave the UI stuck in loading mode.
The existing chat character counter is now wired through `syncChatInputSize()` and the app-level chat input listener: it appears near the configured warning threshold, marks danger/over-limit states, updates during Up/Down input-history recall, and sets `aria-invalid=true` when the input exceeds `MAX_CHAT_INPUT_LENGTH`.
Normal chat streaming now distinguishes user stop from timeout/network interruption. The Stop button marks a user abort, the stream renderer shows a clean stopped state instead of a timeout/error, and HTTP error returns clear their pending stream timeout/abort state.
Chat persistence now uses a shared `getMessagePersistText()` helper that reads both normal `.msg-text` content and Agent Mode `.agent-summary` content, so agent answers are retained in the local cache and backend conversations instead of disappearing from chat history.
Chat persistence no longer treats the first DOM `.message` as a non-real greeting. The current `#chat-messages` container starts empty, so save, autosave, edit, clear, switch, new-chat, and DOM trim paths now handle the first real user/assistant message instead of preserving or dropping it by index.
Conversation sidebar refresh now has a shared `refreshConversationSidebar()` helper. Successful conversation saves and clears refresh the sidebar so message counts and previews do not remain stale after a chat turn.
File upload chat bubbles now render their file card and file-info badge with DOM helpers (`buildFileUploadCard()`, `addFileUploadMessage()`, `buildFileInfoBadge()`, `addFileUploadResponse()`) instead of passing HTML strings through the Markdown renderer. Uploads also return early while chat is already loading and stop if creating a backing conversation fails.
Voice/STT now normalizes backend transcription results before returning them to the renderer. `backend/router_voice.py` accepts both plain string transcripts and structured engine payloads such as `{ text, language }`, preserves useful metadata, marks empty transcripts as unsuccessful, and avoids crashing audit logging on dict results.
Wake Word fast STT now catches local faster-whisper transcription errors such as missing `cublas64_12.dll` and returns an empty transcript instead of poisoning the detector loop with a persistent runtime error.
Chat voice recording now checks MediaRecorder support, chooses the best supported audio MIME type (`webm`, `ogg`, or `mp4`), and sends the actual recorded MIME type through the preload STT bridge. The preload bridge strips codec parameters before choosing the upload filename, so `audio/ogg;codecs=opus` becomes an `.ogg` upload instead of falling back incorrectly.
TTS playback now has a clearable queue with a run token and current-audio tracking. Turning TTS off or clearing speech stops the active audio, revokes its object URL, empties queued text, and ignores stale async TTS responses that return after the queue was cleared.
TTS generation is now provider-locked per response. `voice/tts.py` uses provider-specific cache signatures, retries a whole multi-chunk response on the next provider instead of mixing chunk voices, and reports `voice_consistency: provider_locked_per_response` from `/voice/tts/status`.
Voice conversation TTS now generates one TTS file for the full streamed assistant answer after the text stream completes, instead of submitting each sentence as an independent TTS job. This keeps spoken turns on the same voice/provider policy as typed chat TTS and prevents sentence-level voice changes.
Settings voice tests now use the same MIME fallback for microphone checks, ignore empty chunks, post the actual recorder MIME type, stop tracks on startup failure, and revoke TTS object URLs after the settings TTS test finishes.
Wake Word (`Lexa` / hotword) now has a truthful readiness boundary. `voice/wakeword.py` tracks `ready`, `thread_alive`, and `error`; `backend/router_voice.py` only reports wake-word start success when the detector is both active and ready, and rejects not-ready starts with HTTP 503 instead of letting the UI show a false active state.
Wake Word recording performance was fixed for Windows/sounddevice. `voice/vad.py` now calibrates with one continuous recording, `voice/wakeword.py` records the wake window in one continuous capture, and `voice/conversation.py` records command turns with a persistent `InputStream` instead of reopening the recorder for every 30ms chunk.
Wake Word phrase matching now uses normalized token matching instead of substring matching. This preserves aliases such as `Lexa`, `Alexa`, and `okay Lexa`, while avoiding false wakes from words that merely contain `lex`/`lexa` as a substring.
Wake Word now supports natural inline commands. If STT hears `Lexa, ...` or `Hey Lexa, ...` in one utterance, `voice/wakeword.py` extracts the text after the wake phrase and starts the conversation with that command instead of discarding it and waiting for a second recording.
Wake Word status now exposes bounded debug telemetry (`last_transcript`, `last_detected_text`, `last_command`, `last_command_source`, `last_window_rms`, `wake_checks`, `stt_checks`) so failures can be diagnosed from `/voice/wakeword/status` without guessing.
Wake Word status serialization now normalizes numpy scalar values from VAD calibration. `voice/vad.py`, `voice/wakeword.py`, and `backend/router_voice.py` cast sensitivity/RMS/counter fields to JSON-safe Python numbers, preventing FastAPI 500s after microphone calibration.
Lexa's frontend wake-word UI now validates both `active` and `ready` on start, periodically syncs `/voice/wakeword/status` while polling events, and marks wake word inactive if the backend detector dies or reports an error.
Lexa's frontend wake-word state now separates persistent user preference from runtime detector state. If the user wants Wake Word on, backend reconnects or detector status loss no longer silently flip `lexa-wakeword` to `off`; Lexa schedules an automatic restart with backoff. Manual disable still clears the preference and cancels restart timers.
Lexa backend was restarted after the STT normalization patch; live `/voice/stt/status` and `/voice/tts/status` both report ready after restart.
Lexa backend was restarted after the Wake Word readiness/performance patch; live start/status/stop probe returned `active: true`, `ready: true`, `thread_alive: true`, then stopped cleanly.
Lexa Voice now has an aggregate diagnostics endpoint at `GET /voice/diagnostics` with `/voice/status` as an alias. It reports JSON-safe audio device state, optional microphone probe, STT readiness, TTS readiness, and Wake Word readiness in one payload for UI and future health checks.
The preload `voiceStatus()` bridge now uses `/voice/diagnostics`, and `voiceDiagnostics(probeAudio=false)` is exposed for explicit microphone probes.
Voice diagnostics normalize Windows `sounddevice` default-device objects to plain numeric JSON, so driver objects cannot crash FastAPI response serialization.
Lexa backend was restarted after the Voice diagnostics patch; live `/voice/diagnostics`, `/voice/diagnostics?probeAudio=true`, STT/TTS status, and Wake Word start/status/stop probes all returned successfully.
Lexa Settings now exposes a Voice Diagnostics row in the `STIMME TESTEN` group. It renders the aggregate voice state, bounded per-check details for microphone/STT/TTS/Wake Word, an offline backend state, and a `Diagnose` action that runs `window.lexa.voiceDiagnostics(true)` for a real microphone probe.
Lexa Settings Voice Diagnostics now treats a wake-word-only warning as core voice ready. If microphone, STT, and TTS are ok but Wake Word is simply off, the status row shows `READY`, the Wake Word check remains yellow, and the summary explicitly says Wake Word is off.
Lexa backend was restarted after the Wake Word token-matching patch; live Wake Word start/status/stop still returned `active: true`, `ready: true`, `thread_alive: true`, then stopped cleanly.
After the Wake Word keep-alive patch, live `/voice/wakeword/start` returned `active: true`, `ready: true`, `thread_alive: true`, and `/voice/diagnostics` returned `state: ready`.
After the TTS voice-consistency and Wake Word fast-STT fallback patch, live `/voice/tts/status` returned engine `elevenlabs`, provider order `elevenlabs,cartesia,sapi`, and `voice_consistency: provider_locked_per_response`. Live `/voice/diagnostics` returned `state: ready`, `nextAction: Voice stack is ready.`, with Wake Word `active: true`, `ready: true`, and an empty wake-word error.
Focused regression after the TTS voice-consistency, Wake Word fast-STT fallback, and diagnostics-next-action patch: `36 passed` across `tests/test_stt_fast_transcribe.py`, `tests/test_tts_voice_consistency.py`, `tests/test_conversation_tts_consistency.py`, and `tests/test_router_voice.py`; `py_compile` passed for `voice/tts.py`, `voice/conversation.py`, `voice/stt.py`, and `backend/router_voice.py`. Frontend voice smoke remained green: chat send guards `50 passed`, settings voice `16 passed`, preload voice `9 passed`.
After the inline Wake Word command and JSON-safe status patch, live `/voice/wakeword/start` returned `status: started`, `/voice/wakeword/status` returned `active: true`, `ready: true`, `thread_alive: true`, an empty error, JSON-safe sensitivity, and telemetry counters. Live `/voice/diagnostics` returned `state: ready`.
Focused regression after the inline Wake Word command and JSON-safe status patch: `41 passed` across `tests/test_wakeword_matching.py`, `tests/test_stt_fast_transcribe.py`, and `tests/test_router_voice.py`; `py_compile` passed for `voice/wakeword.py`, `voice/vad.py`, and `backend/router_voice.py`. Frontend smoke remained green: app chat/input wiring `14 passed`, settings voice `16 passed`, preload voice `9 passed`, chat send guards `50 passed`.
Lexa Voice now has a `voice-stack-v3` architecture boundary. `/voice/architecture` reports the target stack: Siri-style local keyword spotting for Wake Word, OpenAI/Gemini-style speech-to-speech realtime with VAD/barge-in for conversation, and the old cascaded STT -> LLM -> TTS path only as fallback.
STT now supports OpenAI `gpt-4o-mini-transcribe` as the modern default provider, with Deepgram, Groq, and local faster-whisper still available as fallbacks. Live `/voice/stt/status` after backend restart reports engine `openai`, OpenAI available, plus Deepgram/Groq/local available.
TTS now supports OpenAI `gpt-4o-mini-tts` as the first provider when the OpenAI key is present. Live `/voice/tts/status` after backend restart reports engine `openai`, provider order `openai,elevenlabs,cartesia,sapi`, and keeps `voice_consistency: provider_locked_per_response`.
Wake Word detection now runs through `voice/wakeword_engines.py` with `openwakeword` as the default local keyword spotter. The old transcript phrase matcher is no longer the automatic fallback; it only exists as an explicit legacy debug mode behind `LEXA_WAKE_LEGACY_TRANSCRIPT_ENABLED=1`.
Live `/voice/architecture` after backend restart reports OpenAI realtime ready with model `gpt-realtime-2`, Gemini Live key present but `google.genai` package missing, and Wake Word on local openWakeWord when installed/configured.
Live OpenAI TTS probe after the `voice-stack-v3` restart succeeded via `/voice/tts` with a short sentence and wrote a `31488` byte MP3 response.
Focused regression after the `voice-stack-v3` provider/architecture patch: `49 passed` across wakeword/router/STT/TTS/conversation voice tests; frontend smokes stayed green with chat send guards `50 passed`, settings voice `16 passed`, preload voice `9 passed`, and app chat/input wiring `14 passed`. Python compile passed for `voice/wakeword.py`, `voice/wakeword_engines.py`, `voice/stt.py`, `voice/tts.py`, `voice/realtime.py`, and `backend/router_voice.py`.
Wake Word transcript fallback now has a configurable STT throttle while Lexa waits for a true local openWakeWord model. `WAKE_FALLBACK_STT_MIN_INTERVAL_S` defaults to `2.0`, `/voice/wakeword/status` reports `skipped_stt_checks` and `fallback_stt_min_interval_s`, and the throttle only applies to STT-backed fallback engines, not future local keyword spotters.
Live backend restart after the Wake Word fallback throttle showed `/voice/wakeword/start` active/ready with `skipped_stt_checks` and `fallback_stt_min_interval_s: 2.0` present in status. Focused regression passed: `45 passed` across `tests/test_wakeword_matching.py` and `tests/test_router_voice.py`; app chat/input wiring remained green with `14 passed`; Python compile passed for `voice/wakeword.py`, `voice/config.py`, and `backend/router_voice.py`.
Settings Voice Diagnostics now surfaces architecture-level voice details from the aggregate diagnostics payload. The panel adds rows for `Wake engine` and `Realtime provider`, using the same DOM-safe diagnostic row renderer as the existing microphone/STT/TTS/Wake Word checks, so users can see when Wake Word is still on the transcript fallback and when OpenAI Realtime is ready.
Focused regression after the Settings voice architecture rows: `node --check frontend/src/settings.js` passed, Settings voice static smoke rose to `18 passed`, preload voice stayed `9 passed`, and router voice stayed `33 passed`.
Settings voice architecture rows now have payload-level static coverage. `tests/test_settings_voice_static.js` evaluates `voiceDiagnosticsArchitectureRows()` with a sample diagnostics payload and asserts that the Wake engine row shows fallback/throttle detail and the Realtime provider row shows OpenAI Realtime readiness; Settings voice smoke is now `20 passed`.
Wake Word transcript fallback now uses adaptive STT backoff. Repeated non-wake transcripts increase `fallback_stt_interval_s` from the 2s minimum toward the 6s maximum, reducing cloud STT churn in noisy rooms; confirmed wake phrases reset the interval to the minimum for responsiveness. `/voice/wakeword/status` reports `fallback_stt_interval_s`, min/max, and `non_wake_transcripts`.
Live backend restart after adaptive Wake Word backoff returned Wake Word `active: true`, `ready: true`, and the new fallback interval telemetry. Focused regression passed: wakeword/router `46 passed`, Settings voice `20 passed`, and Python compile passed for `voice/wakeword.py`, `voice/config.py`, and `backend/router_voice.py`.
Realtime voice diagnostics now distinguish provider configuration from active runtime. `/voice/architecture` reports `configured`, `provider_configured`, `runtime_active`, `active_path`, and provider states; OpenAI Realtime can be configured while Lexa truthfully reports that `cascaded_stt_llm_tts` is still the active path until `LEXA_REALTIME_VOICE_ENABLED` is explicitly enabled.
Settings Voice Diagnostics mirrors that distinction: the Realtime provider row now says `openai_realtime configured, cascaded_stt_llm_tts active` instead of implying that speech-to-speech runtime is already active. Live backend restart confirmed `/voice/architecture` reports `runtime_active: false`, `active_path: cascaded_stt_llm_tts`, then Wake Word was restarted and `/voice/diagnostics` returned `state: ready`.
Focused regression after the honest Realtime status patch: `voice/realtime.py` and `backend/router_voice.py` compile, router voice tests `33 passed`, and Settings voice static tests `20 passed`.
Realtime voice status now has direct unit coverage in `tests/test_realtime_voice_status.py`. It locks three core cases: OpenAI Realtime configured but runtime disabled, OpenAI Realtime runtime explicitly enabled, and no realtime provider configured falling back to `cascaded_stt_llm_tts`. Focused regression passed with `36 passed` across realtime status and router voice tests; Settings voice stayed `20 passed`.
Realtime voice status now separates `runtime_requested`, `runtime_implemented`, and `runtime_active`. The runtime cannot report active from `LEXA_REALTIME_VOICE_ENABLED` alone while the transport is still status-boundary-only; `/voice/architecture` reports `runtime_gate`, `provider_state`, and the active path. Live restart showed `runtime_requested: false`, `runtime_implemented: false`, `runtime_active: false`, `provider_configured: true`, and `active_path: cascaded_stt_llm_tts`; Wake Word was restarted and diagnostics returned ready.
Focused regression after separating realtime requested/implemented/active states: `37 passed` across realtime status and router voice tests; Settings voice stayed `20 passed`; Python compile passed for `voice/realtime.py` and `backend/router_voice.py`.
Realtime voice now has a session preflight boundary at `GET /voice/realtime/preflight`. It returns `can_start`, `blockers`, `warnings`, provider, active path, and the full realtime status, so future realtime session start code has a single tested guard instead of duplicating readiness logic.
Live `/voice/realtime/preflight` after backend restart returns `can_start: false` with blocker `Realtime audio transport is not implemented yet.`, provider `openai_realtime`, and active path `cascaded_stt_llm_tts`. Wake Word was restarted afterward and `/voice/diagnostics` returned `state: ready`.
Focused regression after the realtime preflight boundary: `40 passed` across realtime status and router voice tests; Settings voice stayed `20 passed`; Python compile passed for `voice/realtime.py` and `backend/router_voice.py`.
Aggregate Voice Diagnostics now include `realtime_preflight` directly. Settings can display the same preflight blocker shown by `/voice/realtime/preflight`, and `/voice/diagnostics` includes `can_start`, blockers, warnings, and next action in the main payload instead of requiring a second endpoint call.
Live `/voice/diagnostics` after backend restart reported `realtime_preflight.can_start: false` and blocker `Realtime audio transport is not implemented yet.`; Wake Word was restarted afterward and diagnostics returned `state: ready`. Focused regression stayed green with realtime/router voice `40 passed`, Settings voice `20 passed`, and Python compile for `backend/router_voice.py` and `voice/realtime.py`.
The Electron preload bridge now exposes `voiceArchitecture()` and `voiceRealtimePreflight()` to the renderer with offline-safe fallback payloads. This gives Settings, Chat, and the Orb a single renderer-safe path to ask for architecture and realtime preflight state without hardcoding backend URLs.
Focused regression after the voice preload bridge expansion: preload voice static smoke is now `11 passed`, Settings voice stayed `20 passed`, realtime/router voice stayed `40 passed`, and `node --check frontend/preload.js` passed. Live `/voice/architecture`, `/voice/realtime/preflight`, and `/voice/diagnostics` remained healthy.
Realtime voice now has guarded session-control endpoints. `POST /voice/realtime/start` runs the preflight and returns HTTP `409` with `session_state: blocked` while the realtime audio transport is not implemented; `POST /voice/realtime/stop` is idempotent and returns `session_state: stopped` without requiring an active session. The Electron preload bridge exposes `voiceRealtimeStart()` and `voiceRealtimeStop()` with offline-safe fallback payloads.
Live backend restart after the guarded realtime start/stop patch confirmed `/voice/realtime/start` returns `409` with blocker `Realtime audio transport is not implemented yet.`, `/voice/realtime/stop` returns stopped/inactive, Wake Word was restarted with `active: true` and `ready: true`, and `/voice/diagnostics` returned `state: ready`.
Focused regression after guarded realtime start/stop passed with realtime/router voice `42 passed`, preload voice `13 passed`, Settings voice `20 passed`, app chat/input wiring `14 passed`, and Python/Node syntax checks for `backend/router_voice.py`, `voice/realtime.py`, and `frontend/preload.js`.
The Orb/classic voice path now updates the shared Voice Status Bar through recording, STT, AI streaming, and TTS states. Orb clicks also probe the guarded realtime boundary first; when realtime is blocked, the status bar labels the active fallback path as `STT -> AI -> TTS` instead of leaving users guessing.
Focused frontend regression after the Orb/Voice Status Bar patch passed with app chat/input wiring `16 passed`, chat send/voice guard smoke `55 passed`, preload voice `13 passed`, Settings voice `20 passed`, and syntax checks for `frontend/src/app.js` and `frontend/src/chat.js`.
Settings TTS copy now matches the actual provider stack. The old `CARTESIA SONIC (Primary TTS)` label was replaced with a neutral `TTS PROVIDER` group, and the status row now reports the active `voice.tts.engine` such as OpenAI `gpt-4o-mini-tts` instead of hardcoding Cartesia as primary. TTS test copy now lists OpenAI, ElevenLabs, Cartesia, and SAPI.
Focused regression after the Settings TTS provider-copy patch passed with Settings voice static smoke `22 passed`, preload voice `13 passed`, app chat/input wiring `16 passed`, and `node --check frontend/src/settings.js`.
Wake Word events now drive the shared Voice Status Bar, not just the orb animation. Wake, listening, command capture, response, backend TTS speaking, barge-in, conversation end, error, and live volume events update visible status, provider, transcript, and meter state so hands-free voice no longer feels silent or disconnected from the UI.
Focused regression after the Wake Word status-bar event patch passed with app chat/input wiring `18 passed`, chat send/voice guard smoke `55 passed`, preload voice `13 passed`, and `node --check frontend/src/app.js`.
Frontend polish pass after the reported screenshot: the Voice Status Bar markup now has the correct `.voice-status-bar` class, left/center/right layout wrappers, stable 96x24 level-meter canvas, and centered fixed overlay styling below the top nav instead of leaking unstyled text into the top-left corner. The compact Orb is brighter and more legible in active chat via a larger compact clamp, drop shadow, brighter dot/core material, larger points, and stronger ambient light.
Focused regression after the Voice Status Bar/Orb CSS patch passed with app chat/input wiring `23 passed`, chat send/voice guard smoke `55 passed`, Settings voice `22 passed`, preload voice `13 passed`, and syntax checks for `frontend/src/app.js` and `frontend/src/orb3d.js`. Live `/voice/diagnostics` still reported `state: ready`, Wake Word ready, and TTS engine `openai`.
Responsive frontend polish now gives the chat input and top nav stronger overflow guards. `#chat-input` can shrink with `min-width: 0`, input action buttons no longer collapse, mobile top nav hides lower-priority time/title text before overflow, status text is ellipsized, and mobile input buttons keep stable 34px dimensions.
Focused regression after the responsive input/nav patch passed with app chat/input wiring `26 passed`, chat send/voice guard smoke `55 passed`, Settings voice `22 passed`, and preload voice `13 passed`.
Chat open-state layout now reduces vertical dead space from the compact Orb. When `voice-orb-container.compact` is active, chat messages gain a tighter top padding and flex min-height guard, while the compact Orb uses a smaller but still legible clamp. This keeps voice presence without pushing real conversation content too far down.
Focused regression after the open-chat layout tightening passed with app chat/input wiring `27 passed`, chat send/voice guard smoke `55 passed`, Settings voice `22 passed`, and preload voice `13 passed`.
Lexa chat input is now a professional multiline composer instead of a single-line text field. `#chat-input` is a growing textarea with a 160px overflow guard, Enter sends by default, Shift+Enter/Ctrl+Enter can insert new lines where appropriate, Ctrl+Enter mode still works, and Up/Down history recall no longer steals cursor movement inside multiline prompts.
Focused regression after the multiline chat composer patch passed with app chat/input wiring `32 passed`, chat send/voice guard smoke `55 passed`, Settings voice `22 passed`, preload voice `13 passed`, and syntax checks for `frontend/src/app.js` and `frontend/src/chat.js`.
The Personal OS Context Map renderer is now larger and more readable. It renders a full `Relationship Map` stage with 1160x430 viewBox, more visible file/tag/ref nodes, a legend, grouped lanes, larger node cards, degree badges, and responsive stacking instead of the earlier tiny mini-network.
Focused regression after the Context Map renderer polish passed with Personal OS prompt/static smoke `135 passed`, Personal OS preload smoke `18 passed`, Personal OS router tests `38 passed`, app chat/input wiring `32 passed`, chat send/voice guard smoke `55 passed`, and `node --check frontend/src/personal_os.js`.
The chat composer no longer uses sticky positioning in the ambient/start view, so it cannot float over the greeting/orb. It becomes sticky only when the transcript is open via `voice-orb-container.compact`. Render QA confirmed ambient composer `position: relative`, compact composer `position: sticky`, and no overlap with the greeting or orb.
Focused regression after the composer positioning fix passed with app chat/input wiring `33 passed`, chat send/voice guard smoke `55 passed`, Personal OS prompt/static smoke `135 passed`, and syntax checks for `frontend/src/app.js`, `frontend/src/chat.js`, and `frontend/src/personal_os.js`.
Lexa first product-UI polish pass now removes several visible demo-quality signals from the main chat and Personal OS surfaces. Conversation starters no longer render emoji text; they use deterministic inline SVG icons. The zero-state hero has stable non-viewport-scaled type and neutral tracking, the talk button/composer/submit button have calmer product chrome, and the Voice Status Bar is a compact glass overlay with a softer meter, non-italic transcript text, clipped status label, and neutral provider badge.
The Personal OS cockpit received a matching surface pass: status cards, panels, capability rows, draft rows, review cards, and assist cards use quieter backgrounds, 8px radii, lower border contrast, and no glow hover treatment. This keeps the review workflow intact while making the cockpit less boxy and less noisy.
The shell chrome also received a product polish pass: titlebar and status badge are quieter, sidebar active/hover states no longer slide or glow, and transient toast/notification surfaces use neutral shadows instead of purple demo glow.
Focused regression after the chat/voice/Personal OS/shell UI polish pass passed with app chat/input wiring `39 passed`, chat send/voice guard smoke `55 passed`, Settings voice static smoke `22 passed`, preload voice static smoke `13 passed`, Personal OS prompt/static smoke `136 passed`, Personal OS preload smoke `18 passed`, and syntax checks for `frontend/src/chat.js` and `frontend/src/personal_os.js`.
Lexa chat transcript surface now has a calmer professional pass. Assistant and user message bubbles use lower-contrast surfaces, softer avatars, neutral metadata, no backdrop blur on message bodies, calmer code/inline-code blocks, and suggestion chips no longer use purple glow or lift effects. This targets the visible "cheap demo bubble" problem in active conversations without touching chat routing.
Focused regression after the transcript surface polish passed with app chat/input wiring `41 passed`, chat send/voice guard smoke `55 passed`, Settings voice static smoke `22 passed`, preload voice static smoke `13 passed`, and Personal OS prompt/static smoke `136 passed`.
Lexa Dashboard and System tool surfaces now have a denser professional pass. Dashboard widgets no longer use animated hero glow or gradient clock text, the dashboard Chat button is neutral, and system tool cards render as compact two-column rows with subdued icon wells instead of large centered icon cards with purple glow/lift hover.
Focused regression after the Dashboard/System surface polish passed with app chat/input wiring `43 passed`, chat send/voice guard smoke `55 passed`, Personal OS prompt/static smoke `136 passed`, and Settings voice static smoke `22 passed`.
Lexa Voice Status Bar now has a second product-polish pass. State labels no longer use emoji/debug copy, the overlay is narrower and quieter, empty provider/transcript fields collapse visually, and the level meter draws a rounded rail/bar instead of a black block.
Focused regression after the Voice Status Bar product-polish pass passed with app chat/input wiring `45 passed`, chat send/voice guard smoke `55 passed`, and `node --check frontend/src/app.js`.
Lexa local smalltalk and capability-copy now has a professional tone pass. Built-in greeting, thanks, goodbye, identity, capability, compliment, insult, action-confirmation, and voice tool-result fallbacks no longer use repeated `Chef`/buddy/demo copy. The dashboard greeting also no longer says `Chef`/`Boss`.
Focused regression after the professional tone pass passed with intent-engine tests `29 passed`, app chat/input wiring `46 passed`, chat send/voice guard smoke `55 passed`, and Python compile for `backend/intent_engine.py`, `backend/ai_engine.py`, `backend/action_parser.py`, `backend/router_chat.py`, and `voice/conversation.py`. The live backend was restarted and `/chat` for `was kannst du` returned the professional capability list without `Chef` or emoji bullet clutter.
Lexa local intent status copy now has a second professionalism pass. Fast-path action messages for Spotify, web search/open, weather, calendar, email, downloads, todos, process list, clipboard, jokes, age, and boredom no longer use emoji/debug endings or over-hyped buddy phrasing. `tests/test_intent_engine.py` now locks this with shared demo-tone markers for both smalltalk and local status/help replies.
Focused regression after the intent status-copy pass passed with intent-engine tests `42 passed`, app chat/input wiring `46 passed`, chat send/voice guard smoke `55 passed`, and Python compile for `backend/intent_engine.py`. The live backend was restarted; `/chat` probes for `spiel daft punk` and `mir ist langweilig` returned neutral production-style replies.
Lexa ambient start view now has a calmer product-surface pass. The zero-state no longer leans on oversized hero typography, gradient H1 text, oversized orb, pill CTA glow, or rounded stat pills; the orb is smaller, the headline is neutral, stats are subdued, and the talk button is a compact 8px product control.
Focused regression after the ambient start polish passed with app chat/input wiring `47 passed`, chat send/voice guard smoke `55 passed`, and intent-engine tests `42 passed`.
The manual `/agent ...` branch is detected before normal chat loading/history setup. `sendAgentMessage()` owns that path, so the `/agent` prefix is stripped once and the normal chat path does not pre-set `isLoading`.
Agent Mode now has a renderer-side stream read timeout in `sendAgentMessage()`. If `/agent/run` stops delivering SSE chunks, Lexa cancels the reader, clears `isLoading`, re-enables Send, and shows the translated `chat.agentTimeout` message instead of leaving the chat stuck in a loading state.
The preload `agentRun()` bridge now uses `fetchWithTimeout(..., 15000)` for `/agent/run`, so connection setup cannot hang forever before the renderer receives a stream to read.
Agent Mode now has a visible cancel control in the agent message header. It cancels the active stream reader, marks the run as stopped, clears `isLoading`, and re-enables Send without showing a false error toast.
The Personal OS Health card uses the first blocking or warning diagnostic check as its headline detail. For example, an `attention` state caused by one pending draft should show the pending-draft reason directly.
Draft review now recognizes validated `target_file`, `targetFile`, or `target` frontmatter fields as read-only target candidates. Frontmatter targets are shown with `targetSource: frontmatter`; they load target metadata when possible but do not generate a body diff because these manual drafts are proposals, not guaranteed full-file replacements. Draft Detail labels this section `Target Review` and shows target path/source, clipped target-read errors, or a clear no-body-diff message. Chat/Agent formatting for `personal_os_review_draft` includes target path/source and trims long target-read errors.
Personal OS auto-refresh is intentionally non-invasive. `app.js` calls `refreshPersonalOsView({ auto: true })` on the interval; `personal_os.js` skips that auto-refresh while a draft is selected, a modal is open, or select/decision/apply work is in progress. Manual Refresh still forces a read.
Personal OS MCP config loading now falls back from `LEXA_DATA_DIR/mcp_servers.json` to the project `mcp_servers.json`. This fixes dev/Desktop runs where the in-memory registry reported `Unknown MCP server: 'personal_os'` because the user-data directory did not contain a copied MCP config.
Focused regression after the MCP config fallback passed with Personal OS router tests plus the new registry fallback test `39 passed`, Personal OS prompt/static smoke `137 passed`, Personal OS preload static `18 passed`, and Python compile for `backend/mcp_registry.py` and `backend/router_personal_os.py`. The live backend was restarted; `/personal-os/status` reported `connected`, 10 tools, and `/personal-os/diagnostics` returned `attention` only because one draft still needs review.

Electron dev ergonomics: `frontend/main.js` has a dev-only source watcher for unpackaged runs. It watches `frontend/src` for `.js`, `.css`, and `.html` changes, debounces for 350ms, and calls `mainWindow.webContents.reloadIgnoringCache()`. This is disabled in packaged builds through `app.isPackaged`.

## Useful Commands

```powershell
venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
venv\Scripts\python.exe -m pytest tests\test_router_personal_os.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests\test_personal_os_actions.py tests\test_agent_loop.py tests\test_ai_engine.py tests\test_router_companion.py tests\test_router_personal_os.py tests\test_security.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
node tests\test_chat_rendering.js
node tests\test_personal_os_prompt.js
node tests\test_chat_send_guards.js
node tests\test_preload_voice_static.js
node tests\test_settings_voice_static.js
node tests\test_app_chat_input_wiring.js
venv\Scripts\python.exe -m pytest tests\test_router_voice.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests\test_stt_fast_transcribe.py tests\test_tts_voice_consistency.py tests\test_conversation_tts_consistency.py tests\test_router_voice.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests\test_wakeword_matching.py tests\test_stt_fast_transcribe.py tests\test_router_voice.py -q -p no:cacheprovider
venv\Scripts\python.exe -m pytest tests\test_wakeword_matching.py tests\test_router_voice.py tests\test_stt_fast_transcribe.py tests\test_tts_voice_consistency.py tests\test_conversation_tts_consistency.py -q -p no:cacheprovider
```

## Current Priorities

1. Keep runtime artifacts out of commits.
2. Maintain a clean reviewable baseline.
3. Continue security and tool-execution hardening.
4. Use the Personal OS diagnostics endpoint/tool as the startup readiness check.
5. Use the Code Loop action/tool to choose the next small Lexa code improvement from OS evidence before patching.
6. Continue using the Code Loop action/tool to choose the next small Lexa code improvement from OS evidence; the SDK README graph health issue is resolved.

## Agent Rules

- Do not load the whole repo unless the user asks for a full audit.
- Use targeted `rg` before opening files.
- Avoid broad refactors while the working tree is large.
- Do not revert user changes.
- Prefer tests for security, routing, and tool-boundary changes.
