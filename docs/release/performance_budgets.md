# Performance Budgets

These budgets are conservative release-candidate targets. Phase 4A treats most performance checks as warn-only to avoid flaky failures across local machines and CI runners.

| Check | Target | Phase 4A behavior |
| --- | ---: | --- |
| Eval Suite `--all` | under 30 seconds | measured, warn-only by default |
| Quick Gate | under 5 minutes local | documented target |
| Full Gate | under 15 minutes local | documented target |
| Electron Startup Health Smoke | under 20 seconds | test timeout / smoke-controlled |
| Backend `/health` response in smoke | under 2 seconds | smoke-controlled local endpoint |
| Packaging Config Smoke | under 30 seconds without `-Build` | measured by script runtime |
| Packaging Build Smoke | machine-dependent | manual `-Build`, not CI default |

## Hard-Fail Policy

Release-blocking performance failures should be enabled only after the metric is stable across multiple local and CI runs.

Current hard failures:

- Eval suite command exits non-zero.
- Electron startup smoke fails readiness/security assertions.
- Packaging smoke finds forbidden user data or secrets in artifacts.

Current warnings:

- Eval suite runtime above target.
- Missing optional website build setup.
- Missing OS mount in CI.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_performance_budgets.ps1
```

Use `-Strict` only when you intentionally want local budget overruns to fail.
