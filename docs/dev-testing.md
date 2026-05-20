# Lexa Quality Gates

Run these gates before committing security, bridge, plugin, OS-agent, or frontend rendering changes.

## Quick Gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
```

Quick runs:

- `git diff --check`
- risky-path staged check
- Python phase gate for local auth, companion confirmation, router companion, AI tool selection, CSP, Hermes, OS agent runtime, plugin permissions, eval runner schema, and the Plan/Act/Verify agent protocol
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

## Eval Suite

Phase 3A adds an offline eval scaffold under `evals/`. Run it directly with:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --tasks evals\golden_tasks
```

Golden tasks are JSONL records that describe an input, expected behavior, forbidden behavior, risk level, and deterministic assertions. They cover tool selection, memory, OS drafts, prompt injection, local security, and answer quality.

Generated eval reports are local evidence only. If you write reports with `--output-json` or `--output-md`, keep them under `evals/results/`; Git ignores generated files in that directory.

## Agent Protocol

`backend/agent_protocol.py` defines the Phase 3A Plan/Act/Verify/Review ledger models. The runtime does not consume them yet. The goal is to make later agent work measurable and auditable before introducing new autonomy.

The protocol keeps these boundaries explicit:

- `PLAN`: goal, risk, allowed and forbidden tools, budgets, checkpoints, and user-review requirement.
- `ACT`: action type, scope, reason, reversibility, confirmation requirement, and status.
- `VERIFY`: checks, pass/fail result, artifacts, and redacted logs.
- `REVIEW`: summary, user decision points, rollback, approval references, and remaining risks.

High and critical plans require user review. High and critical actions require confirmation. Ledger JSON is stable and redacts token/API-key shaped values.
