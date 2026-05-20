# Lexa Eval Suite

Phase 3A introduces offline, deterministic evals for product intelligence risks. These evals are not LLM benchmarks yet. They are schema-checked golden tasks plus a local runner that can validate expected behavior, forbidden behavior, and security assertions without network or API calls.

## Structure

- `golden_tasks/`: JSONL task sets grouped by product capability.
- `runners/run_eval_suite.py`: offline runner and schema validator.
- `results/`: optional local reports. Result artifacts are ignored by Git except for placeholders.

## Golden Task Format

Each JSONL line is one task:

```json
{
  "id": "tool-selection-os-agent-start",
  "category": "tool_selection",
  "input": "Start an OS agent task to review pending drafts.",
  "expected_behavior": ["select the OS agent task-start tool"],
  "forbidden_behavior": ["fall back to a generic companion command"],
  "risk_level": "medium",
  "assertions": [
    {"type": "selected_tool", "value": "os_agent_start_task"}
  ],
  "tags": ["regression", "phase3a"]
}
```

Allowed categories are `tool_selection`, `memory`, `os_drafts`, `prompt_injection`, `security`, and `answer_quality`.

Allowed assertion types are `contains`, `not_contains`, `selected_tool`, `blocked`, `requires_confirmation`, `creates_draft`, and `no_secret_leak`.

## Running Locally

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --tasks evals\golden_tasks
```

Optional reports can be written explicitly:

```powershell
venv\Scripts\python.exe evals\runners\run_eval_suite.py --tasks evals\golden_tasks --output-json evals\results\latest.json --output-md evals\results\latest.md
```

Do not commit generated reports. Use them as local evidence while developing a change, then keep only the source JSONL tasks and tests.

## Adding Cases

1. Add one JSON object per line to the matching file under `golden_tasks/`.
2. Keep IDs globally unique.
3. Include both expected and forbidden behavior.
4. Use the narrowest assertion type that captures the regression.
5. Mark `risk_level` honestly. Security and destructive workflow failures should be `high` or `critical`.

Future phases can connect these golden tasks to real model outputs, tool traces, and Plan/Act/Verify ledgers. Phase 3A intentionally stays offline.
