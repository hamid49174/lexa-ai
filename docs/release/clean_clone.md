# Clean Clone Smoke

The clean clone smoke proves that Lexa can be copied into a source-only workspace without local user data, generated reports, build artifacts, or mounted Personal OS content.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1
```

Safe default behavior:

- creates a source-only copy in a temp directory
- copies only Git-visible source files plus current untracked source files
- refuses risky paths such as `personal_os/`, `tmp/`, `vendor/`, `hermes_workspace/`, `lexa_memory.db*`, `audit.log`, `bridge-audit.log`, `evals/results/`, and build outputs
- does not delete files
- does not stage or commit anything

Optional modes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install -RunQuickGate
```

`-Install` creates a venv and installs Python/frontend dependencies inside the clean copy. Use it only when dependency installation is intended. `-RunQuickGate` requires `-Install`.

Phase 4B status: source-only clean copy is release-blocking. Full clean install is still a heavier proof step and may be run before a public RC.
