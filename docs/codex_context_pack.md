# Codex Context Pack

This file is generated from safe Lexa repository metadata and fixed release-readiness facts. It intentionally excludes Personal OS contents, user data, eval results, traces, logs, secrets, signing keys, certificates, and build artifacts.

## Current Project State

- Current Lexa commit: f2d1a17
- GitHub remote status: configured
- Release targets: InternalRC, PublicRC, PublicRelease
- InternalRC may proceed with documented warnings.
- Phase 4F readiness focus: blocker matrix, remote CI readiness, VM installer proof, signing readiness, website target, OS cleanup review, and safe context workflow.
- Phase 5A readiness focus: turn each PublicRC blocker into either a practical proof path or an explicit external prerequisite.
- Phase 5B readiness focus: classify every remaining PublicRC blocker as agent-solvable, user-decision, external-infrastructure, later, or proven.
- PublicRC/PublicRelease remain blocked until remote CI proof, VM installer proof, signing, website release target proof, OS cleanup review, and public privacy/trace review are complete.

## Recent Commits

- f2d1a17 Allow certifi CA bundle in artifact scan
- 8a936bd Stabilize Lexa release readiness
- c790f92 Make memory graph a neural cloud
- 7a21ecc Revert "Make memory graph brain-like"
- a7e3e41 Make memory graph brain-like

## Safe Context Sources

- AGENTS.md
- README.md
- docs/dev-testing.md
- docs/release/release_candidate_checklist.md
- docs/release/public_rc_blocker_matrix.md
- docs/release/privacy_trace_consent_checklist.md
- docs/release/ci.md
- docs/release/signing_plan.md
- docs/release/website_strategy.md
- docs/release/os_repo_cleanup_plan.md
- evals/README.md

## Do Not Load Or Commit

- personal_os/ contents unless explicitly scoped by the user
- real memory databases, audit logs, bridge audit logs, traces, eval results, installers, build output, secrets, signing keys, certificates, private OS/Obsidian content

## Required Gates

- scripts\run_quality_gates.ps1 -Mode Quick
- scripts\run_quality_gates.ps1 -Mode Full
- scripts\run_quality_gates.ps1 -Mode CI
- scripts\run_eval_regression_gate.ps1
- scripts\run_release_candidate_check.ps1 -Target InternalRC
- scripts\check_remote_ci_readiness.ps1

## Open Release Risks

- Remote GitHub Actions run is not yet proven until a real workflow run URL and commit SHA are recorded.
- Installer install/uninstall in a disposable VM or sandbox is not yet proven.
- Installer is unsigned.
- Website is currently a static external target with local package/lint proof, but public config and Stripe.js/CSP approval remain unresolved.
- External OS cleanup remains a separate reviewed project.
- Public release privacy/trace consent checklist exists only as a release review artifact until approved.

## Agent/User/External Split

- Agent-solvable: keep scripts, docs, redaction, artifact scans, local CI modes, and RC output honest.
- User decisions: GitHub Actions run proof, website public config/CSP approval, OS cleanup approval, privacy/trace consent, signing provider.
- External infrastructure: GitHub Actions run, disposable VM/Sandbox proof, certificate/secret store.
- Later work: website packaging/repo structure and public privacy UI after release-owner decision.
- Proven items should have recorded command output, run URL, commit SHA, or review signoff.

## Codex Working Rules

- Do not use git add ..
- Do not delete files without explicit approval.
- Do not commit user data, generated artifacts, secrets, signing keys, certificates, or private OS/Obsidian content.
- Keep OS, Hermes, Website, Plugin, Electron, and release changes scoped to the active phase.
