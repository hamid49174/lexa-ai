# Core Flow Coverage Plan

Date: 2026-05-20

Goal: strengthen integration coverage for Lexa's internal daily-use core flows before any further lifecycle refactors. This plan does not claim PublicRC readiness and does not change product behavior.

## Current Coverage Map

| Flow | Current tests covering it | Missing coverage | Risk if refactored without stronger coverage | Suggested minimal test |
| --- | --- | --- | --- | --- |
| App startup | `electron_startup_health_smoke.js`, `electron_ui_visual_smoke.js`, `test_internal_daily_use_readiness_static.js` | Startup with real backend CI proof remains external; local smoke is mocked | Renderer/main/preload ordering regressions could hide until manual app launch | Keep startup smoke in required gate list; add focused startup assertions only when a startup bug appears |
| Auth/local health | `electron_startup_health_smoke.js`, `test_local_auth.py`, preload security static tests | No remote CI proof; no signed installer proof | Bridge/auth regressions could weaken local-only guard behavior | Keep startup health smoke and preload static checks together |
| Chat input submit | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, `electron_core_chat_flow_smoke.js` | Browser-level manual typing with a live backend is not covered | Send-pipeline refactors could break user-message insertion or input reset | `electron_core_chat_flow_smoke.js` submits text through the real send button with a mocked stream |
| Mocked assistant response rendering | `test_chat_rendering.js`, `electron_core_chat_flow_smoke.js` | Does not cover every markdown feature through the full send pipeline | Renderer refactors could break streaming-to-final formatted output | Keep mocked SSE response in `electron_core_chat_flow_smoke.js` and rendering unit coverage in `test_chat_rendering.js` |
| Streaming response lifecycle | `test_chat_send_guards.js`, `electron_core_chat_flow_smoke.js`, `electron_streaming_robustness_smoke.js`, `electron_ui_visual_smoke.js`, `test_chat_streaming_helpers.js` | Real provider/network behavior and full send-pipeline orchestration remain outside local smoke coverage | Streaming refactors could strand loading state, disabled buttons, duplicate partial text, or unsafe malformed stream output | Keep robustness smoke in required gates before moving any larger streaming lifecycle code |
| Conversation history save/load | `test_router_conversations.py`, `test_chat_send_guards.js`, `electron_ui_visual_smoke.js`, `electron_core_chat_flow_smoke.js`, `electron_tool_confirmation_smoke.js`, `electron_history_lifecycle_smoke.js`, `electron_history_failure_smoke.js` | Real backend persistence and active-conversation delete edge cases still need focused coverage | History refactors could drop raw markdown, duplicate messages, corrupt active selection, or crash on malformed history payloads | Keep failure-path smoke in required gates before moving save/load/delete orchestration |
| Tool-call display | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, backend action/parser tests, `electron_tool_confirmation_smoke.js`, `electron_tool_display_smoke.js`, `test_chat_tool_display_helpers.js` | Real Companion/tool execution remains outside renderer smoke coverage | Tool rendering refactors could expose unsafe labels, unsafe result content, or hide confirmation state | Keep render-only display smoke mocked; do not add real tool execution to renderer tests |
| File upload / attachment display | `electron_file_upload_result_smoke.js`, `test_chat_file_display_helpers.js`, `test_chat_send_guards.js`, `test_frontend_script_order_static.js` | Real file upload execution, backend upload calls, filesystem reads/writes, and provider-backed file analysis remain intentionally outside renderer display smoke | File UI refactors could expose unsafe filenames/content, create live controls from history, or accidentally trigger upload/tool/provider paths | Keep display-only smoke mocked with in-memory `File` objects; add backend upload contract tests only with safe fixtures |
| Confirmation happy path | `test_router_companion.py`, `test_companion_confirmation.py`, `electron_presence_challenge_smoke.js`, `electron_tool_confirmation_smoke.js`, `electron_confirmation_click_smoke.js` | Real Companion execution remains intentionally outside renderer smoke coverage | Confirmation UI refactors could call Companion incorrectly or lose safe denial behavior | Keep focused click smoke mocked; do not add real tool execution to renderer tests |
| Personal OS cockpit read-only view | `electron_personal_os_readonly_smoke.js`, `electron_personal_os_handoff_smoke.js`, `test_personal_os_prompt.js`, `test_internal_daily_use_readiness_static.js`, `test_frontend_script_order_static.js` | Real OS root browsing, draft decisions, raw inbox submit, cleanup/archive/migration, SDK write operations, and real filesystem writes remain intentionally outside smoke coverage | Personal OS UI refactors could expose unsafe OS-like content, make the Internal surface confusing, or accidentally trigger write-capable bridge methods while opening the cockpit | Keep the read-only and handoff smokes mocked; do not click approve/reject/apply/raw-submit/cleanup paths without dedicated write-safe harness coverage |
| Personal OS chat handoff and draft-review display | `electron_personal_os_handoff_smoke.js`, `test_personal_os_prompt.js` | Real draft decision/write behavior, real OS files, real provider sends, and Companion execution remain intentionally outside smoke coverage | Handoff/review UI changes could auto-send prompts, lose no-auto-decision guidance, or accidentally invoke write-capable bridge methods | Keep handoff smoke focused on composer placement and display-only review controls; add a separate write-safe harness before testing decisions |
| OS draft creation path | `test_personal_os_prompt.js`, `test_router_personal_os.py`, `test_personal_os_actions.py`, eval OS draft tests | Full renderer draft creation from chat handoff is not isolated | OS draft UI refactors could bypass Draft/Approval expectations | Add a mocked Personal OS draft handoff smoke only after core chat/history smokes are stable |
| Settings persistence | `test_settings_voice_static.js`, `test_app_chat_input_wiring.js`, `electron_ui_visual_smoke.js`, `electron_settings_persistence_smoke.js`, `test_settings_helpers.js` | Provider/keyring/license persistence remains intentionally outside the local preference smoke | Settings refactors could silently stop saving local preferences, lose Beta/Internal labels, or apply corrupt localStorage values | Keep local preference smoke in settings gates; add provider/secret coverage only with explicit keyring-safe mocks |
| Provider/model settings | `electron_provider_settings_smoke.js`, `test_settings_provider_helpers.js`, `test_frontend_script_order_static.js`, `test_preload_bridge_security_static.js` | Real provider calls, API-key/keyring writes, and backend contract edge cases remain intentionally outside the renderer smoke | Provider settings refactors could break model selection, expose unsafe labels, or accidentally touch secret/keyring paths | Keep provider smoke keyring-safe; add fake backend contract coverage before changing provider/model payload handling |
| Beta/Internal label visibility | `test_internal_daily_use_readiness_static.js`, `test_app_chat_input_wiring.js` | Visual placement is only indirectly covered | Unstable surfaces could become visibly unlabelled | Keep static readiness checks in every internal daily-use pass |

## Added In This Pass

`tests/electron_core_chat_flow_smoke.js` adds focused Electron coverage for two core boundaries:

1. Chat submit to streamed assistant response:
   - Loads the real `frontend/src/index.html` and renderer scripts.
   - Uses isolated Electron `userData`.
   - Uses the existing preload smoke bridge.
   - Stubs only renderer `fetch()` for `/chat/stream`.
   - Clicks the real send button.
   - Asserts the user message appears, the mocked assistant response renders, Markdown formats, unsafe HTML stays non-executable, raw persisted text remains available, local history is written, answer action buttons re-enable, and the composer resets.

2. Persisted conversation render boundary:
   - Calls `renderPersistedConversationMessages()` with mocked persisted messages.
   - Asserts user/assistant DOM shape, formatted Markdown output, no executable script tags, and raw persisted Markdown retained on the message.

## Added In Tool/History Coverage Sprint

`tests/electron_tool_confirmation_smoke.js` adds focused Electron coverage for render-only tool confirmation and history boundaries:

1. Tool confirmation rendering:
   - Loads the real `frontend/src/index.html` and renderer scripts.
   - Uses isolated Electron `userData` and the existing preload smoke bridge.
   - Stubs renderer `fetch()` only for `/chat/stream`.
   - Clicks the real send button and returns a mocked streamed action with `rc: true`.
   - Asserts confirmation language, command/param text, confirm and deny controls, unsafe HTML containment, and no pending-tool clear/execution side effects.
   - Calls `addMessage(..., action, true, true)` directly to cover the non-stream render-only path.

2. Conversation history rendering:
   - Calls `renderPersistedConversationMessages()` with ordered user/assistant messages.
   - Asserts message order, Markdown formatting, action-like persisted payloads not becoming live confirmation controls, selected conversation row state, title/preview text safety, and empty history state.

## Added In History Lifecycle Sprint

`tests/electron_history_lifecycle_smoke.js` adds focused Electron coverage for mocked conversation lifecycle behavior:

- initial empty history state
- mocked conversations appearing in the sidebar
- safe title and preview text rendering for unsafe HTML-like content
- inactive conversation `aria-current` state
- selecting a conversation through `switchConversation()` and hydrating messages in order
- selected conversation state and `lexa-active-conversation` storage
- Markdown rendering and unsafe HTML containment after history load
- action-like persisted history not becoming live confirmation/tool controls
- switching between two conversations and replacing the rendered transcript
- deleting an inactive mocked conversation and preserving the active conversation

This coverage uses only the existing Electron smoke mock bridge and does not exercise real backend persistence or real data deletion.

## Added In History Failure + Confirmation Click Sprint

`tests/electron_history_failure_smoke.js` adds focused renderer coverage for malformed and failed history paths:

- malformed conversation rows with missing title, missing preview, and unsafe HTML-like title/preview content
- malformed persisted message entries, including null/empty entries and action-like content that must not become live controls
- failed conversation load preserving the active conversation, active row, and transcript
- invalid local history recovery without rendering garbage
- empty/unavailable history recovery to a stable empty state

The sprint also fixed a small history sidebar robustness bug in `frontend/src/chat_history_ui.js`: missing conversation titles/previews are normalized before rendering. Normal conversation output is preserved, and backend load/save/delete orchestration remains in `chat.js`.

`tests/electron_confirmation_click_smoke.js` adds mocked renderer coverage for confirmation button behavior:

- approval click clears pending confirmation once and calls only the mocked `executeWithConfirmation()` bridge path
- denial click clears pending confirmation and updates the UI without execution
- window-confirm cancel clears pending confirmation without execution
- unsafe params remain contained in text, and prompt text includes the expected command summary

This smoke uses mocks/spies only. It does not execute real Companion tools, OS actions, OS draft apply/write behavior, or real confirmation approval execution.

## Added In Streaming Robustness Sprint

`tests/electron_streaming_robustness_smoke.js` adds focused renderer coverage for mocked `/chat/stream` behavior:

- assistant response split across underlying stream chunks renders as one coherent message
- markdown split across chunks still renders bold text, links, code, and tables after final render
- unsafe HTML-like content split through stream chunks remains contained as text
- malformed SSE events and malformed JSON payloads do not crash the renderer or drop later valid content
- a stream ending without a final marker recovers to a usable final message when content exists
- stream read errors keep the partial answer, show a safe warning, avoid leaking raw error details into the chat, and restore the composer controls
- user abort during streaming leaves a stable partial response and restores the composer controls
- simulated timeout before response shows the localized timeout message without leaking mock exception details

`tests/test_chat_streaming_helpers.js` directly covers the extracted streaming parser helpers for buffered-line splitting, data-line parsing, ignored non-data/empty lines, done events, and malformed JSON logging without throwing.

Extraction completed:

- `frontend/src/chat_streaming_helpers.js` now owns only `chatStreamBufferedLines()` and `parseChatStreamDataLine()`.
- `frontend/src/chat.js` still owns fetch orchestration, AbortController ownership, rendering, state recovery, history persistence, tool handling, and the send pipeline.

## Added In Tool Display Coverage Sprint

`tests/electron_tool_display_smoke.js` adds focused renderer coverage for mocked non-confirmed tool display:

- a mocked `/chat/stream` response with a non-confirmed `system_info` action uses only the Electron smoke bridge and replaces placeholder assistant text with the mocked tool result
- rendered tool result content remains safe when formatted into chat DOM
- non-confirmed tool success and no-result paths do not render confirmation controls or live action cards
- composer/send state recovers after mocked tool display
- persisted tool-like history content remains escaped text and does not create live action controls

`tests/test_chat_tool_display_helpers.js` directly covers the extracted display helper for string results, summary/message/error precedence, fallback key-value formatting, skipped internal fields, empty unsupported data, and unsafe text staying text for renderer formatting.

Extraction completed:

- `frontend/src/chat_tool_display_ui.js` now owns only `toolResultDisplayText()`.
- `frontend/src/chat.js` still owns real tool execution calls, success/failure branching, rendering into the active message, notifications, history persistence, confirmation behavior, and send pipeline state.

## Added In Settings Persistence Sprint

`tests/electron_settings_persistence_smoke.js` adds focused renderer coverage for local settings preferences:

- settings view markup loads under the real renderer
- theme, accent, font size, and language preferences persist through the existing localStorage mechanism
- saved local preferences hydrate back into the UI controls
- corrupt theme/accent/font/language values recover to safe defaults
- unknown localStorage keys are preserved
- unsafe persisted values do not create executable DOM nodes
- Beta/Internal readiness chips remain visible in Settings
- the smoke does not trigger renderer `fetch()` while saving local preferences

`tests/test_settings_helpers.js` directly covers the extracted pure normalization helpers for valid and invalid theme, accent, font-size, and language values.

Extraction completed:

- `frontend/src/settings_helpers.js` now owns only local preference normalization helpers.
- `frontend/src/settings.js` still owns settings view refresh, provider/model status, voice settings, key actions, license activation/removal, profile save, backup controls, Hermes autostart controls, backend calls, and IPC-backed settings behavior.

## Added In Provider/Model Settings Sprint

`tests/electron_provider_settings_smoke.js` adds focused renderer coverage for provider/model settings with keyring-safe smoke mocks:

- provider status rows render mocked availability for Groq, OpenAI, Gemini, and Anthropic
- the AI model selector hydrates the mocked current model
- a safe mocked model change uses only the `setAiModel` smoke bridge
- unsafe provider/model labels are rendered as inert text and do not create executable nodes
- no renderer `fetch()` calls are performed
- no secret-like values are exposed in the Settings path
- no API-key/keyring bridge methods or presence challenges are triggered
- bridge audit metadata does not include the selected model value

`tests/test_settings_provider_helpers.js` directly covers the extracted provider/model display helpers for grouped/flat options, malformed payload recovery, active selection, description text, and classic-script constraints.

Extraction completed:

- `frontend/src/settings_provider_helpers.js` now owns provider/model display helpers.
- `loadModelSelection()` and `changeAiModel()` now live in `settings.js` instead of `chat.js`.
- API-key/keyring controls, real provider/backend calls, voice runtime, license activation, Electron IPC, chat lifecycle, and OS draft paths remain untouched.

## Added In File Upload / Attachment Result Sprint

`tests/electron_file_upload_result_smoke.js` adds focused render-only coverage for file and attachment display:

- uses the real renderer with isolated Electron `userData`
- uses only in-memory `File` objects
- verifies the upload card renders a safe filename and metadata
- verifies file result badges render unsafe type/size metadata as inert text
- verifies result content keeps Markdown rendering while escaping unsafe HTML-like input
- verifies failed file-result display is non-executable
- verifies attachment-like history content does not create live action controls
- verifies no renderer `fetch()` calls occur
- verifies no upload/tool/provider/OS bridge methods are called

`tests/test_chat_file_display_helpers.js` directly covers the extracted file display helpers for size labels, extension fallback, unsafe suffix handling, badge text, missing payloads, and classic-script constraints.

Extraction completed:

- `frontend/src/chat_file_display_ui.js` now owns only `fileUploadSizeLabel()`, `fileUploadExtension()`, and `fileInfoBadgeText()`.
- `frontend/src/chat.js` still owns `handleFileUpload()`, in-memory card insertion, upload orchestration, backend calls, action handling, history persistence, and send/streaming state.
- Real filesystem upload execution, backend file analysis, Companion execution, OS draft/apply behavior, provider calls, and Electron IPC remain untouched.

## Added In Read-only Personal OS Cockpit Sprint

`tests/electron_personal_os_readonly_smoke.js` adds focused renderer coverage for opening and inspecting the Personal OS cockpit without write actions:

- loads the real renderer with isolated Electron `userData` and the existing smoke bridge
- switches to the Personal OS view and keeps the Internal readiness chip visible
- renders mocked OS status, draft queue rows, draft detail, context query rows, context pack results, context map nodes, empty state, and error state
- verifies unsafe OS-like titles, previews, body text, diagnostics, and graph labels remain contained and do not create executable nodes
- verifies apply remains disabled for a mocked pending draft and write-capable controls are not clicked
- verifies no renderer `fetch()` calls occur
- verifies no Personal OS decision/apply/raw-submit, Companion/tool execution, provider, or secret bridge methods are called

Extraction completed:

- `frontend/src/personal_os_display_helpers.js` now owns pure display helpers for text normalization, localized UI text fallback, status classes, event/assist classes, error formatting, refresh labels, state labels, and draft status labels.
- `frontend/src/personal_os.js` still owns refresh orchestration, bridge reads, draft selection/review, draft approval/rejection/apply actions, raw inbox submit, context browsing actions, graph rendering event handlers, and chat handoff.

Remaining coverage gaps:

- no real OS root access or real filesystem reads/writes
- no approve/reject/apply/raw-submit/cleanup/archive/migration clicks
- no SDK write operation coverage
- no path-redaction assertion for arbitrary backend error detail; current coverage verifies escaping/containment, not semantic redaction

## Added In Personal OS Chat-Handoff + Draft Review Smoke Sprint

`tests/electron_personal_os_handoff_smoke.js` adds mocked renderer coverage for Personal OS prompt placement and draft-review display:

- opens Personal OS through the real renderer view switch
- renders a mocked context payload and clicks the real context-to-chat handoff button
- verifies the chat composer receives the expected Personal OS context prompt without auto-sending
- renders a mocked pending draft queue and draft review package
- verifies draft title/body/path, review assist, prompt hint, apply boundary, audit history, target diff, and related context display safely
- clicks only the review-to-chat button and verifies the draft-review prompt is placed in the chat composer
- verifies the review prompt includes no-auto-decision guidance
- verifies no renderer `fetch()` calls, send calls, Personal OS decision/apply/raw-submit calls, Companion/tool execution, provider, or secret bridge calls occur

Extraction completed:

- `frontend/src/personal_os_review_helpers.js` now owns the display-only review hint helpers `renderPosApplyHint()` and `renderPosPromptHint()`.
- `frontend/src/personal_os.js` still owns draft selection, bridge reads/writes, approve/reject/apply, raw inbox submit, context file reads, chat handoff orchestration, and prompt construction.

Current UI behavior documented by the smoke:

- pending draft approve/reject controls are visible according to existing behavior and are not clicked by this smoke
- apply remains disabled for the mocked pending draft
- the chat-review control is enabled only because a mocked review package is present

Remaining coverage gaps:

- no real OS root access or filesystem mutation
- no approve/reject/apply/raw-submit/cleanup/archive/migration clicks
- no SDK write operation or Companion execution coverage
- no real provider/chat send coverage from the handoff prompt

## Stop-line Before Refactors

Do not extract or rewrite the full streaming lifecycle, send pipeline, conversation save/load/delete orchestration, active-conversation delete recovery, real file upload execution, backend upload contracts, filesystem writes, real tool execution, real confirmation approval execution, Companion execution, OS draft actions, Personal OS write paths, settings keyring/secret handling, voice runtime, license activation, backend/provider calls, or Electron IPC until focused integration coverage exists for the specific lifecycle being changed.

Recommended next coverage target: provider/model backend contract coverage with fake provider responses, or a Personal OS read-call failure smoke that still avoids approve/reject/apply/raw-submit and real OS writes.
