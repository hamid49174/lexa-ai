# OS Cleanup Inventory

This is a category-level inventory for the external Personal OS repository at `C:\Users\admin\OneDrive\Desktop\OS`. It deliberately does not copy private OS/Obsidian content into the Lexa repository.

## Phase 4E Snapshot

The external OS repository is still dirty and was not modified, staged, committed, cleaned, archived, or deleted by Phase 4E work.

Observed counts from `git status --short` and `git diff --stat`:

- tracked modified files: 16
- tracked diff size: 261 insertions, 66 deletions
- untracked paths: many draft/event/raw/automation/MCP/workflow paths

These counts are intentionally category-level. Private filenames and content should stay in the OS review project, not in Lexa release docs.

## Observed Categories

The OS repo remains dirty and separate. Observed categories include:

- modified source-of-truth Markdown/index files
- modified Lexa architecture/product/task notes inside OS
- modified OS agent instructions
- untracked event log path
- untracked workflow files
- untracked rollup/context paths
- untracked draft files, including smoke-related drafts
- untracked raw inbox paths
- untracked automation log/run paths
- untracked MCP/Raw-Inbox integration paths

## Classification

| Category | Action |
| --- | --- |
| Productive Markdown/index changes | Review, then commit in OS repo only if approved |
| Draft files | Preserve; apply/reject/archive only through OS draft workflow |
| Event logs | Preserve; rotate only with explicit backup and approval |
| Raw inbox files | Review as user-owned input |
| Smoke-related drafts/logs | Archive only after backup and explicit approval |
| MCP/Worker integration source | Review separately from user data |
| Generated dependencies/build output | Ignore or clean only in a separate approved cleanup task |
| Potential secrets/private imports | Quarantine and review; never commit blindly |

## Operational Cleanup Flow

1. Take an OS backup/snapshot.
2. Run OS quality gates before cleanup.
3. Export `git status --short` and `git diff --stat` for review.
4. Classify every dirty path as keep, review, archive, backup-needed, or quarantine.
5. Do not delete drafts, events, raw inbox entries, or rollups without human review.
6. Apply approved draft/event actions through OS workflows.
7. Run OS quality gates after cleanup.
8. Commit only reviewed source-of-truth changes in the OS repo.

## Release Impact

This dirty state does not block InternalRC if OS gates are green and OS remains external/uncommitted. It blocks PublicRC/PublicRelease until the cleanup risk is reviewed or accepted by the release owner.
