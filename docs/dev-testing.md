# Lexa Quality Gates

Run these gates before committing security, bridge, plugin, OS-agent, or frontend rendering changes.

## Quick Gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_quality_gates.ps1 -Mode Quick
```

Quick runs:

- `git diff --check`
- risky-path staged check
- Python phase gate for local auth, companion confirmation, router companion, AI tool selection, CSP, Hermes, OS agent runtime, plugin permissions, eval adapters, agent simulations, trend reports, policy dashboard, trace replay, trace sampling, synthetic trace generation, and the Plan/Act/Verify agent protocol
- offline eval suite with `venv\Scripts\python.exe evals\runners\run_eval_suite.py --all`
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

Phase 3B adds suite and adapter modes:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --list-suites
venv\Scripts\python.exe evals\runners\run_eval_suite.py --suite tool_selection
venv\Scripts\python.exe evals\runners\run_eval_suite.py --all
```

Golden tasks are JSONL records that describe an input, expected behavior, forbidden behavior, risk level, and deterministic assertions. They cover tool selection, memory, OS drafts, prompt injection, local security, answer quality, synthetic trace replay, Plan/Act/Verify, and agent simulation. Local adapters may use synthetic fixtures, temp roots, and pure functions only.

Generated eval reports are local evidence only. If you write reports with `--output-json` or `--output-md`, keep them under `evals/results/`; Git ignores generated files in that directory.

Do not use real user data in evals. In particular, do not read or write `lexa_memory.db`, do not point an eval fixture at `personal_os/`, and do not call external APIs, real MCP servers, or network services.

Trace replay is available with:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --suite trace_replay
```

Trace fixtures must be synthetic. Runtime trace sampling writes only when both `LEXA_AGENT_TRACE=1` and `LEXA_AGENT_TRACE_SAMPLING=1` are set and the run is marked as synthetic/test context. Real runtime traces are local artifacts and must stay in ignored paths such as `evals/results/traces/` or `tmp/agent_traces/`.

Generate synthetic traces locally:

```powershell
venv\Scripts\python.exe evals\runners\generate_synthetic_traces.py --output-dir evals\results\traces\generated
venv\Scripts\python.exe evals\runners\run_eval_suite.py --suite trace_replay --trace-dir evals\results\traces\generated
```

The eval runner can also generate and replay in one command:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --suite trace_replay --generate-synthetic-traces --trace-dir evals\results\traces\generated
```

Plan/Act/Verify regression evals live in `evals/golden_tasks/plan_act_verify.jsonl` and use synthetic fixtures only. They check plans, budgets, checkpoints, approval requirements, verification behavior, and review creation.

Agent simulation evals live in `evals/golden_tasks/agent_simulation.jsonl` and run through local mock tools only:

- `mock_memory_search`
- `mock_os_draft_create`
- `mock_companion_command`
- `mock_plugin_action`
- `mock_mcp_tool`
- `mock_verification`

Run them with:

```powershell
venv\Scripts\python.exe evals\runners\run_agent_simulation.py --list
venv\Scripts\python.exe evals\runners\run_agent_simulation.py --simulation safe_memory_lookup
venv\Scripts\python.exe evals\runners\run_eval_suite.py --suite agent_simulation
```

Trend reports and policy dashboards are local-only report tools:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --all --json-report evals\results\latest.json
venv\Scripts\python.exe evals\runners\eval_trend_report.py evals\results\previous.json evals\results\latest.json --output-md evals\results\trend.md
venv\Scripts\python.exe evals\runners\policy_dashboard.py evals\results\latest.json --output-md evals\results\policy_dashboard.md
```

Do not commit generated `evals/results/*.json`, `evals/results/*.md`, `evals/results/*.html`, trace JSONL files, or dashboard outputs. Use temp directories in tests and ignored `evals/results/` paths during local review.

## Agent Protocol

`backend/agent_protocol.py` defines the Phase 3A Plan/Act/Verify/Review ledger models. The runtime does not consume them yet. The goal is to make later agent work measurable and auditable before introducing new autonomy.

The protocol keeps these boundaries explicit:

- `PLAN`: goal, risk, allowed and forbidden tools, budgets, checkpoints, and user-review requirement.
- `ACT`: action type, scope, reason, reversibility, confirmation requirement, and status.
- `VERIFY`: checks, pass/fail result, artifacts, and redacted logs.
- `REVIEW`: summary, user decision points, rollback, approval references, and remaining risks.

High and critical plans require user review. High and critical actions require confirmation. Ledger JSON is stable and redacts token/API-key shaped values.

Phase 3B wires the ledger into `backend/agent_loop.py` behind `LEXA_AGENT_LEDGER=1`. With the flag off, the agent response shape is unchanged. With it on, runs include a redacted ledger for local verification and future eval traces.

Phase 3C adds two more feature flags:

- `LEXA_AGENT_TRACE=1`: writes redacted JSONL agent traces to an ignored trace directory. Optional `LEXA_AGENT_TRACE_DIR` can point to a temp or ignored path.
- `LEXA_AGENT_POLICY_ENFORCE=1`: enables the first Plan/Act/Verify policy checks in the agent loop. High/critical unsafe actions, forbidden tools, missing scopes, budget violations, and protected direct writes become review-required or blocked instead of silently proceeding.

Phase 3D tightens trace capture:

- `LEXA_AGENT_TRACE_SAMPLING=1`: required in addition to `LEXA_AGENT_TRACE=1` before trace writes are allowed.
- Sampling requires synthetic/test context by default.
- Sampling limits event count, metadata length, and output paths.
- `LEXA_AGENT_POLICY_ENFORCE=1` now also evaluates stricter tool, risky-tool, OS-write, memory-read, runtime, and retry budgets.

With these flags off, runtime behavior remains compatible with the pre-Phase-3C agent loop.
