# Release Candidate Checklist

Use this checklist before calling any build a Lexa release candidate. Do not deploy, upload, publish, or sign anything until every blocking gate is green or explicitly reviewed.

## 1. Security Gates

- [ ] Local Auth tests are green.
- [ ] `/health` does not expose instance tokens or secrets.
- [ ] Companion Confirmation tests are green.
- [ ] Plugin Permissions tests are green.
- [ ] Preload Bridge high-risk gates are green.
- [ ] Electron CSP/DOM tests are green.
- [ ] OS Draft Approval gates are green.
- [ ] Secret redaction tests are green.
- [ ] Risky Artifact Check is green.

## 2. Eval Gates

- [ ] Eval Suite `--all` is green.
- [ ] Eval Regression Gate is green.
- [ ] No critical/high blocking failures.
- [ ] Failure Triage is empty or explicitly reviewed.
- [ ] Eval Baseline reflects the intended green behavior.

## 3. Agent Gates

- [ ] Agent Protocol tests are green.
- [ ] Trace Replay tests are green.
- [ ] Agent Simulation tests are green.
- [ ] Plan/Act/Verify evals are green.
- [ ] Budget Enforcement tests are green.

## 4. Runtime Gates

- [ ] Electron Startup Health Smoke is green.
- [ ] Electron Presence Smoke is green.
- [ ] Electron UI Visual Smoke is green.
- [ ] No EPIPE popup.
- [ ] No main-process error popup.
- [ ] `bridge-audit.log` is under userData, not the repo.
- [ ] FastAPI uses lifespan startup/shutdown handlers without deprecated `@app.on_event` warnings.

## 5. OS Gates

- [ ] OS SDK TypeScript check is green.
- [ ] OS Draft check is green.
- [ ] OS MCP Server check is green.
- [ ] Raw-Inbox Worker check is green.
- [ ] No draft deletion, migration, or archival happened during gates.
- [ ] No OS user data is staged or committed.

## 6. Hermes Gates

- [ ] Hermes Adapter tests are green.
- [ ] `hermes_workspace/` is not staged or committed.
- [ ] Hermes secrets are not in build artifacts.
- [ ] No real Telegram action was sent during smoke checks.

## 7. Website Gates

- [ ] Website smoke ran or clearly reported website path missing.
- [ ] Website build/lint is green if the website has a package setup.
- [ ] No Supabase/Stripe/private secrets are committed.
- [ ] `tmp_*.js` scratch/migration files are reviewed before deployment.
- [ ] External scripts/CDNs are reviewed for CSP/vendor strategy.
- [ ] No deployment occurred.

## 8. Packaging Gates

- [ ] Packaging smoke is green.
- [ ] Full packaging build with `scripts\run_packaging_smoke.ps1 -Build` has been attempted for release candidates.
- [ ] Installer smoke has checked the generated artifact or is explicitly marked not yet proven.
- [ ] Installer install/uninstall has been tested in a disposable VM, or release is marked Needs Review.
- [ ] Signing status is documented.
- [ ] Public release candidate installer is signed, or release is marked Needs Review.
- [ ] Build artifacts contain no `.env`.
- [ ] Build artifacts contain no `audit.log` or `bridge-audit.log`.
- [ ] Build artifacts contain no `lexa_memory.db*`.
- [ ] Build artifacts contain no `personal_os/` or OS vault data.
- [ ] Build artifacts contain no `hermes_workspace/`.
- [ ] Build artifacts are not staged or committed.

## 9. Repo Hygiene

- [ ] `git status --short` is clean before final release commit/tag.
- [ ] No `git add .` was used.
- [ ] No eval results are staged.
- [ ] No trace results are staged.
- [ ] No build artifacts are staged.
- [ ] No smoke artifacts are staged.
- [ ] No user data is staged.

## 10. Release Decision

- [ ] Ready
- [ ] Blocked
- [ ] Needs Review

## 10A. Release Tier

- [ ] InternalRC
- [ ] PublicRC
- [ ] PublicRelease

InternalRC can proceed with reviewed warnings for unsigned installer, VM install/uninstall not yet proven, remote CI not yet proven, external dirty OS, and static website gaps.

PublicRC additionally requires remote CI proof, signed installer, VM install/uninstall proof, reviewed OS cleanup risk, and a clear website release target.

PublicRelease additionally requires release signing, installer proof, website deployment workflow, trace/privacy consent review, and no open high/critical risks.

## 11. Phase 4B Freshness Gates

- [ ] Clean clone/copy smoke is green.
- [ ] CI core mode is green or CI runner failure is documented.
- [ ] Dependency reproducibility check has no release-blocking missing files.
- [ ] OS dirty state is documented and not accidentally committed through Lexa.
- [ ] Packaging/installer status is marked as proven, warning, or blocked.

## 12. Phase 4C Proof Gates

- [ ] Remote CI status is recorded as proven or not yet remotely proven.
- [ ] `scripts\run_quality_gates.ps1 -Mode CI` is green locally.
- [ ] `scripts\run_release_candidate_check.ps1 -Mode CICore` is green locally.
- [ ] Clean install plus Quick Gate has run, or exact blocker is documented.
- [ ] Eval/report output paths are unique per run and safe for parallel execution.
- [ ] `scripts\run_release_candidate_check.ps1 -Mode Packaging` is green for package proof.
- [ ] `scripts\run_release_candidate_check.ps1 -Mode Installer` is green or marked Needs Review.
- [ ] `scripts\run_release_candidate_check.ps1 -Mode StrictRC` reports Ready or Needs Review truthfully.
- [ ] Signing keys and certificates are absent from Git and staged files.

## 13. Phase 4D Tier Gates

- [ ] `scripts\run_release_candidate_check.ps1 -Target InternalRC` is green or Needs Review with only accepted warnings.
- [ ] `scripts\run_release_candidate_check.ps1 -Target PublicRC` is blocked until signing, remote CI, VM install/uninstall, website target, and OS cleanup risk are proven/reviewed.
- [ ] `scripts\run_release_candidate_check.ps1 -Target PublicRelease` is blocked until PublicRC requirements plus public release/privacy readiness are proven.
- [ ] Installer VM test plan exists.
- [ ] Signing plan defines Dev, InternalRC, PublicRC, and PublicRelease requirements.
- [ ] Website target is explicitly classified.
- [ ] OS cleanup inventory is category-level and does not copy private OS content.
- [ ] Codex context pack exists and excludes user data.

## 14. Phase 4E PublicRC Blocker Readiness

- [ ] `git remote -v` shows a GitHub remote, or Remote CI is explicitly marked not yet proven.
- [ ] Manual GitHub Actions proof steps are documented.
- [ ] Installer smoke supports `-Target`, `-ExpectedPublisher`, and `-AllowUnsignedInternal`.
- [ ] Unsigned installer is warn-only for InternalRC and blocking for PublicRC/PublicRelease.
- [ ] VM install/uninstall remains plan-only unless a disposable VM/sandbox is explicitly approved.
- [ ] Website release target remains `static-external` until a separate package/build/lint target is approved.
- [ ] OS cleanup remains separate and backup-first.
- [ ] Codex context pack can be regenerated from safe repository metadata without reading private OS/Obsidian content.

## 15. Phase 4F PublicRC Blocker Matrix

- [ ] PublicRC Blocker Matrix exists at `docs/release/public_rc_blocker_matrix.md`.
- [ ] Each PublicRC blocker has area, status, tier impact, missing proof, next action, owner, and external prerequisite status.
- [ ] `scripts\check_remote_ci_readiness.ps1` reports `RemoteCIReady`.
- [ ] RC check output contains blockers, warnings, next actions, and external prerequisites.
- [ ] InternalRC may remain Needs Review with accepted warnings.
- [ ] PublicRC remains blocked while remote CI, VM installer proof, signing, website target, OS cleanup review, remote runner availability, and artifact policy proof are not complete.
- [ ] PublicRelease remains blocked until PublicRC is complete and privacy/trace consent is reviewed.

## 16. Phase 5A External Blocker Operations

- [ ] Remote CI is either proven with a GitHub Actions run URL and commit SHA, or explicitly marked external because no GitHub remote exists.
- [ ] VM installer install/uninstall is either proven in a disposable VM/Sandbox, or explicitly marked not yet proven.
- [ ] Signing checklist is complete without committing certificates, keys, passphrases, or signing secrets.
- [ ] Website remains `static-external` for InternalRC, with PublicRC blocked until a build/lint or equivalent static-release target is approved.
- [ ] OS cleanup remains a separate backup-first review project; no OS data is deleted or staged from Lexa.
- [ ] `docs/release/privacy_trace_consent_checklist.md` exists.
- [ ] PublicRelease remains blocked until privacy/trace consent is reviewed and approved.

Decision notes:

- Blocking failures require a fix or explicit release-owner review.
- Warnings are acceptable only when documented with owner, reason, and follow-up.
- Baseline updates are allowed only from a fully green eval run and must never accept secret leaks or high/critical failures.
- `Ready` means every release-blocking gate is green and no unresolved release-review warning remains.
- `Needs Review` means all blocking gates are green, but unsigned installer, missing VM install/uninstall, remote-CI-not-proven, website build gaps, or external OS dirtiness still require owner signoff.
- `Blocked` means at least one release-blocking gate failed.
