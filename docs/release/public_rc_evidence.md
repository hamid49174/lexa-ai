# PublicRC Evidence Ledger

This ledger records local evidence only. It does not prove external PublicRC blockers such as GitHub Actions, VM/Sandbox installer execution, signing, website release ownership, or privacy/legal approval.

## Evidence Capture

- Date: 2026-05-20
- Branch: `codex/lexa-stabilization-review`
- Latest full internal regression snapshot commit under test: `d77db0ea8e7fb402c7ec33660048fae511ad4936`
- Baseline commit inspected before PublicRC hardening: `672d2e714595f4c24d7115bb757fba03f3e85faf`
- GitHub remote: not configured in this workspace

## Full InternalRC Regression Snapshot

This snapshot was run locally against commit `d77db0ea8e7fb402c7ec33660048fae511ad4936`. It strengthens InternalRC evidence only. It does not prove external PublicRC or PublicRelease blockers.

| Area | Command | Result |
| --- | --- | --- |
| Git status | `git status --short` | clean before snapshot |
| Branch | `git branch --show-current` | `codex/lexa-stabilization-review` |
| Commit under test | `git rev-parse HEAD` | `d77db0ea8e7fb402c7ec33660048fae511ad4936` |
| Remote CI readiness | `git remote -v`; `powershell -ExecutionPolicy Bypass -File scripts\check_remote_ci_readiness.ps1` | no GitHub remote configured; `RemoteCIReady: no` |
| Full Python suite | `venv\Scripts\python.exe -m pytest -q` | `786 passed, 1 skipped in 63.74s` |
| Eval suite | `venv\Scripts\python.exe evals\runners\run_eval_suite.py --all` | `65/65 passed, 0 failed` |
| Eval regression gate | `powershell -ExecutionPolicy Bypass -File scripts\run_eval_regression_gate.ps1` | passed; `0 blocking` regressions |
| JS static/unit suite | PowerShell loop over `tests/test_*.js` with `node` | 19/19 files passed; 956 assertions passed, 0 failed |
| Electron focused smokes | PowerShell loop over focused `tests/electron_*_smoke.js` files | 11/11 smoke files exited 0; counted smoke assertions: 124 passed, 0 failed; `electron_ui_visual_smoke.js` retained known non-blocking legacy diagnostics |
| Hermes smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_hermes_smoke.ps1` | `14 passed`; no external Telegram/API calls |
| OS quality gates | `powershell -ExecutionPolicy Bypass -File scripts\run_os_quality_gates.ps1 -AllowMissing` | completed OS SDK TypeScript, draft check, phase2a smoke, OS MCP server type/check, and Raw Inbox Worker type/check without deleting, migrating, or archiving drafts |
| Website smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_website_smoke.ps1` | exit 0 with static-external warnings: `tmp_*.js` files need review, config placeholders remain, external CDN resources need CSP/vendor review, and there is no package-based build/lint proof |
| Dependency reproducibility | `powershell -ExecutionPolicy Bypass -File scripts\check_dependency_repro.ps1` | completed with 1 warning: `python` is not available on PATH; website package/lock are optional missing for the static-external website |
| Clean clone/copy smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1` | completed; install/gates skipped by script defaults; temp clean copy retained for inspection |
| Packaging config smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1` | passed; build skipped by design; existing `dist` installer status: unsigned; no build artifacts staged |
| Isolated packaging build | `powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1 -Build -ArtifactRoot <temp-artifact-root>` | passed; NSIS installer built in temp; forbidden artifact scan passed; `Lexa AI Setup 1.0.0.exe` size `252721285` bytes; signing status: unsigned |
| Built-installer smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <temp-artifact-root> -RequireInstaller -Target InternalRC -AllowUnsignedInternal` | passed for InternalRC with unsigned warning; install/uninstall not requested and not proven |
| VM installer proof plan | `powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -PlanOnly -Target InternalRC` | plan-only output; Windows Sandbox available: `True`; Hyper-V available: `False`; VM marker: `False`; does not prove install/uninstall |
| Git whitespace safety | `git -c core.autocrlf=false diff --check` | passed |
| Risky artifact check | `powershell -ExecutionPolicy Bypass -File scripts\check_risky_artifacts.ps1 -Mode Strict` | passed; staged files checked: 0; warnings: 0 |
| InternalRC checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target InternalRC -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 0; decision: `Needs Review`; warnings include no remote CI proof and unsigned installer |
| PublicRC checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target PublicRC -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 1; decision: `Blocked`; blockers include remote CI, VM installer proof, signing, website target/CDN/CSP/SRI review, OS cleanup review, and remote artifact-policy proof |
| PublicRelease checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target PublicRelease -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 1; decision: `Blocked`; PublicRC blockers plus privacy/trace consent approval and public release workflow requirements |

JS static/unit exact results:

- `node tests/test_app_chat_input_wiring.js`: `183 tests: 183 passed, 0 failed`
- `node tests/test_bridge_risk_classification_static.js`: `21 tests: 21 passed, 0 failed`
- `node tests/test_chat_rendering.js`: `89 tests: 89 passed, 0 failed`
- `node tests/test_chat_send_guards.js`: `200 tests: 200 passed, 0 failed`
- `node tests/test_chat_streaming_helpers.js`: `8 tests: 8 passed, 0 failed`
- `node tests/test_chat_tool_display_helpers.js`: `7 tests: 7 passed, 0 failed`
- `node tests/test_electron_main_static.js`: `59 tests: 59 passed, 0 failed`
- `node tests/test_frontend_script_order_static.js`: `46 tests: 46 passed, 0 failed`
- `node tests/test_hermes_frontend_static.js`: `21 tests: 21 passed, 0 failed`
- `node tests/test_internal_daily_use_readiness_static.js`: `10 tests: 10 passed, 0 failed`
- `node tests/test_personal_os_prompt.js`: `174 tests: 174 passed, 0 failed`
- `node tests/test_preload_agent_static.js`: `4 tests: 4 passed, 0 failed`
- `node tests/test_preload_bridge_security_static.js`: `41 tests: 41 passed, 0 failed`
- `node tests/test_preload_local_auth_static.js`: `6 tests: 6 passed, 0 failed`
- `node tests/test_preload_personal_os_static.js`: `26 tests: 26 passed, 0 failed`
- `node tests/test_preload_voice_static.js`: `13 tests: 13 passed, 0 failed`
- `node tests/test_settings_helpers.js`: `9 tests: 9 passed, 0 failed`
- `node tests/test_settings_voice_static.js`: `23 tests: 23 passed, 0 failed`
- `node tests/test_tool_audit_surface.js`: `16 tests: 16 passed, 0 failed`

Electron smoke exact results:

- `node tests/electron_core_chat_flow_smoke.js`: `15 tests: 15 passed, 0 failed`
- `node tests/electron_tool_display_smoke.js`: `10 tests: 10 passed, 0 failed`
- `node tests/electron_tool_confirmation_smoke.js`: `15 tests: 15 passed, 0 failed`
- `node tests/electron_confirmation_click_smoke.js`: `10 tests: 10 passed, 0 failed`
- `node tests/electron_history_lifecycle_smoke.js`: `15 tests: 15 passed, 0 failed`
- `node tests/electron_history_failure_smoke.js`: `11 tests: 11 passed, 0 failed`
- `node tests/electron_streaming_robustness_smoke.js`: `15 tests: 15 passed, 0 failed`
- `node tests/electron_settings_persistence_smoke.js`: `14 tests: 14 passed, 0 failed`
- `node tests/electron_startup_health_smoke.js`: `8 tests: 8 passed, 0 failed`
- `node tests/electron_presence_challenge_smoke.js`: `11 tests: 11 passed, 0 failed`
- `node tests/electron_ui_visual_smoke.js`: exit 0; known legacy UI diagnostics retained but non-blocking

## Local Command Evidence

| Area | Command | Result |
| --- | --- | --- |
| Git status | `git status --short` | clean before edits |
| Current branch | `git branch --show-current` | `codex/lexa-stabilization-review` |
| Current commit at start of evidence capture | `git rev-parse HEAD` | `672d2e714595f4c24d7115bb757fba03f3e85faf`; final hardening commit is recorded in Git after this ledger is committed |
| Remote CI readiness | `git remote -v` | no remotes configured; remote CI not proven |
| Backend/launcher/script targeted tests | `venv\Scripts\python.exe -m pytest -q tests/test_router_companion.py tests/test_start_launcher_static.py tests/test_quality_gate_scripts.py` | `40 passed` |
| Electron main static test | `node tests/test_electron_main_static.js` | `59 passed, 0 failed` |
| Preload bridge static test | `node tests/test_preload_bridge_security_static.js` | `41 passed, 0 failed` |
| Website static smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_website_smoke.ps1` | exit 0 with warnings: `tmp_*.js` files need review, config placeholders remain, external CDN resources need CSP/vendor review, no package-based build/lint proof |
| Hermes gate | `powershell -ExecutionPolicy Bypass -File scripts\run_hermes_smoke.ps1` | `14 passed`; no external Telegram/API calls |
| OS gates | `powershell -ExecutionPolicy Bypass -File scripts\run_os_quality_gates.ps1 -AllowMissing` | completed OS SDK, draft check, OS MCP server check, and Raw Inbox Worker check without deleting, migrating, or archiving drafts |
| Eval suite | `venv\Scripts\python.exe evals\runners\run_eval_suite.py --all` | `65/65 passed, 0 failed` |
| Eval regression gate | `powershell -ExecutionPolicy Bypass -File scripts\run_eval_regression_gate.ps1` | passed with `0 blocking` regressions |
| Risky artifact check | `powershell -ExecutionPolicy Bypass -File scripts\check_risky_artifacts.ps1 -Mode Strict` | passed; staged files checked: 0; warnings: 0 |
| Git whitespace safety | `git -c core.autocrlf=false diff --check` | passed after normalizing touched files to LF |
| Full Python suite | `venv\Scripts\python.exe -m pytest -q` | `786 passed, 1 skipped` |
| Packaging config smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1` | passed; build skipped by design; existing local installer artifact is unsigned |
| Installer VM plan | `powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -PlanOnly` | exit 0; Windows Sandbox capability detected; plan-only mode does not prove install/uninstall |
| Isolated installer build | `powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1 -Build -ArtifactRoot <temp-artifact-root>` | passed; NSIS installer built in a temp artifact root; forbidden artifact scan passed; signing status: unsigned |
| Built-installer smoke | `powershell -ExecutionPolicy Bypass -File scripts\run_installer_smoke.ps1 -ArtifactRoot <temp-artifact-root> -RequireInstaller -Target InternalRC` | passed for InternalRC with unsigned warning; install/uninstall not requested and not proven |
| InternalRC checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target InternalRC -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 0; decision: `Needs Review`; warnings: no GitHub remote/remote CI proof, unsigned installer |
| PublicRC checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target PublicRC -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 1; decision: `Blocked`; blockers: remote CI, VM installer proof, signing, website target/CDN/CSP/SRI, OS cleanup review, remote artifact-policy proof |
| PublicRelease checker | `powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target PublicRelease -SkipFullQualityGate -AllowMissingOS -AllowMissingWebsite` | exit 1; decision: `Blocked`; PublicRC blockers plus privacy/trace consent approval and public release workflow requirements |

## External Blockers

- Remote CI: blocked until a GitHub remote exists, the branch is pushed, and a GitHub Actions run URL plus commit SHA are recorded.
- VM/Sandbox installer test: blocked until install/uninstall proof is run in an approved disposable VM or Windows Sandbox.
- Windows signing: blocked until certificate, protected secret storage, signed artifact, and signer verification exist.
- Website release target: blocked for PublicRC until release ownership, package/static validation, and CDN/CSP/SRI policy are approved.
- Website domain metadata: `og:url` and public contact/config domains are inconsistent; intended public domain requires release-owner decision before PublicRC.
- OS cleanup: separate backup-first review project; no Lexa patch should move, delete, or archive OS data.
- Privacy / Trace Consent: required before PublicRelease and not approved by this ledger.
- License integrity: PublicRC/PublicRelease need a product/security decision for server-backed signed licensing or explicit acceptance of local-only limits.

## RC Status Summary

- InternalRC: allowed only as `Needs Review` with documented warnings.
- PublicRC: blocked.
- PublicRelease: blocked.
