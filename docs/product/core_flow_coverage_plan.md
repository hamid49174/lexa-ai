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
| Conversation history save/load | `test_router_conversations.py`, `test_chat_send_guards.js`, `electron_ui_visual_smoke.js`, `electron_core_chat_flow_smoke.js` | Full switch/load/delete lifecycle remains mostly in large visual smoke diagnostics | History refactors could drop raw markdown, duplicate messages, or corrupt active selection | Split conversation switch/load/delete cases into smaller focused Electron smokes before touching history lifecycle |
| Tool-call display | `test_chat_send_guards.js`, `test_app_chat_input_wiring.js`, backend action/parser tests | Focused renderer-only tool-call card display smoke is missing | Tool rendering refactors could expose unsafe labels or hide confirmation state | Add mocked `addMessage(..., action, true)` or mocked stream action display smoke; do not execute tools |
| Confirmation happy path | `test_router_companion.py`, `test_companion_confirmation.py`, `electron_presence_challenge_smoke.js` | Renderer confirmation click path with mocked `executeWithConfirmation` is not isolated | Confirmation UI refactors could call Companion incorrectly or lose safe denial behavior | Add focused Electron confirmation UI smoke with mocked confirmation, no real Companion execution |
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

## Stop-line Before Refactors

Do not extract or rewrite streaming lifecycle, conversation history lifecycle, tool-call rendering, confirmation UI, or Companion execution until focused integration coverage exists for the specific lifecycle being changed.

Recommended next coverage target: a focused renderer smoke for tool-call display and confirmation UI using mocked actions only, with no real Companion execution.
