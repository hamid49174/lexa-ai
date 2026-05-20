# Lexa Feature Readiness Matrix

Date: 2026-05-20
Baseline commit: `7a3009a86c4c0f1b3f41cd7b8b07b5fc966ba53b`
Goal: professional internal daily use. Public release remains postponed.
PublicRC remains blocked until the external proof items in the release ledger are complete.

Classification key:

- `CORE`: should stay visible for internal daily use.
- `BETA`: usable for internal review, but must be visibly labeled.
- `INTERNAL_ONLY`: useful for Lexa operators/developers, not a normal-user surface.
- `HIDE`: should not be in main navigation until the owner explicitly re-enables it.
- `FIX_REQUIRED`: visible behavior is too likely to confuse or mislead without a fix.

Evidence inspected:

- UI shell and visible routes: `frontend/src/index.html`, `frontend/src/app.js`
- Daily UI logic: `frontend/src/chat.js`, `frontend/src/settings.js`, `frontend/src/personal_os.js`, `frontend/src/system.js`, `frontend/src/productivity.js`, `frontend/src/memory.js`, `frontend/src/commands.js`
- Coverage and gates: `tests/electron_ui_visual_smoke.js`, `tests/electron_startup_health_smoke.js`, `tests/electron_presence_challenge_smoke.js`, `tests/test_app_chat_input_wiring.js`, `tests/test_chat_rendering.js`, `tests/test_chat_send_guards.js`, `tests/test_personal_os_prompt.js`, `tests/test_router_personal_os.py`, `tests/test_settings_voice_static.js`, `tests/test_hermes_frontend_static.js`, `tests/test_plugin_manager.py`, `tests/test_plugin_permissions.py`, `tests/test_release_candidate_check.py`
- Release posture docs: `docs/release/public_rc_evidence.md`, `docs/release/public_rc_blocker_matrix.md`, `docs/release/website_strategy.md`, `docs/release/signing_plan.md`

## Matrix

| Feature / surface | UI location | Classification | Current observed / known status | Risk if left visible without label | Required action | Internal daily use | PublicRC later |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dashboard overview | Sidebar `Dashboard`; `dashboard` view | CORE | Visible first-class view with startup/system/Hermes summaries; covered by visual smoke path. | Low; useful situational awareness. | Keep visible. | Yes | Yes |
| Text chat composer and response rendering | Sidebar `Chat`; composer textarea, send button, message list | CORE | Core app surface; JS chat wiring/rendering/static guards and Electron visual smoke cover conversation behavior. | High if broken, but this is the product center. | Keep visible and prioritize smoke coverage. | Yes | Yes |
| Chat history / conversation list | Sidebar `CHATS`, search/new chat, conversation persistence | CORE | Conversation list, search overlay, title update, stale-switch and persistence cases are covered in UI smoke/static tests. | Medium if persistence regresses. | Keep visible; keep persistence smoke in daily gates. | Yes | Yes |
| File attachment and vision screenshot | Chat composer attach and screenshot buttons | BETA | Visible bridge-backed capability with higher privacy/permission impact; visual smoke checks layout, but public privacy review is not final. | Users may assume screenshots/uploads are production-reviewed. | Keep visible with internal/beta posture in matrix; avoid expanding until privacy/trace review is approved. | Optional | Yes, after privacy review |
| Voice orb, mic, TTS, wake word | Chat voice button, orb, mic/TTS toggles, Settings voice/STT/TTS groups | BETA | Voice diagnostics are covered; realtime audio transport is explicitly not implemented, and wake word has fallback/diagnostic complexity. | Confusing if it appears as fully production voice. | Mark visible voice entry/settings as `Beta`; keep diagnostics prominent. | Optional | Yes, after voice transport/privacy proof |
| Productivity todos/habits/time/focus | Sidebar `Productiv`; Productivity view | CORE | Backend and router tests cover todos/habits/time tracking; view has create/search/export controls. | Low-to-medium; daily utility surface. | Keep visible. | Yes | Yes |
| Memory notes/snippets/routines/clipboard cleanup | Sidebar `Gedaechtnis`; Memory view | CORE | Memory tests cover CRUD and chat persistence; cleanup/diagnostics are maintenance actions. Clipboard/history surfaces carry privacy implications. | Medium if clipboard or cleanup feels automatic. | Keep visible; do not auto-clean without explicit action. | Yes | Yes, after privacy review |
| System monitor and command catalog | Sidebar `System` and `Befehle` | CORE | Visible command cards and catalog; high-risk actions require confirmation/presence gates in bridge smokes. | Medium if destructive commands look casual. | Keep confirmation/presence gates strict; keep command statuses visible. | Yes | Yes |
| Hermes gateway cockpit/autostart | Dashboard/System summaries; Settings `Hermes Gateway Autostart` | INTERNAL_ONLY | Hermes smoke uses local adapter tests only and does not prove external Telegram/API operation. | Normal users may mistake Telegram gateway for a supported public integration. | Mark Hermes autostart as `Internal`; keep external proof separate. | Operator-only | Yes, after external gateway proof |
| Personal OS cockpit | Sidebar `OS`; Personal OS view, context search, draft review/apply actions | INTERNAL_ONLY | UI uses draft/review/apply model; router tests enforce SDK boundaries and approval guards. OS cleanup is intentionally separate. | Risky for normal users because draft/apply semantics and vault ownership are advanced. | Keep visible only as `Internal`; never clean/move OS data from this sprint. | Operator-only | Maybe, after UX/backup/review policy |
| Agent runs and attention filter | Chat composer `/agent`, hidden attention filter, agent completion panels | BETA | Agent simulation/eval/static coverage exists; runtime autonomy remains gated and attention UI appears when runs need review. | Users may expect autonomous completion without review. | Keep as beta/internal workflow; do not expose as public automation promise. | Optional for operators | Yes, after agent policy approval |
| Trace Replay and Agent Simulation | Eval docs/tests, not main navigation | INTERNAL_ONLY | Present in eval suite and release checklist; no main user UI found in `index.html`. | If surfaced as product feature, it would confuse normal users. | Keep out of main nav; document as internal QA only. | No | QA proof only |
| Plugin / marketplace-like backend | Backend `/plugins`, plugin manager/permissions tests; no marketplace UI found in main shell | INTERNAL_ONLY | Plugin manager and permission tests exist; legacy plugin loader is default-disabled. | Users could assume installable marketplace maturity. | Keep out of visible main UI unless an owner adds admin-only labeling. | No | Maybe, after plugin policy/review |
| License / Pro UI | Settings `LIZENZ` group | FIX_REQUIRED | Local license UI exists, but PublicRC blocker matrix says local license files are not strong entitlement proof. | Misleads users into believing Pro licensing is production-grade. | Mark `Internal` and document server-backed signed licensing or accepted local-only limits as a decision. | No, except operator testing | Yes, after license integrity decision |
| Auto-update notifications | Renderer listens for main-process update notifications; signing plan says distribution trust incomplete | INTERNAL_ONLY | Update URL validation exists, but signing/release artifact proof is not complete. | Users may trust update notices before signing is solved. | Treat as internal build notification until signing/release validation exists. | Optional | Yes, after signing/release proof |
| Website download / marketing | External `../lexa-website` static site | FIX_REQUIRED | External non-Git website has hardening edits but no release target, package lint/build, CDN/CSP/SRI decision, or domain decision. | Public visitors may see unversioned or inconsistent release metadata. | Preserve edits in docs; version website before relying on it. | No | Yes, after website decision |
| Privacy / Trace consent | Release docs and trace/eval infrastructure | FIX_REQUIRED | Checklist exists but is not release-owner approval. | Public users may not have clear consent controls for traces/privacy-sensitive surfaces. | Keep blocking PublicRelease; do not claim approval. | Internal review only | Yes, required |

## Visible Labeling Decision

For the daily-use sprint, Lexa keeps the core assistant flow visible and marks advanced or unproven surfaces instead of deleting them:

- Voice entry points: `Beta`
- Personal OS navigation/view: `Internal`
- Hermes gateway autostart: `Internal`
- Wake word: `Beta`
- License settings: `Internal`

No feature is marked `HIDE` in this pass because the risky surfaces are either operator workflows or already absent from main navigation. If a non-operator build is prepared later, Personal OS, Hermes, agent QA, plugin administration, and local licensing should be hidden behind an internal build flag.

## Modularization Prep

Large frontend files remain intentionally intact in this sprint:

- `frontend/src/chat.js`
- `frontend/src/personal_os.js`
- Electron `main.js`

Safe first extractions later:

- constants and route/action names
- pure formatting helpers
- API wrapper helpers
- small render helpers with static tests

Do not split streaming, history persistence, tool rendering, or Personal OS draft apply behavior until the corresponding smoke path is run in the same change.
