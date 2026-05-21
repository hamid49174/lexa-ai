from unittest.mock import patch

from backend.action_executor import execute_action
from backend.agent_reflection import ReflectionDecision


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
