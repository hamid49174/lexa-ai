# Packaging Smoke

Lexa uses Electron Builder from `frontend/electron-builder.json`.

Default smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1
```

This checks:

- `frontend/package.json` has a build script
- `frontend/electron-builder.json` exists
- builder config does not include broad parent-directory globs
- builder config does not include forbidden user-data paths
- existing artifact paths do not contain forbidden local data
- build artifacts are not staged

Full local build smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_packaging_smoke.ps1 -Build
```

When `-Build` is used, output is redirected to an isolated temp directory by default. The script requires `backend-dist/lexa-backend`, because the Electron package includes that backend resource.

Forbidden in packaged output:

- `.env` / `*.env`
- `audit.log`
- `bridge-audit.log`
- `lexa_memory.db*`
- `personal_os/`
- `hermes_workspace/`
- `evals/results/`
- `tmp/agent_traces/`
- real traces
- OS vault data
- private logs or secrets

The smoke does not publish, upload, sign, or delete artifacts.
