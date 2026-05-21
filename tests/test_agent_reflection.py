from backend.agent_reflection import (
    ReflectionDecision,
    reflect_action,
    should_reflect_action,
)


def test_low_risk_read_only_action_skips_reflection(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)
    decision = reflect_action("system_info", {}, permission="allowed", source="unit")
    assert decision is None


def test_high_risk_tool_triggers_reflection(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)
    assert should_reflect_action("file_delete", {"path": "x"}, permission="confirmation_required")

    decision = reflect_action("file_delete", {"path": "x"}, permission="confirmation_required", source="unit")

    assert decision is not None
    assert decision.risk_level == "critical"
    assert decision.requires_confirmation is True
    assert decision.verification_step


def test_confirmation_required_tool_triggers_reflection(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)

    decision = reflect_action("todo_delete", {"id": 7}, permission="confirmation_required", source="unit")

    assert decision is not None
    assert decision.requires_confirmation is True
    assert decision.should_execute is True


def test_malformed_reflection_fails_closed_for_risky_action(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)

    decision = reflect_action(
        "file_delete",
        {"path": "x"},
        permission="confirmation_required",
        source="unit",
        decision_factory=lambda context: {"should_execute": True},
    )

    assert decision is not None
    assert decision.should_execute is False
    assert decision.reason == "malformed_reflection_failed_closed"
    assert decision.safer_alternative is not None


def test_reflection_blocks_low_confidence_write_and_suggests_read_only_alternative(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)

    decision = reflect_action(
        "clipboard_write",
        {"text": "hello"},
        permission="allowed",
        source="unit",
        low_confidence=True,
    )

    assert decision is not None
    assert decision.should_execute is False
    assert decision.safer_alternative is not None
    assert decision.safer_alternative["mode"] == "read_only"


def test_reflection_audit_redacts_sensitive_argument_keys_and_values(monkeypatch):
    calls = []
    secret_value = "sk-test-super-secret-value"
    monkeypatch.setattr(
        "backend.agent_reflection.audit_log",
        lambda command, status, details="": calls.append((command, status, details)),
    )

    decision = reflect_action(
        "hermes_telegram_configure",
        {"botToken": secret_value, "homeChannel": "test"},
        permission="confirmation_required",
        source="unit",
    )

    assert decision is not None
    assert calls
    details = " ".join(str(call[2]) for call in calls)
    assert secret_value not in details
    assert "botToken" not in details
    assert "[REDACTED_KEY]" in details


def test_personal_os_write_like_action_triggers_reflection(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)

    decision = reflect_action(
        "os_agent_create_review_draft",
        {"task_id": "task-1"},
        permission="confirmation_required",
        source="unit",
    )

    assert decision is not None
    assert decision.risk_level == "high"
    assert decision.requires_confirmation is True


def test_reflection_feature_flag_can_disable_policy(monkeypatch):
    monkeypatch.setenv("AGENT_REFLECTION_ENABLED", "0")

    decision = reflect_action("file_delete", {"path": "x"}, permission="confirmation_required", source="unit")

    assert decision is None


def test_custom_valid_reflection_decision_is_accepted(monkeypatch):
    monkeypatch.delenv("AGENT_REFLECTION_ENABLED", raising=False)
    custom = ReflectionDecision(
        should_execute=True,
        risk_level="medium",
        confidence=0.7,
        concerns=["unit"],
        requires_confirmation=False,
        verification_step="verify",
        reason="custom",
    )

    decision = reflect_action(
        "clipboard_write",
        {"text": "hello"},
        permission="allowed",
        source="unit",
        decision_factory=lambda context: custom,
    )

    assert decision is not None
    assert decision.reason == "custom"
