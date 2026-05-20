import json

import pytest

from backend.agent_protocol import (
    AgentAction,
    AgentPlan,
    AgentReview,
    AgentRunLedger,
    AgentVerification,
    RiskLevel,
    redact_secrets,
)


def test_valid_plan_is_accepted():
    plan = AgentPlan(
        goal="Review OS drafts safely",
        risk_level="high",
        allowed_tools=["os_draft_queue", "os_draft_apply"],
        forbidden_tools=["shell"],
        budget_steps=5,
        budget_seconds=120,
        checkpoints=["prepare", "verify"],
        requires_user_review=True,
        created_at="2026-05-20T00:00:00Z",
    )

    assert plan.risk_level is RiskLevel.HIGH
    assert plan.to_dict()["requires_user_review"] is True


def test_invalid_risk_level_is_rejected():
    with pytest.raises(ValueError, match="invalid risk_level"):
        AgentPlan(goal="Bad risk", risk_level="urgent", requires_user_review=True)


def test_forbidden_tool_cannot_also_be_allowed():
    with pytest.raises(ValueError, match="forbidden tools"):
        AgentPlan(
            goal="Conflicting tools",
            risk_level="medium",
            allowed_tools=["shell"],
            forbidden_tools=["shell"],
        )


def test_high_or_critical_action_requires_confirmation():
    with pytest.raises(ValueError, match="require confirmation"):
        AgentAction(
            action_id="a1",
            tool_name="backupRestore",
            action_type="admin",
            scope="local",
            reason="Restore backup",
            reversible=False,
            requires_confirmation=False,
            risk_level="critical",
        )


def test_budget_limits_are_enforced():
    with pytest.raises(ValueError, match="budget_steps"):
        AgentPlan(goal="Too many steps", risk_level="low", budget_steps=51)
    with pytest.raises(ValueError, match="budget_seconds"):
        AgentPlan(goal="Too much time", risk_level="low", budget_seconds=3601)


def test_redaction_removes_api_keys_and_tokens():
    text = "api_key=sk-secret123 token: abcdefghij Authorization: Bearer abcdefghij"

    redacted = redact_secrets(text)

    assert "sk-secret123" not in redacted
    assert "abcdefghij" not in redacted
    assert "[REDACTED]" in redacted


def test_ledger_serializes_stably_and_redacts_logs():
    plan = AgentPlan(
        goal="Run a safe tool",
        risk_level="medium",
        allowed_tools=["memory_search"],
        budget_steps=3,
        budget_seconds=60,
        created_at="2026-05-20T00:00:00Z",
    )
    action = AgentAction(
        action_id="a1",
        tool_name="memory_search",
        action_type="read",
        scope="memory:metadata",
        reason="Find relevant preference",
        reversible=True,
        requires_confirmation=False,
        risk_level="low",
    )
    verification = AgentVerification(
        action_id="a1",
        checks_run=["unit"],
        passed=True,
        redacted_logs=["token=supersecretvalue"],
    )
    review = AgentReview(
        summary="Completed with approval reference api_key=sk-secret123",
        user_decision_required=False,
        rollback_available=True,
        approval_references=["draft-123"],
        remaining_risks=["none"],
    )
    ledger = AgentRunLedger(
        run_id="run-1",
        plan=plan,
        actions=[action],
        verifications=[verification],
        review=review,
        status="completed",
    )

    first = ledger.to_json()
    second = ledger.to_json()
    parsed = json.loads(first)

    assert first == second
    assert "supersecretvalue" not in first
    assert "sk-secret123" not in first
    assert parsed["review"]["approval_references"] == ["draft-123"]
    assert parsed["status"] == "completed"


def test_review_can_carry_rollback_and_approval_references():
    review = AgentReview(
        summary="Ready for user review",
        user_decision_required=True,
        rollback_available=True,
        approval_references=["confirmation:abc123", "draft:xyz789"],
        remaining_risks=["requires manual acceptance"],
    )

    payload = review.to_dict()

    assert payload["rollback_available"] is True
    assert payload["approval_references"] == ["confirmation:abc123", "draft:xyz789"]
