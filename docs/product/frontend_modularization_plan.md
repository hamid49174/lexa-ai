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
| Chat voice integration | mic/STT/TTS/orb state and wake-word paths | High | `test_settings_voice_static.js`, voice tests, Electron visual smoke |
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
8. `chat_input_helpers.js`
9. `chat_tool_confirmation_ui.js`
10. `chat_history_ui.js`
11. `chat.js`

Remaining high-risk clusters: streaming send/abort, conversation history switching/deletion/persistence orchestration, non-confirmed tool-call execution/result rendering, confirmation approval execution, Companion execution, voice/STT/TTS/orb behavior, Personal OS draft apply/approve/reject flows, Electron preload IPC, Electron backend lifecycle, signing/update behavior, and OS cleanup.

Stop-line: do not extract streaming, send pipeline, conversation switch/load/delete lifecycle, tool execution/result rendering, or confirmation approval execution until direct E2E or stronger integration coverage exists for those lifecycle paths.

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

Next recommended target: add focused history failure-path coverage for save/load/delete recovery before extracting any history orchestration, or add mocked confirmation click coverage before moving confirmation approval UI. Streaming and send pipeline remain stop-lined.

## Do Not Touch Yet

- streaming send and abort behavior
- conversation history switching/deletion persistence orchestration
- tool execution/result rendering and confirmation approval execution
- voice/STT/TTS/orb behavior
- Personal OS draft apply/approve/reject flows
- Electron preload IPC risk policy
- Electron backend lifecycle, Hermes startup, signing/update release behavior
- any OS cleanup, draft migration, or protected OS writes
