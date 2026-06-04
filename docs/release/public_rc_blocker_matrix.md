# PublicRC Blocker Matrix

Phase 4F turned the remaining PublicRC work into explicit blockers, warnings, owners, and next actions. Phase 5A keeps those blockers concrete: each item is either practically testable in this repo or explicitly marked as an external prerequisite. Phase 5B separates what the agent can still harden from what requires a user decision or external infrastructure proof. This file is a release-readiness artifact, not a product feature plan.

| Blocker ID | Area | Status | InternalRC impact | PublicRC impact | PublicRelease impact | Why it matters | What is missing | Next concrete step | Owner | Can code help | Needs external prerequisite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PRC-001 | CI | not proven | warning | blocking | blocking | Remote CI proves the clean repository works outside the local workstation. | GitHub remote is configured, but no Actions run is recorded for the current commit. | Push branch, run `.github/workflows/quality-gates.yml`, record run URL and SHA. | user | yes | yes |
| PRC-002 | Installer | not proven | warning | blocking | blocking | Installer install/uninstall must be proven outside the productive machine. | Disposable VM or Windows Sandbox execution evidence. | Run `scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Install -Uninstall -VMOnly` inside an approved VM flow. | user | yes | yes |
| PRC-003 | Signing | blocked | warning | blocking | blocking | Unsigned installers create trust and SmartScreen problems. | Code signing certificate and secure signing process. | Obtain certificate, configure signing outside Git, rerun packaging and installer smoke. | user / external | yes | yes |
| PRC-004 | Website | partly proven | warning | blocking | blocking | Website release needs reproducible validation and real public runtime config. | Package-based static lint and ignored runtime-config path exist, but real public Supabase/Stripe values are not supplied. | Create `config.runtime.js` from `config.runtime.example.js` outside Git and rerun website smoke for the public target. | user | yes | partly |
| PRC-005 | OS | external | warning | blocking | blocking | Dirty external OS state can hide user data, generated drafts, or unreviewed changes. | Human-reviewed cleanup decision in the OS repo. | Run backup-first OS cleanup review as a separate project with OS gates before and after. | user | yes | yes |
| PRC-006 | Website | policy encoded, approval required | warning | blocking | blocking | The website still needs an approved public script/CSP policy. | Auth/Dashboard CSP is encoded and linted, Supabase is vendored, and Stripe.js is intentionally external; release-owner approval for the CSP/external-script policy is not recorded. | Approve the Stripe.js allowlist/CSP policy before PublicRC. | user/security | yes | partly |
| PRC-007 | Privacy | not proven | warning | warning | blocking | Public releases need explicit policy for traces, reports, and consent. | Checklist exists, but public privacy/trace consent is not reviewed or approved. | Review `docs/release/privacy_trace_consent_checklist.md` and record release-owner approval. | user | yes | yes |
| PRC-008 | Signing | blocked | warning | blocking | blocking | Signing secrets must never enter Git or build artifacts. | Secret-store or protected CI signing design. | Keep keys out of repo, use secure store/GitHub Secrets only after remote CI exists. | user / external | yes | yes |
| PRC-009 | CI | not proven | warning | blocking | blocking | Remote runners may not have OS/Hermes/Website local paths. | Remote skip/warn behavior must be observed in Actions. | Run remote CI and confirm local-only gates skip or warn honestly. | user | yes | yes |
| PRC-010 | Release | not proven | warning | blocking | blocking | Artifact policy must hold on the actual remote runner. | Remote proof that risky artifact scan blocks result/build/userdata paths. | Run remote CI with `scripts\check_risky_artifacts.ps1` and record outcome. | user | yes | yes |
| PRC-011 | License integrity | smoke ready | warning | blocking | blocking | Paid entitlement must be represented honestly and not rely on renderer-written local plan data. | Desktop activation now validates through the backend and blocks direct paid writes; `scripts\run_paid_license_smoke.ps1` exists, but a real paid license proof and release-owner entitlement policy still need approval. | Apply real Supabase/Stripe config, set `LEXA_LICENSE_SMOKE_KEY` outside Git, run `scripts\run_paid_license_smoke.ps1`, and record whether local checks are defense-in-depth only. | user / product | yes | partly |

## Phase 5B Action Classification

| Blocker | Category | Phase 5B result | Next action |
| --- | --- | --- | --- |
| Remote GitHub Actions proof | External infrastructure needed | GitHub remote is configured, but no remote Actions run has been recorded for the current commit. | User pushes branch, runs Actions, records run URL and SHA. |
| VM installer install/uninstall proof | User/external execution needed | Not proven by this workspace. Installer smoke can print readiness and plan; it does not install into the productive machine. | Run `scripts\run_installer_smoke.ps1 -InstallerPath <installer> -Install -Uninstall -VMOnly` only inside an approved disposable VM or Windows Sandbox. |
| Windows installer signing | External certificate decision needed | Prepared, not solved. No certificate, key, passphrase, or signing secret is present or allowed in Git. | Choose certificate/provider, store secrets outside Git, configure signing, rebuild, verify publisher. |
| Website release target | Partly solved locally | Website remains `static-external`, but a minimal website-local package/lint target, Supabase vendor bundle, and ignored runtime-config path now exist. | Supply `config.runtime.js` outside Git and decide whether a separate website repo/CI is needed before PublicRC. |
| OS cleanup review | User review needed | Not started. Lexa only records category-level inventory; OS remains external and dirty. | Run a separate backup-first OS cleanup project with OS gates before and after. |
| Privacy/trace consent | User/legal/product decision needed | Checklist exists, not approved. | Review consent, retention, opt-in/opt-out, export/delete, provider-use, and public documentation decisions. |
| Website CDN/SRI/CSP | User/security review needed | Supabase is vendored locally; Auth/Dashboard CSP is linted; Stripe.js is the only allowlisted external runtime script. | Approve Stripe.js/CSP policy and record the decision for PublicRC. |
| Public artifact policy | External CI proof needed | Local risky-artifact checks pass; remote runner behavior is not proven. | Prove risky artifact policy in GitHub Actions without publishing build/eval/trace artifacts. |
| Remote CI artifact policy | External CI proof needed | Workflow is designed to avoid result/build artifact uploads, but no remote run exists. | Run GitHub Actions and confirm no release artifacts, eval results, traces, logs, or userdata are uploaded. |
| PublicRelease legal/privacy docs | User/legal/product decision needed | Privacy checklist exists, not release-owner approved. | Complete and approve public privacy/release notes before PublicRelease. |
| License integrity model | User/product/security decision needed | Desktop paid activation is server-backed, renderer direct paid writes are blocked, and a paid-license smoke script now validates the backend response without printing the key. | Run `scripts\run_paid_license_smoke.ps1` with real Supabase/Stripe config and record the entitlement policy before PublicRC. |

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

- Remote CI remains external because the configured GitHub remote still needs a recorded Actions run for the current commit.
- VM installer install/uninstall remains external because this repository cannot prove an isolated Windows VM run by itself.
- Signing remains external because no certificate, key, passphrase, or signing secret is present or allowed in Git.
- Website remains `static-external` for InternalRC. PublicRC remains blocked until ignored `config.runtime.js` public values and Stripe.js/CSP approval are recorded.
- OS cleanup remains external and backup-first. No OS cleanup starts from Lexa release hardening.
- Privacy/trace consent now has a checklist, but PublicRelease remains blocked until the release owner approves it.

## Phase 5B Status

- Remote CI remains an external/user blocker: the GitHub remote is configured, but no remote Actions run is recorded yet and push/run approval is still required.
- VM installer proof remains not proven: the script can report VM/Sandbox readiness and print the proof plan, but no real install/uninstall was executed.
- Signing remains blocked by external certificate and secret-store decisions. InternalRC can warn; PublicRC/PublicRelease require a signed installer.
- Website remains `static-external` with local package/lint proof; PublicRC remains blocked until ignored `config.runtime.js` values and Stripe.js/CSP approval are recorded.
- OS cleanup remains a separate backup-first review project; Lexa does not stage, delete, archive, or commit OS data.
- Privacy/trace consent is now concrete enough for review, but not approved for PublicRelease.
- License integrity is smoke-ready: desktop paid activation is server-backed, renderer direct paid writes are blocked, and PublicRC now needs the paid-license smoke plus an explicit entitlement policy.

## Non-Code Prerequisites

Some blockers cannot be solved by patching this repository alone:

- GitHub Actions execution requires repository access and push/run approval.
- VM installer proof requires a disposable Windows VM or Sandbox.
- Signing requires certificate procurement and secure secret handling.
- OS cleanup requires human review of private external data.
- Website public config and Stripe.js/CSP policy require product/release ownership decisions.
- License integrity requires real paid-license smoke proof and a product/security decision if PublicRC includes paid entitlement enforcement.
