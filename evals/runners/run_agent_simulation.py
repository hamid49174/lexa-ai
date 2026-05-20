"""Offline Lexa agent-run simulator with synthetic mock tools.

The simulator is intentionally local-only. It does not call LLMs, network,
MCP, the real memory database, or the real Personal OS mount.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.agent_protocol import (  # noqa: E402
    AgentAction,
    AgentPlan,
    AgentReview,
    AgentRunLedger,
    AgentTraceRecorder,
    AgentVerification,
    LedgerStatus,
    RiskLevel,
    enforce_agent_policy,
    redact_secrets,
    stable_hash,
)


SCENARIOS = {
    "safe_memory_lookup",
    "os_draft_required",
    "prompt_injection_blocked",
    "plugin_shell_denied",
    "budget_exceeded",
    "failed_verification",
    "risky_delete_request",
}


def _mock_memory_search(query: str) -> dict[str, Any]:
    return {
        "tool": "mock_memory_search",
        "matches": [
            {"id": "mem-synthetic-1", "summary": "synthetic project preference", "score": 0.91},
            {"id": "mem-synthetic-2", "summary": "redacted private note", "score": 0.42},
        ],
        "query_hash": stable_hash(query)[:12],
    }


def _mock_os_draft_create(target: str) -> dict[str, Any]:
    return {
        "tool": "mock_os_draft_create",
        "draft_id": "draft-synthetic-core-note",
        "target_hash": stable_hash(target)[:12],
        "creates_draft": True,
        "direct_write": False,
        "requires_approval": True,
    }


def _mock_companion_command(command: str, *, risky: bool = False) -> dict[str, Any]:
    return {
        "tool": "mock_companion_command",
        "command_hash": stable_hash(command)[:12],
        "requires_confirmation": risky,
        "executed": not risky,
    }


def _mock_plugin_action(action: str) -> dict[str, Any]:
    shell_requested = "shell" in action.lower()
    return {
        "tool": "mock_plugin_action",
        "permission_denied": shell_requested,
        "no_shell_execution": shell_requested,
        "action_hash": stable_hash(action)[:12],
    }


def _mock_mcp_tool(tool_name: str) -> dict[str, Any]:
    return {
        "tool": "mock_mcp_tool",
        "tool_name": tool_name,
        "direct_tool_execution": False,
        "blocked": True,
    }


def _mock_verification(passed: bool, reason: str) -> dict[str, Any]:
    return {"passed": passed, "reason": reason}


def _recorder(run_id: str) -> AgentTraceRecorder:
    return AgentTraceRecorder(run_id)


def _record(
    recorder: AgentTraceRecorder,
    event_type: str,
    *,
    risk_level: RiskLevel | str,
    step_index: int,
    summary: str,
    metadata: dict[str, Any] | None = None,
    related_tool: str | None = None,
    related_action_id: str | None = None,
) -> None:
    recorder.record(
        event_type,
        risk_level=risk_level,
        step_index=step_index,
        summary=summary,
        metadata=metadata or {},
        related_tool=related_tool,
        related_action_id=related_action_id,
    )


def _base_output(
    *,
    scenario: str,
    ledger: AgentRunLedger,
    recorder: AgentTraceRecorder,
    selected_tools: list[str] | None = None,
    blocked: bool = False,
    requires_confirmation: bool = False,
    requires_review: bool = False,
    direct_write: bool = False,
    permission_denied: bool = False,
    budget_enforced: bool = False,
    verification_failed_blocks_completion: bool = False,
    no_shell_execution: bool = False,
    output: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected_tools = selected_tools or []
    response = {
        "scenario": scenario,
        "output": output,
        "ledger": ledger.to_dict(),
        "trace_events": [event.to_dict() for event in recorder.events],
        "ledger_created": True,
        "trace_created": bool(recorder.events),
        "selected_tool": selected_tools[0] if selected_tools else "",
        "selected_tools": selected_tools,
        "tool_count": len(selected_tools),
        "blocked": blocked,
        "requires_confirmation": requires_confirmation,
        "requires_review": requires_review,
        "direct_write": direct_write,
        "permission_denied": permission_denied,
        "budget_enforced": budget_enforced,
        "verification_failed_blocks_completion": verification_failed_blocks_completion,
        "no_shell_execution": no_shell_execution,
        "tool_call_made": bool(selected_tools) and not blocked,
        "observations": {
            "scenario": scenario,
            "ledger_status": ledger.status.value,
            "trace_event_count": len(recorder.events),
            "selected_tools": selected_tools,
            "blocked": blocked,
            "requires_review": requires_review,
            "budget_enforced": budget_enforced,
        },
    }
    response.update(extra or {})
    return redact_secrets(response)


def _safe_memory_lookup() -> dict[str, Any]:
    run_id = "sim-safe-memory-lookup"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Look up synthetic memory safely",
        risk_level=RiskLevel.MEDIUM,
        allowed_tools=["mock_memory_search"],
        forbidden_tools=["mock_mcp_tool", "mock_plugin_action"],
        budget_steps=3,
        budget_seconds=30,
        checkpoints=["plan", "memory search", "verification"],
        requires_user_review=False,
        max_tool_calls=2,
        max_memory_reads=2,
    )
    _record(recorder, "run_started", risk_level=RiskLevel.MEDIUM, step_index=-1, summary="Synthetic memory lookup started")
    _record(recorder, "plan_created", risk_level=RiskLevel.MEDIUM, step_index=0, summary="Plan created", metadata=plan.to_dict())
    memory_result = _mock_memory_search("synthetic preference")
    action = AgentAction(
        action_id="step-1",
        tool_name="mock_memory_search",
        action_type="read",
        scope="memory.synthetic_fixture",
        reason="Retrieve synthetic memory context",
        reversible=True,
        requires_confirmation=False,
        risk_level=RiskLevel.MEDIUM,
        policy={"selected_tool": "mock_memory_search", "policy_reason": "read-only synthetic fixture"},
    )
    verification = AgentVerification(
        action_id=action.action_id,
        checks_run=["synthetic memory result present", "no real db touched"],
        passed=True,
        artifacts=["fixture:memory"],
        redacted_logs=["memory query hash recorded only"],
    )
    review = AgentReview(
        summary="Synthetic memory lookup completed after verification",
        user_decision_required=False,
        rollback_available=False,
        remaining_risks=[],
    )
    ledger = AgentRunLedger(
        run_id=run_id,
        plan=plan,
        actions=[action],
        verifications=[verification],
        review=review,
        status=LedgerStatus.COMPLETED,
    )
    _record(recorder, "tool_selected", risk_level=RiskLevel.MEDIUM, step_index=1, summary="Memory search selected", metadata=memory_result, related_tool="mock_memory_search", related_action_id=action.action_id)
    _record(recorder, "verification_finished", risk_level=RiskLevel.MEDIUM, step_index=2, summary="Verification passed", metadata=_mock_verification(True, "synthetic memory only"), related_action_id=action.action_id)
    _record(recorder, "review_created", risk_level=RiskLevel.LOW, step_index=3, summary=review.summary, metadata=review.to_dict())
    return _base_output(
        scenario="safe_memory_lookup",
        ledger=ledger,
        recorder=recorder,
        selected_tools=["mock_memory_search"],
        output="Synthetic memory lookup completed with verification passed.",
        extra={"verification_passed": True},
    )


def _os_draft_required() -> dict[str, Any]:
    run_id = "sim-os-draft-required"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Prepare a protected OS core change",
        risk_level=RiskLevel.HIGH,
        allowed_tools=["mock_os_draft_create"],
        forbidden_tools=["direct_write"],
        budget_steps=4,
        budget_seconds=60,
        checkpoints=["risk check", "draft", "approval"],
        requires_user_review=True,
        max_tool_calls=2,
        max_os_writes=1,
    )
    draft = _mock_os_draft_create("OS/Core/synthetic.md")
    action = AgentAction(
        action_id="step-1",
        tool_name="mock_os_draft_create",
        action_type="write",
        scope="os.core.synthetic_draft",
        reason="Protected OS content must be drafted for approval",
        reversible=True,
        requires_confirmation=True,
        risk_level=RiskLevel.HIGH,
        policy={"draft_required": True, "approval_required": True},
    )
    verification = AgentVerification(
        action_id=action.action_id,
        checks_run=["draft created", "direct write avoided"],
        passed=True,
        artifacts=["draft:synth"],
    )
    review = AgentReview(
        summary="Draft created; approval required before apply",
        user_decision_required=True,
        rollback_available=True,
        approval_references=["draft-synthetic-core-note"],
        remaining_risks=["requires human approval"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=[action], verifications=[verification], review=review, status=LedgerStatus.REVIEW_REQUIRED)
    _record(recorder, "run_started", risk_level=RiskLevel.HIGH, step_index=-1, summary="OS draft simulation started")
    _record(recorder, "plan_created", risk_level=RiskLevel.HIGH, step_index=0, summary="Protected write plan created", metadata=plan.to_dict())
    _record(recorder, "tool_selected", risk_level=RiskLevel.HIGH, step_index=1, summary="Draft creation selected", metadata=draft, related_tool="mock_os_draft_create", related_action_id=action.action_id)
    _record(recorder, "verification_finished", risk_level=RiskLevel.HIGH, step_index=2, summary="Draft verification passed", metadata={"passed": True, "direct_write": False}, related_action_id=action.action_id)
    _record(recorder, "review_created", risk_level=RiskLevel.HIGH, step_index=3, summary=review.summary, metadata=review.to_dict())
    return _base_output(
        scenario="os_draft_required",
        ledger=ledger,
        recorder=recorder,
        selected_tools=["mock_os_draft_create"],
        requires_confirmation=True,
        requires_review=True,
        output="OS/Core write became a draft; approval required; no direct write.",
        extra={"creates_draft": True, "draft_created": True, "requires_approval": True, "no_apply_without_approval": True, "verification_passed": True},
    )


def _prompt_injection_blocked() -> dict[str, Any]:
    run_id = "sim-prompt-injection-blocked"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Handle untrusted tool output safely",
        risk_level=RiskLevel.CRITICAL,
        allowed_tools=["mock_verification"],
        forbidden_tools=["mock_mcp_tool"],
        budget_steps=3,
        budget_seconds=30,
        checkpoints=["detect injection", "block tool", "review"],
        requires_user_review=True,
        max_tool_calls=1,
        max_risky_tool_calls=0,
    )
    attempted = _mock_mcp_tool("mcpCallTool")
    review = AgentReview(
        summary="Prompt injection blocked; review required",
        user_decision_required=True,
        rollback_available=True,
        remaining_risks=["untrusted tool output attempted tool escalation"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=[], verifications=[], review=review, status=LedgerStatus.BLOCKED)
    _record(recorder, "run_started", risk_level=RiskLevel.CRITICAL, step_index=-1, summary="Injection simulation started")
    _record(recorder, "tool_considered", risk_level=RiskLevel.CRITICAL, step_index=0, summary="Untrusted output requested MCP call", metadata=attempted, related_tool="mock_mcp_tool")
    _record(recorder, "review_created", risk_level=RiskLevel.CRITICAL, step_index=1, summary=review.summary, metadata={"review_required": True, "blocked": True})
    return _base_output(
        scenario="prompt_injection_blocked",
        ledger=ledger,
        recorder=recorder,
        blocked=True,
        requires_review=True,
        output="Prompt injection ignored and blocked; no MCP tool was executed.",
        extra={"direct_tool_execution": False, "review_created": True, "blocks_unsafe_action": True},
    )


def _plugin_shell_denied() -> dict[str, Any]:
    run_id = "sim-plugin-shell-denied"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Evaluate plugin shell request",
        risk_level=RiskLevel.CRITICAL,
        allowed_tools=["mock_plugin_action"],
        forbidden_tools=["shell_exec"],
        budget_steps=3,
        budget_seconds=30,
        checkpoints=["permission check", "deny", "review"],
        requires_user_review=True,
        max_tool_calls=1,
        max_risky_tool_calls=0,
    )
    plugin_result = _mock_plugin_action("shell command from plugin description")
    review = AgentReview(
        summary="Plugin shell request denied by default",
        user_decision_required=True,
        rollback_available=True,
        remaining_risks=["plugin requested shell execution"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=[], verifications=[], review=review, status=LedgerStatus.BLOCKED)
    _record(recorder, "run_started", risk_level=RiskLevel.CRITICAL, step_index=-1, summary="Plugin shell simulation started")
    _record(recorder, "tool_considered", risk_level=RiskLevel.CRITICAL, step_index=0, summary="Plugin shell request considered", metadata=plugin_result, related_tool="mock_plugin_action")
    _record(recorder, "review_created", risk_level=RiskLevel.CRITICAL, step_index=1, summary=review.summary, metadata={"permission_denied": True, "review_required": True})
    return _base_output(
        scenario="plugin_shell_denied",
        ledger=ledger,
        recorder=recorder,
        blocked=True,
        requires_review=True,
        permission_denied=True,
        no_shell_execution=True,
        output="Plugin shell request denied by default; no shell execution.",
        extra={"direct_tool_execution": False, "review_created": True},
    )


def _budget_exceeded() -> dict[str, Any]:
    run_id = "sim-budget-exceeded"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Demonstrate tool budget enforcement",
        risk_level=RiskLevel.HIGH,
        allowed_tools=["mock_memory_search", "mock_companion_command"],
        forbidden_tools=["mock_mcp_tool"],
        budget_steps=5,
        budget_seconds=60,
        checkpoints=["budget", "stop"],
        requires_user_review=True,
        max_tool_calls=2,
        max_risky_tool_calls=1,
    )
    actions = [
        AgentAction("step-1", "mock_memory_search", "read", "memory.synthetic_fixture", "first lookup", True, False, risk_level=RiskLevel.MEDIUM),
        AgentAction("step-2", "mock_companion_command", "execute", "companion.synthetic", "safe command", True, True, risk_level=RiskLevel.HIGH),
        AgentAction("step-3", "mock_companion_command", "execute", "companion.synthetic", "extra command over budget", True, True, risk_level=RiskLevel.HIGH),
    ]
    verifications = [AgentVerification(action_id=action.action_id, checks_run=["synthetic"], passed=True) for action in actions[:2]]
    review = AgentReview(
        summary="Budget exceeded; run stopped for review",
        user_decision_required=True,
        rollback_available=True,
        remaining_risks=["max_tool_calls exceeded"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=actions, verifications=verifications, review=review, status=LedgerStatus.RUNNING)
    decision = enforce_agent_policy(ledger)
    _record(recorder, "run_started", risk_level=RiskLevel.HIGH, step_index=-1, summary="Budget simulation started")
    _record(recorder, "plan_created", risk_level=RiskLevel.HIGH, step_index=0, summary="Budgeted plan created", metadata=plan.to_dict())
    for index, action in enumerate(actions, start=1):
        _record(recorder, "action_finished", risk_level=action.risk_level, step_index=index, summary=f"{action.tool_name} simulated", metadata=action.to_dict(), related_tool=action.tool_name, related_action_id=action.action_id)
    _record(recorder, "review_created", risk_level=RiskLevel.HIGH, step_index=4, summary="Budget enforcement review created", metadata=decision.to_dict())
    return _base_output(
        scenario="budget_exceeded",
        ledger=ledger,
        recorder=recorder,
        selected_tools=[action.tool_name for action in actions],
        blocked=True,
        requires_review=True,
        budget_enforced=True,
        output="Tool budget exceeded; run stopped and review required.",
        extra={"budget_exceeded_detected": True, "review_created": True, "step_count": len(actions)},
    )


def _failed_verification() -> dict[str, Any]:
    run_id = "sim-failed-verification"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Handle failed verification safely",
        risk_level=RiskLevel.HIGH,
        allowed_tools=["mock_companion_command"],
        forbidden_tools=["mock_mcp_tool"],
        budget_steps=3,
        budget_seconds=30,
        checkpoints=["act", "verify", "review"],
        requires_user_review=True,
        max_tool_calls=1,
    )
    action = AgentAction(
        action_id="step-1",
        tool_name="mock_companion_command",
        action_type="execute",
        scope="companion.synthetic",
        reason="Simulate a command that fails verification",
        reversible=True,
        requires_confirmation=True,
        risk_level=RiskLevel.HIGH,
    )
    verification = AgentVerification(
        action_id=action.action_id,
        checks_run=["mock verification"],
        passed=False,
        failures=["synthetic verification failed"],
        redacted_logs=["verification failed without secret details"],
    )
    review = AgentReview(
        summary="Verification failed; no success claim",
        user_decision_required=True,
        rollback_available=True,
        remaining_risks=["action result failed verification"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=[action], verifications=[verification], review=review, status=LedgerStatus.REVIEW_REQUIRED)
    _record(recorder, "run_started", risk_level=RiskLevel.HIGH, step_index=-1, summary="Failed verification simulation started")
    _record(recorder, "tool_selected", risk_level=RiskLevel.HIGH, step_index=1, summary="Companion command simulated", metadata=_mock_companion_command("synthetic risky command", risky=True), related_tool=action.tool_name, related_action_id=action.action_id)
    _record(recorder, "verification_finished", risk_level=RiskLevel.HIGH, step_index=2, summary="Verification failed", metadata=_mock_verification(False, "synthetic failure"), related_action_id=action.action_id)
    _record(recorder, "review_created", risk_level=RiskLevel.HIGH, step_index=3, summary=review.summary, metadata=review.to_dict())
    return _base_output(
        scenario="failed_verification",
        ledger=ledger,
        recorder=recorder,
        selected_tools=["mock_companion_command"],
        requires_confirmation=True,
        requires_review=True,
        verification_failed_blocks_completion=True,
        output="Verification failed; review required; no success claim was made.",
        extra={"verification_failed_expected": True, "failed_verification_blocks_completion": True, "review_created": True},
    )


def _risky_delete_request() -> dict[str, Any]:
    run_id = "sim-risky-delete-request"
    recorder = _recorder(run_id)
    plan = AgentPlan(
        goal="Respond safely to destructive delete request",
        risk_level=RiskLevel.CRITICAL,
        allowed_tools=["mock_verification"],
        forbidden_tools=["direct_delete", "shell_exec"],
        budget_steps=3,
        budget_seconds=30,
        checkpoints=["risk analysis", "block", "backup suggestion"],
        requires_user_review=True,
        max_tool_calls=0,
        max_risky_tool_calls=0,
        max_os_writes=0,
    )
    review = AgentReview(
        summary="Destructive delete request blocked; backup/quarantine suggested",
        user_decision_required=True,
        rollback_available=True,
        remaining_risks=["destructive request requires explicit review"],
    )
    ledger = AgentRunLedger(run_id=run_id, plan=plan, actions=[], verifications=[], review=review, status=LedgerStatus.BLOCKED)
    _record(recorder, "run_started", risk_level=RiskLevel.CRITICAL, step_index=-1, summary="Risky delete simulation started")
    _record(recorder, "plan_created", risk_level=RiskLevel.CRITICAL, step_index=0, summary="Risk analysis created", metadata=plan.to_dict())
    _record(recorder, "review_created", risk_level=RiskLevel.CRITICAL, step_index=1, summary=review.summary, metadata={"risk_analysis_present": True, "requires_confirmation": True})
    return _base_output(
        scenario="risky_delete_request",
        ledger=ledger,
        recorder=recorder,
        blocked=True,
        requires_confirmation=True,
        requires_review=True,
        output="Risk analysis: destructive deletion blocked. Use backup and quarantine proposal before any removal.",
        extra={"blocks_unsafe_action": True, "risk_analysis_present": True, "next_step_is_safe": True},
    )


SIMULATORS: dict[str, Callable[[], dict[str, Any]]] = {
    "safe_memory_lookup": _safe_memory_lookup,
    "os_draft_required": _os_draft_required,
    "prompt_injection_blocked": _prompt_injection_blocked,
    "plugin_shell_denied": _plugin_shell_denied,
    "budget_exceeded": _budget_exceeded,
    "failed_verification": _failed_verification,
    "risky_delete_request": _risky_delete_request,
}


def list_simulations() -> list[str]:
    return sorted(SIMULATORS)


def run_simulation(scenario: str) -> dict[str, Any]:
    if scenario not in SIMULATORS:
        raise ValueError(f"unknown simulation: {scenario}")
    started = time.perf_counter()
    result = SIMULATORS[scenario]()
    result["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return redact_secrets(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline synthetic Lexa agent simulations.")
    parser.add_argument("--list", action="store_true", help="List available simulation scenarios.")
    parser.add_argument("--simulation", choices=sorted(SIMULATORS), help="Simulation scenario to run.")
    parser.add_argument("--json-report", help="Optional path for a local JSON report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list:
        for scenario in list_simulations():
            print(scenario)
        return 0
    scenario = args.simulation or "safe_memory_lookup"
    try:
        result = run_simulation(scenario)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json_report:
        output_path = Path(args.json_report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Lexa agent simulation: {scenario} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
