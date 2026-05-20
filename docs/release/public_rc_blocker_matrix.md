# PublicRC Blocker Matrix

Phase 4F turned the remaining PublicRC work into explicit blockers, warnings, owners, and next actions. Phase 5A keeps those blockers concrete: each item is either practically testable in this repo or explicitly marked as an external prerequisite. This file is a release-readiness artifact, not a product feature plan.

| Blocker ID | Area | Status | InternalRC impact | PublicRC impact | PublicRelease impact | Why it matters | What is missing | Next concrete step | Owner | Can code help | Needs external prerequisite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRC-001 | CI | not proven | warning | blocking | blocking | Remote CI proves the clean repository works outside the local workstation. | No GitHub remote or Actions run is recorded. | Create GitHub repo or remote, push branch, run `.github/workflows/quality-gates.yml`, record run URL and SHA. | user | yes | yes |
| PRC-002 | Installer | not proven | warning | blocking | blocking | Installer install/uninstall must be proven outside the productive machine. | Disposable VM or Windows Sandbox execution evidence. | Run `scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Install -Uninstall -VMOnly` inside an approved VM flow. | user | yes | yes |
| PRC-003 | Signing | blocked | warning | blocking | blocking | Unsigned installers create trust and SmartScreen problems. | Code signing certificate and secure signing process. | Obtain certificate, configure signing outside Git, rerun packaging and installer smoke. | user / external | yes | yes |
| PRC-004 | Website | external | warning | blocking | blocking | Website release needs a reproducible validation target. | Website has no package-based build/lint or equivalent static-release proof. | Keep current static-external target for InternalRC; approve separate website release target before PublicRC. | user | yes | partly |
| PRC-005 | OS | external | warning | blocking | blocking | Dirty external OS state can hide user data, generated drafts, or unreviewed changes. | Human-reviewed cleanup decision in the OS repo. | Run backup-first OS cleanup review as a separate project with OS gates before and after. | user | yes | yes |
| PRC-006 | Website | external | warning | blocking | blocking | The website is static-external and not packaged with Lexa release flow. | Explicit release target and ownership. | Choose separate repo, minimal website package, or equivalent static validation in a dedicated website phase. | user | yes | partly |
| PRC-007 | Privacy | not proven | warning | warning | blocking | Public releases need explicit policy for traces, reports, and consent. | Checklist exists, but public privacy/trace consent is not reviewed or approved. | Review `docs/release/privacy_trace_consent_checklist.md` and record release-owner approval. | user | yes | yes |
| PRC-008 | Signing | blocked | warning | blocking | blocking | Signing secrets must never enter Git or build artifacts. | Secret-store or protected CI signing design. | Keep keys out of repo, use secure store/GitHub Secrets only after remote CI exists. | user / external | yes | yes |
| PRC-009 | CI | not proven | warning | blocking | blocking | Remote runners may not have OS/Hermes/Website local paths. | Remote skip/warn behavior must be observed in Actions. | Run remote CI and confirm local-only gates skip or warn honestly. | user | yes | yes |
| PRC-010 | Release | not proven | warning | blocking | blocking | Artifact policy must hold on the actual remote runner. | Remote proof that risky artifact scan blocks result/build/userdata paths. | Run remote CI with `scripts\check_risky_artifacts.ps1` and record outcome. | user | yes | yes |

## Current Tier Decision

- InternalRC: possible with Needs Review warnings.
- PublicRC: blocked until PRC-001, PRC-002, PRC-003, PRC-004/006, PRC-005, PRC-009, and PRC-010 are resolved or explicitly accepted by the release owner.
- PublicRelease: additionally blocked until PRC-007 is reviewed/approved and all PublicRC blockers are resolved.

## Phase 5A Decisions

- Remote CI remains external because `git remote -v` has no configured GitHub remote in this workspace.
- VM installer install/uninstall remains external because this repository cannot prove an isolated Windows VM run by itself.
- Signing remains external because no certificate, key, passphrase, or signing secret is present or allowed in Git.
- Website remains `static-external` for InternalRC. PublicRC remains blocked until a separate website release target exists.
- OS cleanup remains external and backup-first. No OS cleanup starts from Lexa release hardening.
- Privacy/trace consent now has a checklist, but PublicRelease remains blocked until the release owner approves it.

## Non-Code Prerequisites

Some blockers cannot be solved by patching this repository alone:

- GitHub remote and Actions execution require repository access.
- VM installer proof requires a disposable Windows VM or Sandbox.
- Signing requires certificate procurement and secure secret handling.
- OS cleanup requires human review of private external data.
- Website release target requires a product/release ownership decision.
