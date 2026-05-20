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

Next safest extraction target: the remaining higher-level `appendMarkdownSegment()`, `appendFormattedMessage()`, and `formatMessage()` group, but only if the direct rendering tests remain stable. Streaming, conversation history, tool-call rendering, voice, Companion execution, and Personal OS draft flows remain out of scope.

## Do Not Touch Yet

- streaming send and abort behavior
- conversation history switching/deletion persistence
- tool-call rendering and confirmation UI
- voice/STT/TTS/orb behavior
- Personal OS draft apply/approve/reject flows
- Electron preload IPC risk policy
- Electron backend lifecycle, Hermes startup, signing/update release behavior
- any OS cleanup, draft migration, or protected OS writes
