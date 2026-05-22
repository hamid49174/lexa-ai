# Frontend Modularization Plan

Date: 2026-05-20
Baseline commit before Pass 1: `25a922df1c514d7461d3df2a5ad2a449c1e4e812`

Goal: make the classic-script frontend easier to maintain without changing visible behavior, adding a bundler, or weakening security/release gates.

## Current Size Snapshot

| File | Approx. lines before Pass 1 | Main responsibilities currently mixed |
| --- | ---: | --- |
| `frontend/src/chat.js` | 4698 | chat persistence, rendering, markdown formatting, streaming, agent UI, composer palette, input history, snippets, voice, conversation list, search, file uploads |
| `frontend/src/personal_os.js` | 2316 | OS status cards, draft queue, draft detail/review/apply UI, context search, context map rendering, Obsidian/code-loop prompts |
| `frontend/preload.js` | 2259 | API bridge, local auth, risk classification, presence gates, IPC wrappers, mock bridge behavior |
| `frontend/src/app.js` | 1567 | app startup, view switching, ambient canvas, backend health, wake word/orb orchestration, notifications, global actions |
| `frontend/src/index.html` | 1252 | static shell, view markup, settings controls, script order |
| `frontend/src/settings.js` | 1191 | provider settings, readiness cards, voice diagnostics, license UI, backup controls, Hermes autostart |
| `frontend/main.js` | 1172 | Electron lifecycle, backend process supervision, IPC handlers, update checks, window/tray behavior |

## Proposed Boundaries

| Area | Future module boundary | Risk | Tests that should cover it |
| --- | --- | --- | --- |
| Chat constants | `chat_constants.js` for pure data tables and stable constants | Low | `test_frontend_script_order_static.js`, `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, Electron visual smoke |
| Chat pure formatting | URL normalization, markdown block helpers, table/code helpers | Low-medium | `test_chat_rendering.js`; add direct helper test before moving |
| Chat composer palette | command text, alias ranking, icons, palette render helpers | Medium | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, Electron visual smoke |
| Chat input wiring | textarea sizing, history, snippets, send-mode behavior | Medium | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js` |
| Chat persistence/history | conversation save/load, local agent metadata, deletion/switching | High | Electron visual smoke plus router conversation tests |
| Chat streaming/tool rendering | streaming send, tool-call confirmation, agent run panels | High | Electron visual smoke, chat send guards, companion/router tests |
| Chat file/attachment display | upload card metadata, file result badges, attachment-like history display | Low-medium | `electron_file_upload_result_smoke.js`, `test_chat_file_display_helpers.js`, `test_chat_send_guards.js` |
| Chat voice integration | mic/STT/TTS/orb state and wake-word paths | High | `test_settings_voice_static.js`, voice tests, Electron visual smoke |
| Settings local preferences | theme, accent, font size, language normalization and hydration helpers | Low | `electron_settings_persistence_smoke.js`, `test_settings_helpers.js`, `test_frontend_script_order_static.js` |
| Settings provider/voice/license controls | provider status, API key/keyring buttons, voice runtime settings, license activation, backend-backed controls | High | settings voice static tests, future keyring-safe settings smokes |
| Personal OS constants/pure helpers | labels, clipping, status class helpers | Low-medium | `test_personal_os_prompt.js` |
| Personal OS draft actions | approve/reject/apply, SDK boundaries, chat handoff | High | `test_personal_os_prompt.js`, `test_router_personal_os.py`, OS gates |
| Electron preload/main | security policy, IPC wrappers, lifecycle/retry/update checks | High | preload/main static tests, startup/presence smokes |

## Recommended Extraction Order

1. Pure constants from `chat.js` that do not depend on DOM, state, or backend calls.
2. Pure chat formatting helpers already covered by `test_chat_rendering.js`.
3. Composer palette helpers after tests read the extracted file directly.
4. Personal OS pure prompt/status helpers after `test_personal_os_prompt.js` covers the exact function boundary.
5. Preload/main extraction only after adding targeted static tests for the boundary being moved.

## Pass 1 Extraction

Pass 1 extracts only `_AGENT_PATTERNS` from `frontend/src/chat.js` into `frontend/src/chat_constants.js`.

Behavior intentionally preserved:

- no script modules or bundler
- `chat_constants.js` loads before `chat.js`
- `_needsAgentMode()` still reads `_AGENT_PATTERNS`
- agent auto-detection behavior remains covered by `test_chat_send_guards.js`
- Beta/Internal labels remain in `index.html`

## Pass 2 Extraction

Pass 2 extracts only `stripModelFunctionTags()` and `normalizeChatUrl()` from `frontend/src/chat.js` into `frontend/src/chat_formatting.js`.

Size snapshot before and after Pass 2:

| File | Before Pass 2 | After Pass 2 |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4653 lines / 218734 bytes | 4632 lines / 218103 bytes |
| `frontend/src/chat_formatting.js` | new | 22 lines / 727 bytes |

Tests covering this boundary:

- `test_frontend_script_order_static.js` verifies `chat_formatting.js` loads after `chat_constants.js` and before `chat.js`
- `test_chat_rendering.js` directly checks empty input, function-tag stripping, safe URL acceptance, and unsafe URL rejection
- `test_chat_rendering.js` still exercises the helpers indirectly through `formatMessage()`
- Electron startup and visual smokes verify the classic renderer loads the new script in the app shell

Next safest extraction target: pure markdown block helpers such as table/code/inline rendering helpers, but only after adding direct tests for the exact helper boundary. Streaming, conversation history, tool-call rendering, voice, and Personal OS draft flows remain out of scope.

## Pass 3 Extraction

Pass 3 extracts low-level markdown DOM helpers from `frontend/src/chat.js` into `frontend/src/chat_markdown.js`: `appendInlineMarkdown()`, `appendLineBreak()`, `chatTableCells()`, `isChatTableSeparator()`, `appendChatTable()`, `appendCodeBlock()`, and `isMarkdownBlockStart()`.

Size snapshot before and after Pass 3:

| File | Before Pass 3 | After Pass 3 |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4632 lines / 218103 bytes | 4508 lines / 213344 bytes |
| `frontend/src/chat_markdown.js` | new | 125 lines / 4858 bytes |

Tests covering this boundary:

- `test_frontend_script_order_static.js` verifies `chat_markdown.js` loads after `chat_formatting.js` and before `chat.js`
- `test_chat_rendering.js` directly checks inline markdown, empty input, unsafe HTML/link handling, table rendering, code-block escaping, and block-start detection
- `test_chat_rendering.js` still exercises the helpers indirectly through `formatMessage()`
- Electron startup and visual smokes verify the classic renderer loads the new script in the app shell

Pass 3 left the higher-level `appendMarkdownSegment()`, `appendFormattedMessage()`, and `formatMessage()` group as the next candidate, but only if direct rendering tests stayed stable. Streaming, conversation history, tool-call rendering, voice, Companion execution, and Personal OS draft flows remained out of scope.

## Pass 4 Extraction

Pass 4 probes and then extracts the higher-level message formatting boundary from `frontend/src/chat.js` into `frontend/src/chat_message_formatting.js`: `appendMarkdownSegment()`, `appendFormattedMessage()`, and `formatMessage()`.

Dependency and risk probe:

- Reads: `document`, `stripModelFunctionTags()`, and markdown helpers from `chat_markdown.js`
- Writes: no globals or app state
- DOM: creates transient DOM nodes/fragments for formatted chat output
- Dependencies: calls `chat_formatting.js` through `stripModelFunctionTags()` and calls `chat_markdown.js` helpers for line breaks, inline markdown, tables, code blocks, and block-start detection
- Streaming/history/tool surfaces: used by streaming completion, history hydration, agent summaries, and file-upload/chat rendering through the existing `renderFormattedMessage()` entry point; the extracted functions do not own those flows
- Safety behavior: continues stripping model function tags and escaping unsafe user/model content through text nodes and safe URL checks

Size snapshot before and after Pass 4:

| File | Before Pass 4 | After Pass 4 |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4508 lines / 213344 bytes | 4402 lines / 209933 bytes |
| `frontend/src/chat_message_formatting.js` | new | 107 lines / 3521 bytes |

Tests covering this boundary:

- `test_frontend_script_order_static.js` verifies `chat_message_formatting.js` loads after `chat_markdown.js` and before `chat.js`
- `test_chat_rendering.js` directly checks plain text, empty string, multiline text, tables, function tag stripping, mixed markdown, code escaping, links, and unsafe HTML/script-like inputs
- `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, and Electron smokes cover caller paths that use `renderFormattedMessage()`

Next safest extraction target: pause further chat rendering extraction and review caller clusters around message actions or export helpers before moving more code. Streaming, conversation history, tool-call rendering, voice, Companion execution, and Personal OS draft flows remain out of scope.

## Pass 5 Caller Cluster Review

Pass 5 paused direct rendering extraction and mapped the remaining `chat.js` caller clusters before moving more code. The only extraction performed was the pure answer download formatting helper boundary: `messageExportMarkdownFromText()` and `messageExportFilename()` moved to `frontend/src/chat_export.js`.

Size snapshot before and after Pass 5:

| File | Before Pass 5 | After Pass 5 |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4402 lines / 209933 bytes | 4390 lines / 209340 bytes |
| `frontend/src/chat_export.js` | new | 13 lines / 687 bytes |

Caller cluster map:

| Cluster | Approx. location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Agent attention and local conversation metadata | `setNewConversationControlsBusy()`, `getMessagePersistText()`, `getAgentRunMeta()`, `renderAgentAttentionPanel()`, conversation local helpers near the first quarter of `chat.js` | `LexaState`, `localStorage`, agent metadata, i18n | Yes | Yes | No direct fetch in most helpers | send guards, input wiring, Electron smokes | Medium | Test specific pure metadata helpers before considering any extraction |
| Conversation history lifecycle | `saveChatHistory()`, `persistChatAfterDomMutation()`, `renderPersistedConversationMessages()`, `clearChat()`, conversation switch/delete/load helpers | `LexaState`, `localStorage`, `window.lexa`, message DOM | Yes | Yes | Some conversation APIs | chat rendering, input wiring, Electron smokes | High | Leave in `chat.js` until stronger lifecycle E2E coverage exists |
| Message action buttons | copy, continue, verify, workspace handoff, regenerate, action overflow, action button factories | i18n, `LexaState`, composer state, message DOM | Yes | Yes | Some actions send agent messages | app input wiring, send guards, Electron smokes | Medium | Add direct tests around individual pure prompt/label helpers before extraction |
| Answer download formatting | `messageExportMarkdownFromText()`, `messageExportFilename()` | `Date`, string inputs only | No | No | No | direct send-guard helper tests, script-order static test | Low | Extracted to `chat_export.js` in Pass 5 |
| Answer download action | `exportMessageMarkdown()`, `createMessageExportButton()` | `document`, `Blob`, `URL`, i18n, toast helpers | Temporary button state only | Yes | No | app input wiring, Electron smokes | Medium | Keep in `chat.js`; add browser-level download action coverage before moving |
| Send and streaming lifecycle | `sendMessage()`, streaming chunk handling, abort handling, agent run updates | `LexaState`, provider settings, streaming response state, message DOM | Yes | Yes | Yes | send guards, rendering tests, Electron smokes | High | Do not extract in near term |
| Tool-call and confirmation UI | tool action parsing, confirmation/denial paths, Companion execution prompts | tool state, `window.lexa`, confirmation UI, i18n | Yes | Yes | Yes | send guards and smoke coverage only | High | Document and test first; no extraction yet |
| Composer palette and input wiring | slash-command palette, snippets, input sizing, keyboard/history behavior | `chatInput`, `LexaConfig`, `LexaState`, `localStorage`, i18n | Yes | Yes | No direct fetch | app input wiring, send guards | Medium | Possible future target only for pure command metadata helpers |
| Provider/model UI and file/search helpers | model selector, file upload, search result rendering, model status helpers | `window.lexa`, files/search state, i18n | Yes | Yes | Yes | static wiring and Electron smokes | Medium-high | Test first and leave lifecycle code in `chat.js` |
| Voice hooks | STT/TTS, wake-word/orb hooks, recording/playback state | voice globals, media APIs, backend voice APIs, orb DOM | Yes | Yes | Yes | voice static/settings tests and smokes | High | Out of scope for frontend modularization passes |

Tests covering the Pass 5 extraction:

- `test_chat_send_guards.js` directly checks normal markdown metadata, empty input, default title fallback, multiline source preservation, and stable filenames.
- `test_frontend_script_order_static.js` verifies `chat_export.js` is a classic script loaded after `chat_message_formatting.js` and before `chat.js`.
- `test_app_chat_input_wiring.js` verifies the helper file exists while the DOM download action remains wired in `chat.js`.

Next safest extraction target: do not continue rendering extraction immediately. If another small extraction is needed, target only pure composer command metadata or pure message action prompt helpers after adding direct tests. Streaming, history, tool-call rendering, confirmation UI, voice, Companion execution, and Personal OS draft flows remain intentionally untouched.

## Pass 6 Safe Multi-helper Extraction

Pass 6 extracted three low-risk helper clusters from `frontend/src/chat.js` after adding direct behavior guards for each boundary.

Extracted clusters:

| Cluster | New file | Functions/data moved | Why low risk |
| --- | --- | --- | --- |
| Composer command metadata/search | `frontend/src/chat_composer_helpers.js` | `LEXA_COMPOSER_COMMANDS`, `composerCommandText()`, `composerCommandLabel()`, `composerCommandDesc()`, `composerCommandPrefix()`, `composerCommandAliases()`, `composerCommandAliasKey()`, `composerCommandHintText()`, `composerCommandAliasValues()`, `composerCommandIconSvg()`, `composerCommandMatches()`, `composerCommandScore()`, `composerCommandSearchItems()`, `composerCommandForAlias()`, `expandComposerSlashAlias()` | Reads i18n through `t()` and static command data; does not mutate state, touch DOM, call backend/fetch, or own command palette lifecycle |
| Answer action prompt builders | `frontend/src/chat_message_actions.js` | `workspaceDraftPromptFromText()`, `continuePromptFromText()`, `verifyAnswerPromptFromText()` | Builds strings from source text, composer prefixes, i18n, and `LexaConfig`; does not mutate state, touch DOM, call backend/fetch, or start agent runs |
| Chat input metrics | `frontend/src/chat_input_helpers.js` | `chatInputMetrics()` | Pure counter/threshold calculation from input text and config; DOM sizing and class updates remain in `syncChatInputSize()` |

Size snapshot before and after Pass 6:

| File | Before Pass 6 | After Pass 6 |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4390 lines / 209339 bytes | 4218 lines / 192304 bytes |
| `frontend/src/chat_composer_helpers.js` | new | 117 lines / 13918 bytes |
| `frontend/src/chat_message_actions.js` | new | 41 lines / 2753 bytes |
| `frontend/src/chat_input_helpers.js` | new | 17 lines / 673 bytes |

Tests covering Pass 6:

- `test_chat_send_guards.js` now directly checks empty/default input metrics, exact danger threshold behavior, empty prompt inputs, multiline/special-text preservation for prompt builders, composer fallback text behavior, and icon fallback behavior.
- `test_frontend_script_order_static.js` verifies the new helper files are classic scripts loaded after prior chat helpers and before `chat.js`, and verifies `chat.js` consumes the extracted globals without redefining them.
- `test_app_chat_input_wiring.js` verifies UI callers remain wired in `chat.js` while command metadata and prompt helpers live in the helper files.

Current chat script order:

1. `chat_constants.js`
2. `chat_formatting.js`
3. `chat_markdown.js`
4. `chat_message_formatting.js`
5. `chat_export.js`
6. `chat_composer_helpers.js`
7. `chat_message_actions.js`
8. `chat_message_actions_controller.js`
9. `chat_input_helpers.js`
10. `chat_tool_confirmation_ui.js`
11. `chat_tool_display_ui.js`
12. `chat_confirmation_state.js`
13. `chat_history_ui.js`
14. `chat_streaming_helpers.js`
15. `chat_file_display_ui.js`
16. `chat.js`

Remaining high-risk clusters: streaming send/abort, conversation history switching/deletion/persistence orchestration, real tool execution/result lifecycle, confirmation approval execution, Companion execution, voice/STT/TTS/orb behavior, Personal OS draft apply/approve/reject flows, Electron preload IPC, Electron backend lifecycle, signing/update behavior, and OS cleanup.

Stop-line: do not extract streaming, send pipeline, conversation switch/load/delete lifecycle, real tool execution/result lifecycle, or confirmation approval execution until direct E2E or stronger integration coverage exists for those lifecycle paths.

## Internal Stability Sprint: Tool/History Coverage and Confirmation UI Split

This sprint added focused renderer coverage first, then extracted only the duplicated render-only confirmation surface into `frontend/src/chat_tool_confirmation_ui.js`.

Coverage added:

- `tests/electron_tool_confirmation_smoke.js` loads the real renderer with isolated Electron `userData`, clicks the real send button, mocks only `/chat/stream`, and verifies a streamed `rc: true` action renders confirmation language, command/parameter text, confirm/deny controls, and escaped unsafe params without clearing or executing pending tools.
- The same smoke calls `addMessage(..., action, true, true)` to cover direct render-only confirmation UI.
- The history portion verifies persisted messages restore in order, assistant Markdown remains formatted, action-like persisted messages do not become live confirmation controls, the selected conversation row is marked, title/preview text renders safely, and the empty history state appears.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4512 lines / 192304 bytes | 4466 lines / 189992 bytes |
| `frontend/src/chat_tool_confirmation_ui.js` | new | 40 lines / 1388 bytes |

Moved function:

- `appendToolConfirmationUi(body, action)`

What stayed in `chat.js`:

- `confirmAction()`
- `denyAction()`
- streaming state and parser behavior
- send pipeline behavior
- history switch/load/delete lifecycle
- Companion/tool execution calls
- voice/STT/TTS behavior
- Personal OS draft behavior

Tests covering this boundary:

- `electron_tool_confirmation_smoke.js`
- `electron_core_chat_flow_smoke.js`
- `test_frontend_script_order_static.js`
- `test_chat_rendering.js`
- `test_chat_send_guards.js`
- `test_app_chat_input_wiring.js`
- Electron startup and visual smokes

Next recommended larger target: add a focused renderer smoke for mocked confirmation denial/approval clicks before moving any approval execution UI, or add focused conversation switch/load/delete smokes before extracting history lifecycle helpers. Do not split streaming or send pipeline code yet.

## History Lifecycle Coverage and History UI Extraction

This sprint added focused history lifecycle coverage first, then extracted only conversation sidebar render helpers into `frontend/src/chat_history_ui.js`.

Coverage added:

- `tests/electron_history_lifecycle_smoke.js` loads the real renderer with isolated Electron `userData` and the existing smoke mock bridge.
- It verifies the initial empty history state, mocked conversation sidebar rows, safe title/preview rendering, selected row state, `switchConversation()` hydration order, Markdown formatting after history load, unsafe HTML containment, action-like persisted messages not becoming live tool controls, switching between two conversations, and deleting an inactive mocked conversation.
- The delete assertion is limited to mocked bridge data and an inactive conversation. Real data deletion and active-conversation recovery remain out of scope for this pass.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4466 lines / 189992 bytes | 4406 lines / 186353 bytes |
| `frontend/src/chat_history_ui.js` | new | 100 lines / 4443 bytes |

Moved functions:

- `conversationListDisplayTitle(conversation)`
- `conversationListPreviewText(conversation)`
- `renderConversationEmptyState(container, message)`
- `createConversationListItem(conversation, options)`

What stayed in `chat.js`:

- `loadChatHistory()`
- `renderPersistedConversationMessages()`
- `switchConversation()`
- `saveCurrentConversation()`
- `deleteConversation()`
- conversation backend calls
- local storage and active-conversation orchestration
- streaming and send pipeline behavior

Tests covering this boundary:

- `electron_history_lifecycle_smoke.js`
- `electron_core_chat_flow_smoke.js`
- `electron_tool_confirmation_smoke.js`
- `test_frontend_script_order_static.js`
- `test_chat_rendering.js`
- `test_chat_send_guards.js`
- `test_app_chat_input_wiring.js`
- Electron startup and visual smokes

Next recommended target: after the history failure and mocked confirmation click smokes are stable, consider only pure confirmation state helpers or history fallback helpers. Streaming and send pipeline remain stop-lined.

## History Failure and Confirmation Click Coverage Sprint

This sprint added failure-path coverage first, fixed one small malformed-history bug, and extracted only the pure confirmation prompt summary helper.

Coverage added:

- `tests/electron_history_failure_smoke.js` loads the real renderer with isolated Electron `userData` and covers malformed sidebar conversations, missing title/preview fields, unsafe title/preview/message content, malformed persisted messages, failed conversation load preserving the active transcript, invalid local-history recovery, and stable empty-history recovery.
- `tests/electron_confirmation_click_smoke.js` covers mocked approval, denial, and window-cancel confirmation clicks. It asserts pending confirmation is cleared exactly once, unsafe params remain escaped, the confirmation prompt contains the expected safe command summary, and only mocked bridge handlers are called.

Bug fixed:

- `frontend/src/chat_history_ui.js` now normalizes missing conversation titles and previews before rendering. This prevents malformed history payloads from crashing the sidebar while preserving normal conversation rendering.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4114 lines / 186353 bytes | 4107 lines / 186009 bytes |
| `frontend/src/chat_history_ui.js` | 84 lines / 4443 bytes | 91 lines / 4660 bytes |
| `frontend/src/chat_confirmation_state.js` | new | 14 lines / 569 bytes |

Moved function:

- `confirmationActionSummaryText(action, prepared)`

Why this boundary was safe:

- It is a pure string builder for the existing `window.confirm()` prompt.
- It reads only the passed action/prepared confirmation payloads.
- It does not mutate state, touch DOM, call fetch/backend APIs, or execute Companion.
- `electron_confirmation_click_smoke.js` covers the approval and cancel prompt summary behavior after the extraction.

What stayed in `chat.js`:

- `confirmAction()` approval/denial execution flow
- pending confirmation clear call
- `prepareCompanionExecute()` and `executeWithConfirmation()` calls
- streaming and send pipeline behavior
- history save/load/delete orchestration
- real tool and Companion execution

Current chat script order:

1. `chat_constants.js`
2. `chat_formatting.js`
3. `chat_markdown.js`
4. `chat_message_formatting.js`
5. `chat_export.js`
6. `chat_composer_helpers.js`
7. `chat_message_actions.js`
8. `chat_input_helpers.js`
9. `chat_tool_confirmation_ui.js`
10. `chat_tool_display_ui.js`
11. `chat_confirmation_state.js`
12. `chat_history_ui.js`
13. `chat_streaming_helpers.js`
14. `chat.js`

Next recommended target: add focused streaming abort/timeout/chunk-boundary smoke before any streaming extraction, or add a render-only non-confirmed tool display smoke. Do not move history orchestration, send pipeline, real tool execution, or confirmation approval execution yet.

## Streaming Robustness Coverage and Parser Helper Extraction

This sprint added focused streaming robustness coverage first, then extracted only the pure stream parser helpers into `frontend/src/chat_streaming_helpers.js`.

Coverage added:

- `tests/electron_streaming_robustness_smoke.js` loads the real renderer with isolated Electron `userData`, clicks the real send button, and mocks only `/chat/stream`.
- It covers assistant content split across underlying stream chunks, markdown split across chunks, split code/table/link rendering, unsafe HTML containment, malformed SSE events, malformed JSON payloads, stream completion without a final marker, stream read errors, user abort during streaming, simulated timeout before response, no duplicate assistant messages, and composer/control recovery.
- `tests/test_chat_streaming_helpers.js` directly checks buffered line splitting and `data: ` JSON event parsing, including ignored non-data lines and malformed JSON returning `null` without throwing.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4107 lines / 186009 bytes | 4104 lines / 185894 bytes |
| `frontend/src/chat_streaming_helpers.js` | new | 19 lines / 571 bytes |

Moved functions:

- `chatStreamBufferedLines(buffer)`
- `parseChatStreamDataLine(line)`

Why this boundary was safe:

- It reads only the passed buffer or line.
- It does not mutate renderer state, touch DOM, fetch backend data, own `AbortController`, trigger tool execution, or persist history.
- It preserves the existing `data: ` line requirement and malformed JSON warning behavior.
- The new streaming smoke covers the same parser edge through the real send path, and the direct helper test covers the pure helper behavior.

What stayed in `chat.js`:

- `sendMessage()`
- fetch orchestration and request body
- timeout/abort ownership
- stream render scheduling
- final response rendering
- tool-call and confirmation handling
- history persistence
- send button/composer state recovery

Current chat script order:

1. `chat_constants.js`
2. `chat_formatting.js`
3. `chat_markdown.js`
4. `chat_message_formatting.js`
5. `chat_export.js`
6. `chat_composer_helpers.js`
7. `chat_message_actions.js`
8. `chat_input_helpers.js`
9. `chat_tool_confirmation_ui.js`
10. `chat_tool_display_ui.js`
11. `chat_confirmation_state.js`
12. `chat_history_ui.js`
13. `chat_streaming_helpers.js`
14. `chat.js`

Next recommended target: add a settings persistence smoke before settings modularization, or add a render-only file upload result smoke. The full streaming lifecycle, send pipeline, and real tool execution remain stop-lined.

## Tool Display Coverage and Display Helper Extraction

This sprint added render-only non-confirmed tool display coverage first, then extracted only the pure tool-result display text helper into `frontend/src/chat_tool_display_ui.js`.

Coverage added:

- `tests/electron_tool_display_smoke.js` loads the real renderer with isolated Electron `userData`, clicks the real send button, and mocks only `/chat/stream`; the tool execution path uses the existing Electron smoke bridge only.
- It covers non-confirmed mocked tool result display replacing placeholder text, unsafe result content remaining contained, no confirmation controls/action cards for non-confirmed display, no-result tool output keeping safe placeholder text, composer/control recovery, and persisted tool-like history content not creating live controls.
- `tests/test_chat_tool_display_helpers.js` directly covers `toolResultDisplayText()` for string results, summary/message/error precedence, fallback key-value formatting, skipped internal fields, empty unsupported data, and unsafe text staying plain text for renderer formatting.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4104 lines / 185894 bytes | 4083 lines / 184875 bytes |
| `frontend/src/chat_tool_display_ui.js` | new | 18 lines / 608 bytes |

Moved function:

- `toolResultDisplayText(data)`

Why this boundary was safe:

- It reads only the passed tool result data.
- It does not mutate state, touch DOM, fetch backend data, execute tools, trigger confirmation, persist history, or own send/streaming lifecycle.
- It preserves existing result precedence: string data, then `summary`, `message`, `error`, then fallback key-value pairs while skipping internal display fields.
- The new smoke covers the display path through the real send flow with mocked tool execution, and the direct helper test covers the pure formatter behavior.

What stayed in `chat.js`:

- `window.lexa.execute()` calls
- success/failure branching
- active message rendering
- toast and notification behavior
- history persistence
- confirmation approval/denial execution
- send pipeline and streaming lifecycle

Current chat script order:

1. `chat_constants.js`
2. `chat_formatting.js`
3. `chat_markdown.js`
4. `chat_message_formatting.js`
5. `chat_export.js`
6. `chat_composer_helpers.js`
7. `chat_message_actions.js`
8. `chat_input_helpers.js`
9. `chat_tool_confirmation_ui.js`
10. `chat_tool_display_ui.js`
11. `chat_confirmation_state.js`
12. `chat_history_ui.js`
13. `chat_streaming_helpers.js`
14. `chat.js`

Next recommended target: settings persistence smoke before settings modularization, or a render-only file upload result smoke. Real tool execution and confirmation execution remain stop-lined.

## Settings Persistence Coverage and Helper Extraction

This sprint moved outside `chat.js` and added focused coverage for the Settings local preference surface before extracting pure helpers.

Settings responsibility map:

| Cluster | Approx. location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch/IPC | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Local appearance and language preferences | `loadLanguagePreference()`, `changeLanguage()`, `toggleTheme()`, `setAccentColor()`, `setFontSize()`, `loadThemePreferences()` | `localStorage`, `document`, `LexaI18n`, `t()` | Yes, localStorage/document attributes only | Yes | i18n load only for language | `electron_settings_persistence_smoke.js`, `test_settings_helpers.js`, script-order static test | Low | Extracted pure normalization helpers; keep behavior in `settings.js` |
| Settings view refresh and readiness | `refreshSettingsView()`, `renderSystemReadiness()`, diagnostics helpers | `LexaState`, `window.lexa`, settings DOM, i18n | Yes | Yes | Backend/mock bridge calls | visual/startup smokes, settings voice static | Medium | Test first; extract only pure formatting helpers later |
| Provider/model settings | `loadModelSelection()`, `changeAiModel()`, provider status rows | `window.lexa`, model select, provider state | Yes | Yes | Backend calls | static checks and visual smoke | Medium-high | Add keyring-safe/provider-safe smoke before extraction |
| Voice/STT/TTS settings | voice diagnostics, STT model/engine, ElevenLabs settings, microphone/TTS tests | media APIs, `window.lexa`, voice globals | Yes | Yes | Backend/voice APIs and key actions | `test_settings_voice_static.js`, visual smoke | High | Stop-line; do not extract runtime behavior yet |
| Keyring/API key controls | Cartesia, ElevenLabs, Deepgram key set/delete actions | `showInputModal`, `window.lexa`, secret bridge policy | Yes | Yes | Secret/keyring bridge calls | bridge policy/static tests | High | Stop-line; do not touch without dedicated secret-safe coverage |
| License display and activation | `loadLicenseStatus()`, `activateLicense()`, `removeLicense()` | `window.lexa`, license DOM, modal input | Yes | Yes | IPC and validation calls | release blocker docs, static readiness labels | High | Stop-line; PublicRC/PublicRelease decision remains external |
| Profile, backup, Hermes controls | `saveProfile()`, backup controls, Hermes autostart controls | `window.lexa`, settings DOM, backend state | Yes | Yes | Backend/IPC bridge calls | Hermes static/visual smokes | Medium-high | Test first; leave orchestration in `settings.js` |

Coverage added:

- `tests/electron_settings_persistence_smoke.js` loads the real renderer, exercises only local settings preferences, asserts persistence/hydration, corrupt localStorage recovery, unknown-key preservation, unsafe value containment, no renderer `fetch()` calls, and stable Beta/Internal chips.
- `tests/test_settings_helpers.js` directly checks the pure helper boundary for valid/invalid theme, accent, font-size, and language values.
- `tests/test_frontend_script_order_static.js` verifies `settings_helpers.js` is a classic script loaded after `personal_os.js` and before `settings.js`.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/settings.js` | 1191 lines / 54258 bytes in the Git blob | 1195 lines / 54423 bytes |
| `frontend/src/settings_helpers.js` | new | 25 physical lines / 875 bytes |

Moved functions:

- `settingsSafeChoice(value, allowedValues, fallback)`
- `settingsSafeTheme(theme)`
- `settingsSafeAccent(accent)`
- `settingsSafeFontSize(size)`
- `settingsSafeLanguage(lang)`

Small robustness fix:

- corrupt stored `lexa-theme`, `lexa-accent`, `lexa-fontsize`, and `lexa-lang` values now recover to safe defaults instead of applying arbitrary stored strings to the UI shell.

What stayed in `settings.js`:

- Settings refresh/orchestration
- provider/model calls
- keyring/API-key actions
- voice/STT/TTS runtime behavior
- license activation/removal
- profile save
- backup controls
- Hermes autostart controls
- Electron IPC and backend bridge calls

Current tail script order:

1. `personal_os.js`
2. `settings_helpers.js`
3. `settings.js`
4. `devtools.js`

Next recommended target: provider/model settings UI coverage with keyring-safe mocks, or one more pure settings display formatter only after direct tests. Secrets/keyring, voice runtime, license activation, backend/provider calls, Electron IPC, chat lifecycle, and OS drafts remain stop-lined.

## Provider/Model Settings Coverage and Helper Extraction

This sprint added keyring-safe provider/model settings coverage and moved the settings-owned model selector handlers out of `frontend/src/chat.js`.

Provider/model settings responsibility map:

| Cluster | Location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch/IPC | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Provider status rows | `refreshSettingsView()` in `settings.js` | `LexaState`, `window.lexa.aiStatus()`, status row DOM, i18n | DOM only | Yes | Smoke bridge/backend status read | `electron_provider_settings_smoke.js`, visual smokes | Medium | Keep render-only; do not mix with API-key/keyring actions |
| AI model selection display | `settings_provider_helpers.js`, `loadModelSelection()` in `settings.js` | `window.lexa.aiModels()`, `model-select`, `model-desc` | DOM only | Yes | Smoke bridge/backend model read | `electron_provider_settings_smoke.js`, `test_settings_provider_helpers.js` | Low-medium | Keep helper boundary; add backend contract tests before changing API payload shape |
| AI model change action | `changeAiModel()` in `settings.js` | `window.lexa.setAiModel()`, toast, `model-desc` | Backend-selected model through bridge | Yes | Mocked write bridge only in smoke | `electron_provider_settings_smoke.js` | Medium | Keep keyring-safe smoke in gates before UI changes |
| API-key/keyring controls | Cartesia, ElevenLabs, Deepgram key set/delete actions in `settings.js` | modal input, secret bridge policies, key storage backend | Yes | Yes | Secret/keyring bridge calls | bridge policy/static tests only | High | Stop-line; do not touch without dedicated secret-safe coverage and explicit user intent |
| Provider/backend contracts | `/ai/models`, provider health/status, provider fallback | backend provider code and configured secrets | Yes | No direct DOM | Real backend/provider calls | Python provider/router tests, smoke mocks | High | Do not change contracts in frontend maintainability passes |

Coverage added:

- `tests/electron_provider_settings_smoke.js` loads the real renderer with isolated Electron `userData` and the existing smoke bridge.
- It verifies provider status rows, model selector hydration, safe mocked model change, unsafe provider/model label containment, no renderer fetch calls, no secret-like values in the settings path, no keyring/API-key bridge calls, no presence challenge requests, redacted bridge audit metadata, and no fatal renderer errors.
- `tests/test_settings_provider_helpers.js` directly covers provider/model option normalization, grouped and flat options, malformed payload recovery, description text, active option selection, inert unsafe label rendering, and classic-script constraints.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/settings.js` | 1310 lines / 54423 bytes | 1334 lines / 55367 bytes |
| `frontend/src/chat.js` | 4375 lines / 184875 bytes | 4337 lines / 183080 bytes |
| `frontend/src/settings_provider_helpers.js` | new | 56 lines / 1916 bytes |

Moved responsibility:

- `loadModelSelection()` moved from `chat.js` to `settings.js`.
- `changeAiModel()` moved from `chat.js` to `settings.js`.

Extracted provider/model display helpers:

- `settingsAiModelEntries(models)`
- `settingsAiModelHasAvailableData(data)`
- `settingsAiModelFlatOptions(data)`
- `settingsAiModelGroupedOptions(data)`
- `settingsAiModelDescriptionText(data)`
- `settingsRenderAiModelSelection(data, select, desc)`

Small robustness improvement:

- malformed provider/model payloads now normalize to empty options instead of allowing unexpected non-object values into the selector rendering path. Normal backend payload behavior is unchanged.

What stayed out of scope:

- API-key save/load/delete actions
- real keyring/secret access
- real provider/network calls
- voice/STT/TTS runtime behavior
- license activation/removal
- Electron main/preload IPC
- chat send/streaming/history/tool behavior

Current tail script order:

1. `personal_os.js`
2. `settings_helpers.js`
3. `settings_provider_helpers.js`
4. `settings.js`
5. `devtools.js`

Next recommended target from this point was a render-only file upload result smoke, now covered in the following section. Secrets/keyring, provider backend writes, license activation, voice runtime, Electron IPC, and OS drafts remained stop-lined.

## File Upload / Attachment Result Coverage and Helper Extraction

This sprint added render-only coverage for file upload cards, file result badges, and attachment-like history content before extracting only small display metadata helpers.

File/attachment responsibility map:

| Cluster | Location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch/IPC | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| File metadata display | `chat_file_display_ui.js` | passed file/file-info payloads, `t()` for line count label | No | No | No | `test_chat_file_display_helpers.js`, `electron_file_upload_result_smoke.js` | Low | Keep extracted; adjust only with direct helper tests |
| Upload card rendering | `buildFileUploadCard()`, `addFileUploadMessage()` in `chat.js` | file object, `chatMessages`, DOM helper functions | DOM only | Yes | No | `electron_file_upload_result_smoke.js`, `test_chat_send_guards.js` | Low-medium | Keep render-only; do not mix with upload execution |
| File result badge/rendering | `buildFileInfoBadge()`, `addFileUploadResponse()` in `chat.js` | file result payload, `addMessage()`, chat DOM | DOM only | Yes | No direct fetch | `electron_file_upload_result_smoke.js`, `test_chat_file_display_helpers.js`, `test_chat_send_guards.js` | Low-medium | Keep display-only; provider status badges are covered directly |
| Upload orchestration | `handleFileUpload()` in `chat.js`, `/chat/file` in `backend/router_chat.py` | `LexaState`, `window.lexa.chatFile()`, title/history, send button, TTS, backend upload contract | Yes | Yes | Backend bridge call and safe upload fixture tests | `test_router_chat_file_upload_vision.py`, static guards | Medium-high | Keep orchestration small; real provider/API work remains stop-lined until API selection is configured |
| Attachment-like history | `renderPersistedConversationMessages()` | history payloads, message formatter | DOM only | Yes | No | `electron_file_upload_result_smoke.js`, history smokes | Medium | Keep history orchestration in `chat.js` |

Coverage added:

- `tests/electron_file_upload_result_smoke.js` loads the real renderer with isolated Electron `userData` and uses in-memory `File` objects only.
- It verifies safe filename rendering, file extension/size metadata, file result badge text, provider-required image fallback text, unsafe result content containment, failed result display safety, attachment-like history not becoming live controls, no executable nodes, no renderer fetch calls, and no upload/tool/provider/OS bridge methods.
- `tests/electron_vision_readiness_smoke.js` verifies screenshot analysis does not enter the critical `visionAnalyze` confirmation path when no Vision provider is configured.
- `tests/test_chat_file_display_helpers.js` directly covers size labels, extension fallback, unsafe suffix handling, badge text with line counts and analysis status, missing payloads, unsafe text preservation for renderer escaping, and classic-script constraints.
- `tests/test_router_chat_file_upload_vision.py` covers the backend `/chat/file` split between image Vision readiness and existing text-file analysis.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4337 lines / 183080 bytes | 4322 lines / 182551 bytes |
| `frontend/src/chat_file_display_ui.js` | new | 22 lines / 757 bytes |

Moved functions:

- `fileUploadSizeLabel(file)`
- `fileUploadExtension(file)`
- `fileInfoBadgeText(fileInfo)`

Why this boundary was safe:

- It reads only passed display payloads.
- It does not touch DOM directly, call fetch/backend APIs, read files, write files, execute Companion, create OS drafts, or own upload/send/stream/history lifecycle.
- Existing card and badge rendering still insert text through `textContent`.

What stayed in `chat.js`:

- `handleFileUpload()`
- `buildFileUploadCard()`
- `addFileUploadMessage()`
- `buildFileInfoBadge()`
- `addFileUploadResponse()`
- backend upload calls through `window.lexa.chatFile()`
- automatic title/history persistence
- action execution after upload responses
- TTS and send/loading state

Current chat script order:

1. `chat_constants.js`
2. `chat_formatting.js`
3. `chat_markdown.js`
4. `chat_message_formatting.js`
5. `chat_export.js`
6. `chat_composer_helpers.js`
7. `chat_message_actions.js`
8. `chat_input_helpers.js`
9. `chat_tool_confirmation_ui.js`
10. `chat_tool_display_ui.js`
11. `chat_confirmation_state.js`
12. `chat_history_ui.js`
13. `chat_streaming_helpers.js`
14. `chat_file_display_ui.js`
15. `chat.js`

Next recommended target at the time was provider/model backend contract coverage with fake provider responses, or a read-only Personal OS cockpit smoke. Those areas now have separate coverage; real provider/API selection and full Vision behavior remain a future functional milestone.

## Read-only Personal OS Cockpit Coverage and Display Helper Extraction

This sprint moved to another visible internal area and added read-only cockpit coverage before extracting only pure Personal OS display helpers.

Personal OS read-only responsibility map:

| Cluster | Location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch/IPC | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Display text/status helpers | `personal_os_display_helpers.js` | passed values, optional `t()`/i18n globals | No | No | No | `test_personal_os_prompt.js`, `electron_personal_os_readonly_smoke.js`, script-order static test | Low | Keep extracted; change only with direct helper tests |
| Cockpit status and queue rendering | `renderPersonalOsStatus()`, `renderPersonalOsDraftList()` in `personal_os.js` | `PersonalOSState`, diagnostics/queue payloads, DOM | Yes, renderer state only | Yes | No direct fetch | `electron_personal_os_readonly_smoke.js`, `test_personal_os_prompt.js` | Medium | Keep render helpers in `personal_os.js` until more view-state coverage exists |
| Context query, context pack, and graph display | `renderPersonalOsQueryPayload()`, `renderPersonalOsContextPack()`, `renderPersonalOsGraphPayload()` | payloads, graph helper functions, DOM | Yes, selected context state | Yes | No direct fetch | `electron_personal_os_readonly_smoke.js`, graph/static prompt tests | Medium | Test more direct render edge cases before extraction |
| Personal OS bridge reads | `refreshPersonalOsView()`, context/load functions | `window.lexa.personalOs*` read methods | Yes | Yes | Smoke bridge or backend read calls | smoke bridge coverage only | Medium-high | Do not refactor until read-call failure coverage is focused |
| Personal OS writes and SDK decisions | `decidePersonalOsDraft()`, `applyPersonalOsDraft()`, `submitPersonalOsRawInbox()` | modal input, SDK/backend write paths, bridge risk policy | Yes | Yes | Write/admin bridge calls | backend/router/OS gate tests only | High | Stop-line; no approve/reject/apply/raw-submit extraction in maintainability passes |

Coverage added:

- `tests/electron_personal_os_readonly_smoke.js` opens the real Personal OS view with isolated Electron `userData`, renders mocked read-only status, draft, context, context pack, graph, empty, and error states, verifies unsafe OS-like content remains contained, and verifies no write/tool/provider/secret bridge methods or renderer `fetch()` calls occur.
- `tests/test_personal_os_prompt.js` now reads the display helper file directly and adds direct guards for status/event/assist classes, state labels, and draft status labels.
- `tests/test_frontend_script_order_static.js` verifies `personal_os_display_helpers.js` is a classic script loaded after `memory.js` and before `personal_os.js`.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/personal_os.js` | 2492 lines / 117869 bytes | 2371 lines / 112058 bytes |
| `frontend/src/personal_os_display_helpers.js` | new | 122 lines / 5891 bytes |

Moved functions:

- `posText()`
- `posUiText()`
- `posUiCount()`
- `posStatusClass()`
- `posEventClass()`
- `posAssistClass()`
- `posErrorDetailText()`
- `posErrorMessage()`
- `posClip()`
- `posRefreshLabel()`
- `posStateLabel()`
- `posDraftStatusText()`

Why this boundary was safe:

- It is pure display/text formatting.
- It does not touch DOM directly, call the Personal OS SDK, fetch backend data, read/write files, create/approve/reject/apply drafts, run cleanup, execute Companion, or call providers.
- Existing prompt/static tests already covered most helper behavior, and the new smoke covers the visible cockpit display path.

Current tail script order:

1. `memory.js`
2. `personal_os_display_helpers.js`
3. `personal_os_review_helpers.js`
4. `personal_os.js`
5. `settings_helpers.js`
6. `settings_provider_helpers.js`
7. `settings.js`
8. `devtools.js`

What stayed in `personal_os.js`:

- refresh orchestration
- bridge reads and all bridge writes
- draft selection, review, approve/reject/apply behavior
- raw inbox submit behavior
- context file reads and chat handoff
- graph DOM event handlers
- all SDK write boundaries

Next recommended target at the time: a mocked Personal OS chat-handoff/review smoke that verifies prompt placement without approving, rejecting, applying, raw-submitting, cleaning up, or touching real OS files. That target is addressed in the following section; OS drafts, OS cleanup, filesystem writes, Companion execution, SDK writes, Electron IPC, and provider calls remain stop-lined.

## Personal OS Chat-Handoff and Draft Review Smoke

This sprint added mocked coverage for chat handoff and draft-review display before extracting only display-only review hint helpers.

Personal OS handoff/review responsibility map:

| Cluster | Location/functions | Dependencies/globals | Mutates state | Touches DOM | Backend/fetch/IPC | Current coverage | Risk | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Review hint display helpers | `personal_os_review_helpers.js`: `renderPosApplyHint()`, `renderPosPromptHint()` | passed draft/review payloads, `escapeHtml()`, `posText()`, `posUiText()`, `personalOsReviewPromptMeta()`, `posMeterWidthClass()` | No | Returns display HTML only | No | `electron_personal_os_handoff_smoke.js`, `test_personal_os_prompt.js`, script-order static test | Low | Keep extracted; change only with direct display/handoff tests |
| Chat handoff prompt placement | `personalOsPlacePromptInChat()`, `personalOsSendContextToChat()`, `personalOsSendReviewToChat()` | `chatInput`, `switchView()`, local chat draft storage, toast helpers | Yes, composer state only | Yes | No | `electron_personal_os_handoff_smoke.js`, `test_personal_os_prompt.js` | Medium | Keep in `personal_os.js`; do not auto-send or route to providers |
| Draft review display | `renderPersonalOsDetail()` and review render helpers in `personal_os.js` | `PersonalOSState`, selected draft/review payloads, DOM | Yes, renderer state only | Yes | No direct fetch | `electron_personal_os_handoff_smoke.js`, `electron_personal_os_readonly_smoke.js` | Medium | Add read-call failure coverage before moving larger display regions |
| Draft write controls | `decidePersonalOsDraft()`, `applyPersonalOsDraft()`, `submitPersonalOsRawInbox()` | modal input, SDK/backend write paths, bridge risk policy | Yes | Yes | Write/admin bridge calls | backend/router/OS gate tests only | High | Stop-line; no approve/reject/apply/raw-submit extraction in maintainability passes |

Coverage added:

- `tests/electron_personal_os_handoff_smoke.js` opens the real Personal OS view with isolated Electron `userData`, renders mocked context and draft-review payloads, clicks only context-to-chat and review-to-chat display/handoff controls, and verifies prompts are placed in the chat composer without auto-sending.
- The smoke verifies unsafe context, draft, review, path, and diff text stays contained; draft-review prompt text includes no-auto-decision guidance; no renderer `fetch()` calls or chat send calls occur; and no Personal OS decision/apply/raw-submit, Companion/tool, provider, or secret bridge methods are called.
- `tests/test_frontend_script_order_static.js` verifies `personal_os_review_helpers.js` is a classic script loaded after `personal_os_display_helpers.js` and before `personal_os.js`.
- `tests/test_personal_os_prompt.js` reads the review helper file directly so localized review/apply hint labels remain covered after extraction.

Extraction completed:

| File | Before sprint | After sprint |
| --- | ---: | ---: |
| `frontend/src/personal_os.js` | 2371 lines / 112058 bytes | 2337 lines / 110749 bytes |
| `frontend/src/personal_os_review_helpers.js` | new | 35 lines / 1396 bytes |

Moved functions:

- `renderPosApplyHint(review)`
- `renderPosPromptHint(draft, review)`

Why this boundary was safe:

- It is display-only hint generation for already-rendered review payloads.
- It does not read/write OS files, call the Personal OS SDK, create/approve/reject/apply drafts, raw-submit inbox items, run cleanup, execute Companion, call providers, call `fetch()`, or own chat send/stream/history behavior.
- The new smoke covers the visible handoff/review surfaces while explicitly avoiding write-capable controls.

Current UI behavior documented by the smoke:

- pending draft approve/reject controls are visible according to existing behavior and are not clicked by this smoke
- apply remains disabled for the mocked pending draft
- the chat-review control is enabled only because a mocked review package is present

What stayed in `personal_os.js`:

- draft selection and detail state
- bridge reads and all bridge writes
- approve/reject/apply behavior
- raw inbox submit behavior
- context file reads and all chat handoff orchestration
- prompt construction and prompt clipping
- graph DOM event handlers and SDK write boundaries

Current tail script order:

1. `memory.js`
2. `personal_os_display_helpers.js`
3. `personal_os_review_helpers.js`
4. `personal_os.js`
5. `settings_helpers.js`
6. `settings_provider_helpers.js`
7. `settings.js`
8. `devtools.js`

Next recommended target: a Personal OS read-call failure smoke or provider/model backend contract coverage with fake provider responses. OS drafts, OS cleanup, approve/reject/apply/raw-submit, filesystem writes, Companion execution, SDK writes, Electron IPC, and provider calls remain stop-lined.

## Chat Architecture Upgrade Pass 1

This pass chose the message action controller boundary because it is a visible, coherent responsibility already covered by focused renderer and static tests. It moves the answer-action controller surface out of `frontend/src/chat.js` while leaving send, stream, history, tool execution, confirmation approval, provider, voice, and Personal OS write lifecycles untouched.

Boundary moved to `frontend/src/chat_message_actions_controller.js`:

- message action icon setup and overflow menu behavior
- workspace draft handoff button creation and guarded start path
- continue-from-answer prompt placement
- verify-answer handoff button creation and guarded start path
- save-as-memory button behavior
- previous user prompt lookup for regenerate
- regenerate button guarded start path
- button feedback flash behavior
- copy-to-clipboard fallback and copy helpers
- markdown export button behavior

Moved functions:

- `setIconButton()`
- `setMessageActionMenuOpen()`
- `closeMessageActionMenus()`
- `ensureMessageActionMenuDismiss()`
- `createMessageActionOverflowMenu()`
- `startWorkspaceDraftFromMessage()`
- `createWorkspaceHandoffButton()`
- `startContinueFromMessage()`
- `createContinueFromMessageButton()`
- `startVerifyAnswerFromMessage()`
- `createVerifyAnswerButton()`
- `saveMessageAsMemory()`
- `previousUserPromptForMessage()`
- `startRegenerateMessage()`
- `flashIconButton()`
- `copyTextToClipboard()`
- `copyCode()`
- `copyMessage()`
- `exportMessageMarkdown()`
- `createMessageExportButton()`

Size snapshot before and after Chat Architecture Upgrade Pass 1:

| File | Before pass | After pass |
| --- | ---: | ---: |
| `frontend/src/chat.js` | 4322 lines / 180895 chars | 3958 lines / 169032 chars |
| `frontend/src/chat_message_actions_controller.js` | new | 363 lines / 13516 chars |

Tests covering this boundary:

- `tests/electron_message_actions_smoke.js` loads the real renderer with isolated Electron `userData`, renders real assistant action buttons, and uses mocks/spies for clipboard, export download, agent handoff, regenerate, and renderer `fetch()`.
- The smoke verifies copy, export, continue, verify, workspace, and regenerate action behavior without real provider calls, Companion execution, OS writes, or network calls.
- `tests/test_app_chat_input_wiring.js` verifies the message-action call sites still exist and that controller-owned helpers preserve raw Markdown fidelity, accepted feedback, overflow behavior, memory/save failure handling, and regenerate prompt recovery.
- `tests/test_chat_send_guards.js` verifies regenerate uses the guarded shared handler from the new controller.
- `tests/test_frontend_script_order_static.js` verifies `chat_message_actions_controller.js` is a classic script loaded after prompt helpers and before `chat.js`.

What stayed in `chat.js`:

- message rendering and DOM insertion
- `sendMessage()` and the send pipeline
- streaming fetch/abort/recovery lifecycle
- conversation history save/load/delete/switch orchestration
- real tool execution/result lifecycle
- confirmation approval/denial execution
- provider/model settings interaction
- voice/STT/TTS hooks
- Personal OS write-capable boundaries

Next recommended architecture target: either a smaller history controller extraction after adding direct conversation-switch/delete recovery coverage, or a tool UI controller split limited to render-only and mocked click behavior. The send pipeline and full streaming lifecycle remain stop-lined until stronger end-to-end coverage exists for their orchestration.

## Vision Readiness and Agent UX Hardening

This pass did not add provider/API integration and did not extract another large controller. It hardened two visible product seams:

- image uploads now return an honest `vision_provider_required` fallback when no Vision provider is configured, instead of routing image metadata into the normal text-chat path as if analysis had happened
- image uploads with a mocked Vision provider use the existing Vision pipeline and return `analysis_status: analyzed`
- screenshot analysis now preflights provider readiness and avoids the critical `visionAnalyze` bridge/presence path when no provider is ready
- file display helpers now surface `Vision ready` / `Analyzed` status badges for upload results
- agent messages use the normal Lexa sender name and a softer `Plan` badge instead of exposing `Lexa Agent`
- agent step titles and aria labels now use readable labels; technical tool names remain in `data-technical-label` for debugging but are no longer visible chat chrome
- continuation prompts for blocked/failed agent steps omit raw technical tool labels

Files touched in this pass:

| File | Current lines after pass | Responsibility kept |
| --- | ---: | --- |
| `backend/router_chat.py` | 632 | `/chat/file` upload contract, Vision readiness split, existing text-file analysis path |
| `frontend/src/app.js` | 1592 | screenshot/Vision readiness UX and global action wiring |
| `frontend/src/chat.js` | 3666 | agent runtime UI, message insertion, send/stream/history orchestration |
| `frontend/src/chat_file_display_ui.js` | 52 | pure file/result display labels |

Tests covering this pass:

- `tests/test_router_chat_file_upload_vision.py` covers image no-provider fallback, mocked provider analysis, and unchanged text upload analysis.
- `tests/electron_vision_readiness_smoke.js` verifies missing Vision provider UX does not call the critical analysis bridge or request a confirmation.
- `tests/electron_file_upload_result_smoke.js` verifies the provider-required image fallback and unsafe filename containment.
- `tests/test_chat_file_display_helpers.js` directly covers status badges and provider-required fallback text.
- `tests/test_app_chat_input_wiring.js` and `tests/test_chat_send_guards.js` guard the friendlier agent labels while preserving hidden technical detail.

Remaining stop-lines:

- no real Vision provider/API selection yet
- no real provider calls, API keys, keyring writes, or secret handling
- no filesystem write/upload expansion beyond safe upload fixtures
- no send pipeline, streaming lifecycle, history orchestration, tool execution, Personal OS write path, Electron IPC, signing, or release-gate change

## Do Not Touch Yet

- streaming send and abort lifecycle beyond pure parser helpers
- conversation history switching/deletion persistence orchestration
- real file upload expansion beyond safe fixtures, filesystem writes, and provider/API execution
- real tool execution/result lifecycle and confirmation approval execution
- voice/STT/TTS/orb behavior
- settings keyring/API-key handling, voice runtime behavior, license activation/removal, backend/provider contracts/calls, and Electron IPC
- Personal OS draft create/apply/approve/reject/raw-submit flows and OS cleanup/archive/migration
- Electron preload IPC risk policy
- Electron backend lifecycle, Hermes startup, signing/update release behavior
- any OS cleanup, draft migration, or protected OS writes
