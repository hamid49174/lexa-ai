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
| Streaming response lifecycle | `test_chat_send_guards.js`, `electron_core_chat_flow_smoke.js`, `electron_ui_visual_smoke.js` | Abort, timeout, chunk fragmentation, and malformed SSE integration are not fully covered | Streaming refactors could strand loading state, disabled buttons, or partial text | Add a second focused Electron smoke for abort/timeout/chunk-boundary behavior before moving streaming code |
| Conversation history save/load | `test_router_conversations.py`, `test_chat_send_guards.js`, `electron_ui_visual_smoke.js`, `electron_core_chat_flow_smoke.js`, `electron_tool_confirmation_smoke.js`, `electron_history_lifecycle_smoke.js`, `electron_history_failure_smoke.js` | Real backend persistence and active-conversation delete edge cases still need focused coverage | History refactors could drop raw markdown, duplicate messages, corrupt active selection, or crash on malformed history payloads | Keep failure-path smoke in required gates before moving save/load/delete orchestration |
| Tool-call display | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, backend action/parser tests, `electron_tool_confirmation_smoke.js` | Non-confirmed tool execution display remains intentionally broad-smoke/static covered only | Tool rendering refactors could expose unsafe labels or hide confirmation state | Add focused non-executing display smoke for safe/no-confirm tool results before moving more tool UI |
| Confirmation happy path | `test_router_companion.py`, `test_companion_confirmation.py`, `electron_presence_challenge_smoke.js`, `electron_tool_confirmation_smoke.js`, `electron_confirmation_click_smoke.js` | Real Companion execution remains intentionally outside renderer smoke coverage | Confirmation UI refactors could call Companion incorrectly or lose safe denial behavior | Keep focused click smoke mocked; do not add real tool execution to renderer tests |
| OS draft creation path | `test_personal_os_prompt.js`, `test_router_personal_os.py`, `test_personal_os_actions.py`, eval OS draft tests | Full renderer draft creation from chat handoff is not isolated | OS draft UI refactors could bypass Draft/Approval expectations | Add a mocked Personal OS draft handoff smoke only after core chat/history smokes are stable |
| Settings persistence | `test_settings_voice_static.js`, `test_app_chat_input_wiring.js`, `electron_ui_visual_smoke.js` | Focused settings save/load smoke is thin | Settings refactors could silently stop saving provider/voice preferences | Add a small Electron settings persistence smoke if settings modularization resumes |
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

## Stop-line Before Refactors

Do not extract or rewrite streaming lifecycle, send pipeline, conversation save/load/delete orchestration, active-conversation delete recovery, real tool execution, real confirmation approval execution, Companion execution, or OS draft actions until focused integration coverage exists for the specific lifecycle being changed.

Recommended next coverage target: focused streaming abort/timeout/chunk-boundary smoke, or a focused non-confirmed tool display smoke that remains render-only and does not execute Companion.
