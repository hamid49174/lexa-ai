# PublicRC Blocker Matrix

Phase 4F turned the remaining PublicRC work into explicit blockers, warnings, owners, and next actions. Phase 5A keeps those blockers concrete: each item is either practically testable in this repo or explicitly marked as an external prerequisite. Phase 5B separates what the agent can still harden from what requires a user decision or external infrastructure proof. This file is a release-readiness artifact, not a product feature plan.

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
| PRC-011 | License integrity | decision required | warning | blocking | blocking | Local license files can be edited by the client and are not a cryptographic entitlement proof. | Server-backed signed license or explicit business acceptance of local-only enforcement limits. | Decide license entitlement model before PublicRC and record whether local checks are only defense-in-depth. | user / product | yes | partly |

## Phase 5B Action Classification

| Blocker | Category | Phase 5B result | Next action |
| --- | --- | --- | --- |
| Remote GitHub Actions proof | External infrastructure needed | Not proven because this repository has no GitHub remote configured. | User creates/chooses GitHub repo, sets remote, pushes branch, runs Actions, records run URL and SHA. |
| VM installer install/uninstall proof | User/external execution needed | Not proven by this workspace. Installer smoke can print readiness and plan; it does not install into the productive machine. | Run `scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Install -Uninstall -VMOnly` only inside an approved disposable VM or Windows Sandbox. |
| Windows installer signing | External certificate decision needed | Prepared, not solved. No certificate, key, passphrase, or signing secret is present or allowed in Git. | Choose certificate/provider, store secrets outside Git, configure signing, rebuild, verify publisher. |
| Website release target | User decision needed | Website remains `static-external`; no `package.json` is added from Lexa release hardening. | Choose static release process, minimal website package, separate website repo, or later monorepo work. |
| OS cleanup review | User review needed | Not started. Lexa only records category-level inventory; OS remains external and dirty. | Run a separate backup-first OS cleanup project with OS gates before and after. |
| Privacy/trace consent | User/legal/product decision needed | Checklist exists, not approved. | Review consent, retention, opt-in/opt-out, export/delete, provider-use, and public documentation decisions. |
| Website CDN/SRI/CSP | User/security review needed | Website smoke warns; no PublicRC-grade CSP/vendor/SRI review is proven. | Review external CDN/scripts and decide pinning/CSP/vendor policy in the website release target. |
| Public artifact policy | External CI proof needed | Local risky-artifact checks pass; remote runner behavior is not proven. | Prove risky artifact policy in GitHub Actions without publishing build/eval/trace artifacts. |
| Remote CI artifact policy | External CI proof needed | Workflow is designed to avoid result/build artifact uploads, but no remote run exists. | Run GitHub Actions and confirm no release artifacts, eval results, traces, logs, or userdata are uploaded. |
| PublicRelease legal/privacy docs | User/legal/product decision needed | Privacy checklist exists, not release-owner approved. | Complete and approve public privacy/release notes before PublicRelease. |
| License integrity model | User/product/security decision needed | Local license storage exists, but PublicRC-grade entitlement/integrity is not proven. | Choose server-backed signed license validation or explicitly accept local-only license checks as non-security enforcement. |

## Current Tier Decision

- InternalRC: possible with Needs Review warnings.
- PublicRC: blocked until PRC-001, PRC-002, PRC-003, PRC-004/006, PRC-005, PRC-009, PRC-010, and PRC-011 are resolved or explicitly accepted by the release owner.
- PublicRelease: additionally blocked until PRC-007 is reviewed/approved and all PublicRC blockers are resolved.

## Latest Local Regression Snapshot

Snapshot date: 2026-05-21

Snapshot commit under test: `b876228b08b2106193b2fb10a9a71ec58463e41c`

Local evidence after Agent Reflection v1 and abuse coverage:

- Full Python suite: `886 passed, 1 skipped, 1 warning`.
- Focused reflection/security tests: `163 passed`.
- Eval suite: `65/65 passed, 0 failed`.
- Eval regression gate: passed with `0 blocking`.
- JS static/unit suite: 21/21 files passed, 997 assertions passed, 0 failed.
- Electron focused smokes: 15/15 files exited 0, with 176 counted assertions passed, 0 failed; `electron_ui_visual_smoke.js` retained known non-blocking legacy diagnostics.
- Hermes smoke: `14 passed`, local only.
- OS quality gates completed without deleting, migrating, or archiving drafts.
- Website smoke completed as `static-external` with warnings that remain PublicRC-blocking.
- Isolated packaging build and built-installer smoke passed for InternalRC, but installer remains unsigned and install/uninstall was not run.
- InternalRC checker: exit 0, `Needs Review`.
- PublicRC checker: exit 1, `Blocked`.
- PublicRelease checker: exit 1, `Blocked`.

No external proof was created by this local snapshot. PRC-001, PRC-002, PRC-003, PRC-004/006, PRC-005, PRC-009, PRC-010, PRC-011, and PublicRelease privacy approval remain unresolved.

## Phase 5A Decisions

- Remote CI remains external because `git remote -v` has no configured GitHub remote in this workspace.
- VM installer install/uninstall remains external because this repository cannot prove an isolated Windows VM run by itself.
- Signing remains external because no certificate, key, passphrase, or signing secret is present or allowed in Git.
- Website remains `static-external` for InternalRC. PublicRC remains blocked until a separate website release target exists.
- OS cleanup remains external and backup-first. No OS cleanup starts from Lexa release hardening.
- Privacy/trace consent now has a checklist, but PublicRelease remains blocked until the release owner approves it.

## Phase 5B Status

- Remote CI remains an external/user blocker: no GitHub remote is configured, so no remote Actions run can be triggered from this workspace without upload/push approval.
- VM installer proof remains not proven: the script can report VM/Sandbox readiness and print the proof plan, but no real install/uninstall was executed.
- Signing remains blocked by external certificate and secret-store decisions. InternalRC can warn; PublicRC/PublicRelease require a signed installer.
- Website remains `static-external` and PublicRC-blocking until the user approves a website release target.
- OS cleanup remains a separate backup-first review project; Lexa does not stage, delete, archive, or commit OS data.
- Privacy/trace consent is now concrete enough for review, but not approved for PublicRelease.
- License integrity remains a product/security decision: local tamper checks alone must not be represented as strong license enforcement.

## Non-Code Prerequisites

Some blockers cannot be solved by patching this repository alone:

- GitHub remote and Actions execution require repository access.
- VM installer proof requires a disposable Windows VM or Sandbox.
- Signing requires certificate procurement and secure secret handling.
- OS cleanup requires human review of private external data.
- Website release target requires a product/release ownership decision.
- License integrity requires a product/security decision if PublicRC includes paid entitlement enforcement.
