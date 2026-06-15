"""Tests fuer Agententypen code/planning + Browser-Erkennung (Phase 48 D)."""
import asyncio

from backend.orchestrator import browser_agent
from backend.orchestrator.roles import (
    ORCHESTRATOR_ROLES,
    is_role_tool_allowed,
    role_tool_defs,
)


def test_code_and_planning_roles_exist():
    assert "code" in ORCHESTRATOR_ROLES and "planning" in ORCHESTRATOR_ROLES
    assert ORCHESTRATOR_ROLES["code"]["label"] == "Code"
    assert ORCHESTRATOR_ROLES["planning"]["label"] == "Planung"


def test_code_role_tools_are_readonly_and_gated():
    names = [t["function"]["name"] for t in role_tool_defs("code")]
    assert "file_search" in names and "web_search" in names
    assert is_role_tool_allowed("code", "file_search") is True
    assert is_role_tool_allowed("code", "file_delete") is False  # nicht in Allowlist


def test_planning_role_reads_productivity():
    names = [t["function"]["name"] for t in role_tool_defs("planning")]
    assert "todo_list" in names and "habit_list" in names and "pomodoro_status" in names
    assert is_role_tool_allowed("planning", "todo_list") is True
    assert is_role_tool_allowed("planning", "todo_create") is False  # mutierend, nicht erlaubt


def test_browser_status_default_disabled(monkeypatch):
    monkeypatch.setattr(browser_agent, "ORCHESTRATOR_BROWSER_ENABLED", False)
    status = browser_agent.browser_status()
    assert status["available"] is False
    assert "deaktiviert" in status["reason"]


def test_run_browser_task_unavailable_is_graceful(monkeypatch):
    monkeypatch.setattr(browser_agent, "ORCHESTRATOR_BROWSER_ENABLED", False)
    res = asyncio.run(browser_agent.run_browser_task("oeffne example.com"))
    assert res["success"] is False and "nicht verfuegbar" in res["error"]


def test_planner_prompt_mentions_new_roles():
    from backend.orchestrator.core import _planner_user_prompt
    prompt = _planner_user_prompt("Aufgabe", 4)
    assert "'code'" in prompt and "'planning'" in prompt
