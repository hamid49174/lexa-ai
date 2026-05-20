# CI and Release Readiness

Phase 4A adds CI-ready quality gates without deployment, uploads, secrets, or external model/API calls.

## GitHub Actions

`.github/workflows/quality-gates.yml` runs on pushes and pull requests for `main` and `develop`.

It performs:

- checkout
- Python 3.12 setup
- Node 20 setup
- Python dependency install from `requirements.txt` and `requirements-dev.txt`
- frontend dependency install from `frontend/package-lock.json`
- risky artifact check
- Quick quality gate
- eval regression gate
- full Python suite
- release-readiness smoke checks for packaging config, Hermes, website, optional OS gates, and performance budgets

The workflow does not deploy, publish, upload installers, call external LLM APIs, or require secrets.

## Local CI Simulation

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Full
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1
```

Use the release candidate script before tagging or packaging a release candidate. Build/package artifacts stay local and ignored.

## Known Limits

- The website layer in this workspace is a static external folder at `..\lexa-website`, not a Git repo and not a Node project.
- OS gates run only when the Personal OS mount is available. Missing OS paths are explicit warnings in CI.
- Packaging smoke defaults to config and artifact scanning. Use `scripts\run_packaging_smoke.ps1 -Build` for a local installer build.
- Existing `release.yml` remains a tag-triggered release workflow. Phase 4A does not run it and does not publish anything.
