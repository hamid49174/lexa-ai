# Repo Hygiene

Lexa keeps source code, local user data, generated artifacts, and external mounts close together during development. Treat them differently.

## Never Commit

- `personal_os/`: local Personal OS mount with private Markdown context.
- `tmp/`: scratch files and transient test output.
- `vendor/`: vendored or external working copies; review separately before any source import.
- `audit.log` and `bridge-audit.log`: local logs that can reveal private behavior or security events.
- `lexa_memory.db*`: local memory database and SQLite sidecars.
- `hermes_workspace/`: local Hermes runtime workspace and user/task data.
- build outputs: `dist/`, `backend-dist/`, `frontend/dist/`, `build/`.
- caches: `.pytest_cache/`, `.coverage`, `audio_cache/`, `node_modules/`, `venv/`.
- secrets: `.env`, `*.env`, `*.key`, `*.pem`, `*.p12`, and credential files.

## Personal OS Handling

`personal_os/` is an external local mount, not Lexa product source. OS source changes belong in the OS repository with its own snapshot and review flow. Do not move, archive, delete, or migrate Personal OS data from the Lexa repo hygiene pass.

## Logs And Databases

Audit logs and SQLite files are user data. They can contain private prompts, tool traces, paths, or operational metadata. Keep them local. If a bug requires a sample, create a redacted fixture instead of committing the live file.

## Build Artifacts

Build folders are reproducible output. Do not delete them during hygiene work unless there is a separate backup and risk review. Do not commit them unless a release packaging task explicitly requires it.

## Before Committing

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
```

Then verify staged files:

```powershell
git diff --cached --name-only
```

Never use `git add .` in this repo. Stage exact source, test, script, or doc files only.
