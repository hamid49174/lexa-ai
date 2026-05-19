# Lexa Quality Gates

Run these gates before committing security, bridge, plugin, OS-agent, or frontend rendering changes.

## Quick Gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
```

Quick runs:

- `git diff --check`
- risky-path staged check
- Python phase gate for local auth, companion confirmation, router companion, AI tool selection, CSP, Hermes, OS agent runtime, and plugin permissions
- every `tests/test_*.js` static test with Node

## Full Gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Full
```

Full runs everything in Quick, then:

- full Python suite with `venv\Scripts\python.exe -m pytest -q`
- Electron presence-challenge smoke
- Electron UI visual smoke

## Local Artifacts

Do not commit local or user-owned artifacts:

- `personal_os/`
- `tmp/`
- `vendor/`
- `audit.log`
- `bridge-audit.log`
- `lexa_memory.db*`
- `hermes_workspace/`
- build outputs such as `dist/`, `backend-dist/`, `frontend/dist/`, and `build/`

The quality-gate script warns when these paths are present and fails if risky paths are staged. It never deletes files.

## Notes

- There is no root `package.json` in this repo, so the canonical gate is the PowerShell script.
- Do not ignore or delete lockfiles blindly.
- Electron smoke tests require `frontend\node_modules\electron\dist\electron.exe`.
- `personal_os/` is treated as an external local mount. Review it separately and never commit it as Lexa source.
