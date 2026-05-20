# Personal OS Repo Cleanup Plan

The Personal OS is mounted from:

`C:\Users\admin\OneDrive\Desktop\OS`

Lexa sees it through `personal_os/`, which is a local external mount/junction. It must not be staged or committed as Lexa source.

Phase 4B observed state:

- OS repo is dirty before Phase 4B work
- modified Markdown/index files exist
- many untracked drafts exist under `06_Inbox/Drafts/`
- event log and raw inbox paths exist
- MCP/Raw-Inbox integration folders are present
- this phase did not stage, commit, delete, migrate, archive, or clean OS files

Phase 4C status:

- OS remains a separate dirty Git repository.
- Lexa release hardening did not modify, stage, commit, delete, migrate, archive, or clean OS files.
- OS gates may still be run as validation, but cleanup is a separate review project.

Phase 4D status:

- OS remains a separate dirty Git repository.
- Lexa Phase 4D did not modify, stage, commit, delete, migrate, archive, or clean OS files.
- The cleanup is now an explicit review project, not part of Lexa release hardening.
- See `docs/release/os_cleanup_inventory.md` for the safe category-level inventory.

Phase 4E status:

- OS remains a separate dirty Git repository.
- Lexa Phase 4E did not modify, stage, commit, delete, migrate, archive, or clean OS files.
- The observed dirty state is still category-level only in Lexa docs: tracked Markdown/index changes plus untracked draft/event/raw/automation/MCP/workflow paths.
- PublicRC remains blocked until this cleanup risk is reviewed or explicitly accepted by the release owner.

Classification approach for a future cleanup project:

| Category | Examples | Recommendation |
| --- | --- | --- |
| Productive Markdown changes | indexes, dashboards, Lexa architecture/product docs | Review and commit in OS repo only after human approval |
| Drafts | `06_Inbox/Drafts/*.md` | Preserve; apply/reject/archive only through draft workflow |
| Events | `00_System/Events/events.jsonl` | Preserve as audit/history unless explicitly rotated |
| Raw Inbox | `06_Inbox/Raw/` | Review as user-owned input |
| Smoke outputs | MCP/Raw-Inbox smoke drafts or notes | Archive only after backup and approval |
| Generated dependencies | `node_modules`, build outputs | Ignore/clean only in a separate approved cleanup task |
| Potential secrets | env files, logs, private imports | Quarantine/review, never commit blindly |

Rules:

- no OS cleanup inside Lexa release hardening unless explicitly requested
- no deletion without backup/risk review
- no `git add .`
- no draft/event history loss
- OS quality gates may run, but should not mutate durable state

Recommended next project:

Create a separate OS cleanup branch or task, take a backup/snapshot, classify every dirty path, then commit only reviewed source-of-truth changes in the OS repo.

Minimum cleanup workflow:

1. Snapshot OS `git status --short` and `git diff --stat`.
2. Back up Drafts, Events, Raw Inbox, Rollups, and Workflows.
3. Classify each path as keep, review, archive, or quarantine.
4. Run OS SDK, MCP, Raw-Inbox, and Draft gates before any cleanup.
5. Apply only approved Draft/Event actions through the OS approval workflow.
6. Run OS gates again after cleanup.
7. Commit reviewed OS source changes in the OS repo only.

Release tier impact:

- InternalRC: dirty external OS is allowed with documentation and green OS gates.
- PublicRC: dirty OS cleanup risk must be reviewed by a human before release.
- PublicRelease: OS cleanup plan must be complete or explicitly accepted by the release owner.

Phase 4F readiness:

- The OS dirty state is now represented in `docs/release/public_rc_blocker_matrix.md` as PRC-005.
- The next action is not a Lexa code patch. It is a separate backup-first OS cleanup review.
- Lexa release scripts may warn or block by tier, but must not stage, delete, archive, migrate, or commit OS files.

Phase 5A status:

- OS cleanup is operationally ready but not started.
- The OS dirty state is summarized only by category and counts in `docs/release/os_cleanup_inventory.md`.
- No OS file is staged, committed, deleted, archived, migrated, or cleaned by Lexa Phase 5A.
- PublicRC remains blocked until the OS cleanup risk is reviewed or explicitly accepted by the release owner.

Phase 5A start criteria for the separate OS cleanup project:

1. User approves a dedicated OS cleanup task.
2. Backup/snapshot is created first.
3. OS gates run before any cleanup action.
4. Drafts, events, raw inbox, rollups, and workflow files are reviewed manually.
5. Smoke artifacts are archived only after approval.
6. OS gates run after cleanup.
7. Any OS commit happens in the OS repo only.
