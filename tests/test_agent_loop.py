"""
Tests for backend/agent_loop.py — Phase 46: Multi-Step Agent Engine.
Tests: data models, tool execution, result formatting, agent configuration.

Run with: python -m pytest tests/test_agent_loop.py -v
"""
import asyncio
import json
import time
import unittest
from unittest.mock import patch, MagicMock

from backend.agent_loop import (
    AgentStep, AgentRun, StepStatus,
    _execute_tool, _format_tool_result,
)
from backend.config import AGENT_MAX_STEPS


def _run(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════
#  DATA MODELS
# ══════════════════════════════════════════════════

class TestDataModels(unittest.TestCase):

    def test_step_default_values(self):
        step = AgentStep(index=0)
        self.assertEqual(step.action, "")
        self.assertEqual(step.status, StepStatus.PENDING)
        self.assertIsNone(step.result)
        self.assertIsNone(step.error)

    def test_step_to_dict(self):
        step = AgentStep(index=1, action="system_info", status=StepStatus.SUCCESS)
        d = step.to_dict()
        self.assertEqual(d["index"], 1)
        self.assertEqual(d["action"], "system_info")
        self.assertEqual(d["status"], "success")

    def test_run_default_values(self):
        run = AgentRun()
        self.assertEqual(run.status, "running")
        self.assertEqual(run.steps, [])
        self.assertTrue(len(run.id) == 12)

    def test_run_to_dict(self):
        run = AgentRun(user_message="test message")
        step = AgentStep(index=0, action="test", status=StepStatus.SUCCESS)
        run.steps.append(step)
        d = run.to_dict()
        self.assertEqual(d["user_message"], "test message")
        self.assertEqual(len(d["steps"]), 1)
        self.assertEqual(d["steps"][0]["action"], "test")


# ══════════════════════════════════════════════════
#  TOOL EXECUTION
# ══════════════════════════════════════════════════

class TestToolExecution(unittest.TestCase):

    @patch("backend.agent_loop.is_command_allowed", return_value="blocked")
    def test_blocked_command(self, mock_perm):
        result = _run(_execute_tool("format_disk", {}))
        self.assertFalse(result["success"])
        self.assertIn("blockiert", result["error"])

    @patch("backend.agent_loop.is_command_allowed", return_value="confirmation_required")
    def test_confirmation_required(self, mock_perm):
        result = _run(_execute_tool("shutdown", {}))
        self.assertFalse(result["success"])
        self.assertTrue(result.get("needs_confirmation"))

    @patch("backend.agent_loop.is_command_allowed", return_value="unknown")
    def test_unknown_command(self, mock_perm):
        result = _run(_execute_tool("nonexistent_cmd", {}))
        self.assertFalse(result["success"])
        self.assertIn("Unbekannt", result["error"])

    def test_invalid_action_name(self):
        result = _run(_execute_tool("INVALID-NAME!", {}))
        self.assertFalse(result["success"])
        self.assertIn("Ungueltig", result["error"])

    @patch("backend.agent_loop.is_command_allowed", return_value="allowed")
    @patch("backend.agent_loop.validate_params", return_value={})
    @patch("companion.engine.companion")
    def test_successful_execution(self, mock_companion, mock_validate, mock_perm):
        mock_companion.execute.return_value = {"success": True, "data": "OK"}
        result = _run(_execute_tool("system_info", {}))
        self.assertTrue(result["success"])
        self.assertEqual(result["data"], "OK")

    @patch("backend.agent_loop.is_command_allowed", return_value="allowed")
    @patch("backend.agent_loop.validate_params", return_value={"filepath": "OS_MANIFEST.md"})
    def test_personal_os_execution_routes_to_async_bridge(self, mock_validate, mock_perm):
        async def fake_execute(command, params):
            return {"success": True, "data": f"{command}:{params['filepath']}"}

        with patch("backend.personal_os_actions.execute_personal_os_action", fake_execute):
            result = _run(_execute_tool("personal_os_read_file", {"filepath": "OS_MANIFEST.md"}))

        self.assertTrue(result["success"])
        self.assertEqual(result["data"], "personal_os_read_file:OS_MANIFEST.md")


# ══════════════════════════════════════════════════
#  RESULT FORMATTING
# ══════════════════════════════════════════════════

class TestResultFormatting(unittest.TestCase):

    def test_format_success_string(self):
        result = {"success": True, "data": "Notepad geoeffnet"}
        formatted = _format_tool_result("app_open", result)
        self.assertIn("[app_open]", formatted)
        self.assertIn("Erfolgreich", formatted)
        self.assertIn("Notepad", formatted)

    def test_format_success_dict(self):
        result = {"success": True, "data": {"cpu": 45, "ram": 62}}
        formatted = _format_tool_result("system_info", result)
        self.assertIn("Erfolgreich", formatted)

    def test_format_success_list(self):
        result = {"success": True, "data": [{"name": "file1"}, {"name": "file2"}]}
        formatted = _format_tool_result("file_search", result)
        self.assertIn("Erfolgreich", formatted)

    def test_format_failure(self):
        result = {"success": False, "error": "Datei nicht gefunden"}
        formatted = _format_tool_result("file_search", result)
        self.assertIn("Fehlgeschlagen", formatted)
        self.assertIn("Datei nicht gefunden", formatted)

    def test_format_truncation(self):
        result = {"success": True, "data": "x" * 2000}
        formatted = _format_tool_result("test", result)
        self.assertIn("...", formatted)
        self.assertTrue(len(formatted) < 2000)


# ══════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════

class TestConfiguration(unittest.TestCase):

    def test_max_steps(self):
        self.assertEqual(AGENT_MAX_STEPS, 10)

    def test_step_status_values(self):
        self.assertEqual(StepStatus.PENDING.value, "pending")
        self.assertEqual(StepStatus.SUCCESS.value, "success")
        self.assertEqual(StepStatus.NEEDS_CONFIRMATION.value, "needs_confirmation")


if __name__ == "__main__":
    unittest.main()
