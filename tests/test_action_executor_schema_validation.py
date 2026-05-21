from unittest.mock import patch

from backend.action_executor import execute_action


def test_execute_action_rejects_schema_invalid_args_before_companion():
    with patch("backend.action_executor.is_command_allowed", return_value="allowed") as mock_perm, \
         patch("backend.action_executor.companion") as mock_companion, \
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
