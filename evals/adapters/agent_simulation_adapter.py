from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from evals.adapters.base import build_result
from evals.runners.run_agent_simulation import run_simulation


def _scenario_for_task(task: dict[str, Any]) -> str:
    return str(task.get("simulation") or task.get("_simulation") or task["id"].replace("agent-simulation-", ""))


def evaluate(task: dict[str, Any], *, fixture_root: str | Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    simulation = run_simulation(_scenario_for_task(task))
    response = {
        "output": simulation.get("output", ""),
        "ledger_created": bool(simulation.get("ledger_created")),
        "trace_created": bool(simulation.get("trace_created")),
        "selected_tool": simulation.get("selected_tool", ""),
        "selected_tools": simulation.get("selected_tools", []),
        "blocked": bool(simulation.get("blocked")),
        "requires_confirmation": bool(simulation.get("requires_confirmation")),
        "requires_review": bool(simulation.get("requires_review")),
        "direct_write": bool(simulation.get("direct_write")),
        "permission_denied": bool(simulation.get("permission_denied")),
        "budget_enforced": bool(simulation.get("budget_enforced")),
        "verification_failed_blocks_completion": bool(simulation.get("verification_failed_blocks_completion")),
        "no_shell_execution": bool(simulation.get("no_shell_execution")),
        "creates_draft": bool(simulation.get("creates_draft") or simulation.get("draft_created")),
        "draft_created": bool(simulation.get("draft_created")),
        "requires_approval": bool(simulation.get("requires_approval")),
        "no_apply_without_approval": bool(simulation.get("no_apply_without_approval")),
        "direct_tool_execution": bool(simulation.get("direct_tool_execution")),
        "review_created": bool(simulation.get("review_created") or simulation.get("requires_review")),
        "verification_passed": bool(simulation.get("verification_passed")),
        "verification_failed_expected": bool(simulation.get("verification_failed_expected")),
        "risk_analysis_present": bool(simulation.get("risk_analysis_present")),
        "blocks_unsafe_action": bool(simulation.get("blocks_unsafe_action")),
        "next_step_is_safe": bool(simulation.get("next_step_is_safe")),
        "reason": f"offline agent simulation: {simulation.get('scenario')}",
        "observations": simulation.get("observations", {}),
    }
    result = build_result(task, response, started)
    result["duration_ms"] = int(simulation.get("duration_ms") or result["duration_ms"])
    return result
