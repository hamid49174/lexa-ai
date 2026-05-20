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
