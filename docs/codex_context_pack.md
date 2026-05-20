# Codex Context Pack

This pack gives Codex a safe project-level starting context for Lexa work. It is intentionally not a dump of the Personal OS, private conversations, eval results, traces, logs, or user data.

## Current Project State

- Phase 1: Local Auth, Companion Confirmation, tool ranking, and CSP/static gates are complete.
- Phase 2: OS Draft Envelope, plugin permission policy, Electron/DOM/preload hardening, repo hygiene, and release quality gates are complete.
- Phase 3: offline eval suite, Agent Protocol, trace replay, agent simulation, eval regression baseline, and failure triage are complete.
- Phase 4A-4C: release-readiness gates, clean install, CI-core, packaging smoke, installer smoke, collision-safe eval reports, signing plan, and release proof docs are in place.

Recent anchor commits:

- `e1246774ec3f2d061d5295852ed0bb4fc4162ccc` - Phase 4C release proof hardening
- `48e2ddc057369ad50cbbc154e48fe17fac763d39` - Phase 4B clean clone and packaging readiness
- `5e6011beedd3303d81d1a178612ca26c06c0b04a` - Phase 4A full release candidate readiness gates
- `85e76d59f53027e062595502821f5e69965d446e` - Phase 3F eval regression baselines and triage gates

## Architecture Map

- Backend: `backend/`
- Electron frontend: `frontend/`
- Offline evals: `evals/`
- Release and quality scripts: `scripts/`
- Release docs: `docs/release/`
- Tests: `tests/`
- External Personal OS mount: `personal_os/`
- External Website layer: `C:\Users\admin\OneDrive\Desktop\lexa\lexa-website`
- External Hermes workspace: `hermes_workspace/`

## Safe Context Sources

Use these first:

- `AGENTS.md`
- `README.md`
- `docs/dev-testing.md`
- `docs/release/release_candidate_checklist.md`
- `docs/release/ci.md`
- `docs/release/signing_plan.md`
- `docs/release/website_strategy.md`
- `docs/release/os_repo_cleanup_plan.md`
- `evals/README.md`

## Do Not Load Or Commit

- `personal_os/` content except when the user explicitly asks for a scoped OS check
- real `lexa_memory.db*`
- `audit.log` or `bridge-audit.log`
- `hermes_workspace/`
- `evals/results/`
- real traces under `tmp/agent_traces/`
- build outputs and installers
- private OS/Obsidian content
- `.env`, `*.env`, signing keys, or certificates

## Open Release Risks

- Remote GitHub Actions has not been proven from this workspace because no GitHub remote is configured.
- Installer install/uninstall is prepared but not proven in a disposable VM/sandbox.
- Installer is unsigned; this blocks PublicRC/PublicRelease.
- Website is a static external target without package-based lint/build proof.
- OS repo remains a separately dirty repository and needs a human-reviewed cleanup project.

## Recommended Next Work

1. Prove remote CI on a GitHub remote or keep it explicitly blocked for PublicRC.
2. Run installer install/uninstall in a disposable VM/sandbox.
3. Configure Windows signing outside Git.
4. Decide the website release target and add a safe build/lint strategy.
5. Run OS cleanup as a separate backup-first review project.

## Codex Usage Notes

Start with this pack and `AGENTS.md`, then read only the files needed for the current request. Do not scan or summarize private OS content into Lexa docs. Keep all reports redacted and all generated artifacts out of Git.
