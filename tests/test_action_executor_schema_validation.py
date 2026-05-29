import time
from unittest.mock import patch

import pytest

from backend.action_executor import execute_action
from backend.agent_reflection import ReflectionDecision


@pytest.fixture(autouse=True)
def _reset_action_rate_budget():
    import backend.security as security
    for bucket in security._ACTION_RATE_LIMITS.values():
        bucket["entries"].clear()


def test_execute_action_rejects_schema_invalid_args_before_companion():
    with patch("backend.action_executor.is_command_allowed", return_value="allowed") as mock_perm, \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.reflect_action") as mock_reflect, \
         patch("backend.action_executor.audit_log"):
        result = execute_action(
            {"action": "app_open", "params": {"name": 123}},
            source="test",
        )

    assert result["success"] is False
    assert result["executed"] is False
    assert "Tool-Argumente ungueltig" in result["error"]
    mock_companion.execute.assert_not_called()
    mock_perm.assert_not_called()
    mock_reflect.assert_not_called()


def test_execute_action_unknown_tool_rejects_before_reflection_or_companion():
    with patch("backend.action_executor.is_command_allowed", return_value="allowed") as mock_perm, \
         patch("backend.action_executor.reflect_action") as mock_reflect, \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        result = execute_action(
            {"action": "hallucinated_tool", "params": {}},
            source="test",
        )

    assert result["success"] is False
    assert result["executed"] is False
    assert "Tool-Argumente ungueltig" in result["error"]
    mock_perm.assert_not_called()
    mock_reflect.assert_not_called()
    mock_companion.execute.assert_not_called()


def test_execute_action_valid_args_still_execute():
    with patch("backend.action_executor.is_command_allowed", return_value="allowed"), \
         patch("backend.action_executor.validate_params", side_effect=lambda command, params: params), \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        mock_companion.execute.return_value = {"success": True, "data": "ok"}
        result = execute_action(
            {"action": "app_open", "params": {"name": "notepad"}},
            source="test",
        )

    assert result["success"] is True
    assert result["executed"] is True
    mock_companion.execute.assert_called_once_with("app_open", {"name": "notepad"})


def test_execute_action_reflection_can_block_before_companion():
    blocked = ReflectionDecision(
        should_execute=False,
        risk_level="medium",
        confidence=0.2,
        concerns=["unit"],
        safer_alternative={"mode": "read_only"},
        requires_confirmation=False,
        verification_step="verify first",
        reason="unit_block",
    )
    with patch("backend.action_executor.is_command_allowed", return_value="allowed"), \
         patch("backend.action_executor.reflect_action", return_value=blocked) as mock_reflect, \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        result = execute_action(
            {"action": "app_open", "params": {"name": "notepad"}},
            source="test",
        )

    assert result["success"] is False
    assert result["executed"] is False
    assert "Sicherheitsreflexion" in result["error"]
    assert result["reflection"]["reason"] == "unit_block"
    mock_reflect.assert_called_once()
    mock_companion.execute.assert_not_called()


def test_execute_action_confirmation_still_required_after_reflection():
    with patch("backend.action_executor.is_command_allowed", return_value="confirmation_required"), \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        result = execute_action(
            {"action": "process_kill", "params": {"pid": 123}},
            source="test",
        )

    assert result["success"] is False
    assert result["executed"] is False
    assert result["requires_confirmation"] is True
    mock_companion.execute.assert_not_called()


def test_execute_action_high_risk_tool_triggers_reflection():
    with patch("backend.action_executor.is_command_allowed", return_value="confirmation_required"), \
         patch("backend.action_executor.reflect_action", return_value=None) as mock_reflect, \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        result = execute_action(
            {"action": "process_kill", "params": {"pid": 123}},
            source="test",
        )

    assert result["requires_confirmation"] is True
    mock_reflect.assert_called_once_with(
        "process_kill",
        {"pid": 123},
        permission="confirmation_required",
        source="test",
    )
    mock_companion.execute.assert_not_called()


def test_execute_action_validate_params_runs_after_positive_reflection():
    decision = ReflectionDecision(
        should_execute=True,
        risk_level="medium",
        confidence=0.8,
        concerns=["unit"],
        requires_confirmation=False,
        verification_step="verify",
        reason="unit_pass",
    )
    with patch("backend.action_executor.is_command_allowed", return_value="allowed"), \
         patch("backend.action_executor.reflect_action", return_value=decision) as mock_reflect, \
         patch("backend.action_executor.validate_params", side_effect=lambda command, params: {**params, "sanitized": True}) as mock_validate, \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log"):
        mock_companion.execute.return_value = {"success": True, "data": "ok"}
        result = execute_action(
            {"action": "clipboard_write", "params": {"text": "hello"}},
            source="test",
        )

    assert result["success"] is True
    mock_reflect.assert_called_once()
    mock_validate.assert_called_once_with("clipboard_write", {"text": "hello"})
    mock_companion.execute.assert_called_once_with("clipboard_write", {"text": "hello", "sanitized": True})


def test_execute_action_risk_budget_blocks_mutation_before_companion(monkeypatch):
    import backend.security as security

    monkeypatch.setitem(security._ACTION_RATE_LIMITS["execute"], "max", 5)
    security._ACTION_RATE_LIMITS["execute"]["entries"].append((time.time(), 5))

    with patch("backend.action_executor.is_command_allowed", return_value="allowed"), \
         patch("backend.action_executor.reflect_action", return_value=None), \
         patch("backend.action_executor.validate_params", side_effect=lambda command, params: params), \
         patch("backend.action_executor.companion") as mock_companion, \
         patch("backend.action_executor.audit_log") as mock_audit:
        result = execute_action(
            {"action": "file_delete", "params": {"path": "C:\\temp\\old.txt"}},
            source="test",
            confirmed=True,
        )

    assert result["success"] is False
    assert result["executed"] is False
    assert result["rate_limited"] is True
    mock_companion.execute.assert_not_called()
    mock_audit.assert_any_call("file_delete", "risk_rate_limited", "source=test used=5 limit=5")
