# CI and Release Readiness

Phase 4A adds CI-ready quality gates without deployment, uploads, secrets, or external model/API calls. Phase 4B adds a local CI core mode and clean-clone smoke so the workflow is closer to a fresh runner.

Phase 4D status: no remote GitHub Actions run has been proven from this workspace because the local repository has no configured GitHub remote. The workflow is therefore CI-ready and locally simulated, but remote CI remains "not yet remotely proven" until a branch is pushed to GitHub and the workflow run is inspected.

Phase 4E status: `git remote -v` still returns no configured remote in this workspace. Remote CI is therefore not executable from here without a manual GitHub repository setup step. `scripts\run_quality_gates.ps1 -Mode CI` remains the local CI-core proof, but PublicRC/PublicRelease stay blocked until GitHub Actions has actually run remotely.

Phase 4F status: `scripts\check_remote_ci_readiness.ps1` now performs the local readiness check. It verifies GitHub remote presence, workflow existence, absence of secret references, absence of release artifact uploads, absence of user-data paths, and local CI/RC script support. In this workspace it reports `RemoteCIReady: no` because no GitHub remote is configured.

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
- release candidate CI core check
- full Python suite
- release-readiness smoke checks for packaging config, Hermes, website, optional OS gates, and performance budgets

The workflow does not deploy, publish, upload installers, call external LLM APIs, or require secrets.

The workflow uses Windows runners, Python 3.12, and Node 20. OS gates are optional because the Personal OS is a local external mount. Website smoke is optional/static because `..\lexa-website` is not part of this Git repository.

## Local CI Simulation

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Full
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode CI
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Mode CICore
powershell -ExecutionPolicy Bypass -File scripts\check_remote_ci_readiness.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target InternalRC
powershell -ExecutionPolicy Bypass -File scripts\run_release_candidate_check.ps1 -Target PublicRC
```

Use the release candidate script before tagging or packaging a release candidate. Build/package artifacts stay local and ignored.

`CICore` proves the checks that can run from a clean repository without local OS mounts or website project dependencies. It must not be described as a completed remote CI run until a real GitHub Actions job has run.

## Remote CI Proof

Remote CI is considered proven only when all of these are true:

- a GitHub remote is configured
- a branch or pull request is pushed
- `.github/workflows/quality-gates.yml` runs on GitHub Actions
- the run completes without secrets, deployment, uploads, or user-data dependencies
- the run result is linked or recorded in release notes

In this workspace there is currently no GitHub remote, so PublicRC and PublicRelease remain blocked by remote-CI proof.

## Manual Remote CI Setup

To prove remote CI without adding secrets or deployment:

1. Create or select the GitHub repository for Lexa.
2. Add the remote locally, for example `git remote add origin <github-url>`.
3. Push the current branch.
4. Open the GitHub Actions tab and run or inspect `.github/workflows/quality-gates.yml`.
5. Confirm the run uses no secrets, no deployment, no artifact upload, and no user-data paths.
6. Record the run URL and commit SHA in release notes.
7. Re-run `scripts\run_release_candidate_check.ps1 -Target PublicRC`.

Until those steps are complete, the correct status is "Remote CI not yet proven", not "CI passed remotely".

Readiness script expected outcomes:

- no GitHub remote: exit 0, `RemoteCIReady: no`, PublicRC remains blocked
- safe GitHub remote plus safe workflow: exit 0, `RemoteCIReady: yes`, remote run still must be executed and recorded
- workflow with secret references, artifact upload, release action, or user-data paths: exit 1

## Known Limits

- The website layer in this workspace is a static external folder at `..\lexa-website`, not a Git repo and not a Node project.
- OS gates run only when the Personal OS mount is available. Missing OS paths are explicit warnings in CI.
- Packaging smoke defaults to config and artifact scanning. Use `scripts\run_packaging_smoke.ps1 -Build` for an isolated local installer build attempt.
- `CICore` is intended for CI-safe checks. `LocalFull` includes local Electron/OS/Hermes/Website gates. `StrictRC` is for a fuller local release proof, including package build and installer requirement.
- Existing `release.yml` remains a tag-triggered release workflow. Phase 4A does not run it and does not publish anything.
- Remote CI is not yet proven in this workspace because no Git remote is configured.
- If OS, Hermes, or Website paths are absent on CI, the corresponding local-only gate must warn or skip explicitly rather than silently pretending to validate external data.
