# CI and Release Readiness

Phase 4A adds CI-ready quality gates without deployment, uploads, secrets, or external model/API calls. Phase 4B adds a local CI core mode and clean-clone smoke so the workflow is closer to a fresh runner.

## GitHub Actions

`.github/workflows/quality-gates.yml` runs on pushes and pull requests for `main` and `develop`.

It performs:

- checkout
- Python 3.12 setup
- Node 20 setup
- Python dependency install from `requirements.txt` and `requirements-dev.txt`
- frontend dependency install from `frontend/package-lock.json`
- risky artifact check
- CI quality gate (`scripts\run_quality_gates.ps1 -Mode CI`)
- eval regression gate
- clean clone dry-run smoke
- full Python suite
- release-readiness smoke checks for packaging config, Hermes, website, optional OS gates, and performance budgets

The workflow does not deploy, publish, upload installers, call external LLM APIs, or require secrets.

## Local CI Simulation

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Full
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode CI
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Mode CICore
```

Use the release candidate script before tagging or packaging a release candidate. Build/package artifacts stay local and ignored.

## Known Limits

- The website layer in this workspace is a static external folder at `..\lexa-website`, not a Git repo and not a Node project.
- OS gates run only when the Personal OS mount is available. Missing OS paths are explicit warnings in CI.
- Packaging smoke defaults to config and artifact scanning. Use `scripts\run_packaging_smoke.ps1 -Build` for an isolated local installer build attempt.
- `CICore` is intended for CI-safe checks. `LocalFull` includes local Electron/OS/Hermes/Website gates. `StrictRC` is for a fuller local release proof, including package build and installer requirement.
- Existing `release.yml` remains a tag-triggered release workflow. Phase 4A does not run it and does not publish anything.
