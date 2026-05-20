# PublicRC Evidence Ledger

This ledger records local evidence only. It does not prove external PublicRC blockers such as GitHub Actions, VM/Sandbox installer execution, signing, website release ownership, or privacy/legal approval.

## Evidence Capture

- Date: 2026-05-20
- Branch: `codex/lexa-stabilization-review`
- Baseline commit inspected before local hardening: `672d2e714595f4c24d7115bb757fba03f3e85faf`
- GitHub remote: not configured in this workspace

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
