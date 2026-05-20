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
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -NoInstall
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install -RunQuickGate
powershell -ExecutionPolicy Bypass -File scripts\run_clean_clone_smoke.ps1 -Install -RunQuickGate -KeepTemp
```

`-Install` creates a venv and installs Python/frontend dependencies inside the clean copy. It prefers `LEXA_PYTHON`, then `python`, then the current repo venv Python, then the `py` launcher. Use it only when dependency installation is intended. `-RunQuickGate` requires `-Install`.

`-NoInstall` makes the install skip explicit and cannot be combined with `-RunQuickGate`. The clean copy is retained for inspection; the script does not delete temporary folders.

Phase 4C status: source-only clean copy remains release-blocking. Clean install plus Quick Gate is the next stronger proof and must be reported separately from the source-only smoke.
