"""Tests fuer Agententypen code/planning + Browser-Erkennung (Phase 48 D)."""
import asyncio

from backend.orchestrator import browser_agent
from backend.orchestrator.roles import (
    ORCHESTRATOR_ROLES,
    is_role_tool_allowed,
    role_loop_spec,
    role_tool_defs,
)


def test_code_and_planning_roles_exist():
    assert "code" in ORCHESTRATOR_ROLES and "planning" in ORCHESTRATOR_ROLES
    assert ORCHESTRATOR_ROLES["code"]["label"] == "Code"
    assert ORCHESTRATOR_ROLES["planning"]["label"] == "Planung"


def test_code_role_tools_are_readonly_and_gated():
    names = [t["function"]["name"] for t in role_tool_defs("code")]
    assert "file_search" in names and "web_search" in names
    # Echte lokale Code-Analyse: git-Lesetools (always_allowed), KEIN MCP noetig.
    assert {"git_status", "git_log", "git_diff", "git_branch_list"}.issubset(set(names))
    assert is_role_tool_allowed("code", "git_status") is True
    assert is_role_tool_allowed("code", "file_search") is True
    assert is_role_tool_allowed("code", "file_delete") is False  # nicht in Allowlist


def test_planning_role_reads_productivity():
    names = [t["function"]["name"] for t in role_tool_defs("planning")]
    assert "todo_list" in names and "habit_list" in names and "pomodoro_status" in names
    # Voller "zweites Gehirn"-Lesezugriff: Zeiten, Erinnerungen, Routinen, Termine.
    assert {"time_tracking_report", "reminder_list", "routine_list", "calendar_today"}.issubset(set(names))
    assert is_role_tool_allowed("planning", "calendar_today") is True
    assert is_role_tool_allowed("planning", "todo_list") is True
    assert is_role_tool_allowed("planning", "todo_create") is False  # mutierend, nicht erlaubt
    assert is_role_tool_allowed("planning", "calendar_create") is False  # mutierend


def test_research_role_can_deep_read_and_knowledge_uses_graph():
    rnames = [t["function"]["name"] for t in role_tool_defs("research")]
    assert "web_search" in rnames and "web_scrape" in rnames
    knames = [t["function"]["name"] for t in role_tool_defs("knowledge")]
    assert "personal_os_graph" in knames and "personal_os_query" in knames


def test_role_loop_spec_per_role():
    for role in ("research", "knowledge", "code", "planning", "general"):
        spec = role_loop_spec(role)
        assert isinstance(spec.get("max_steps"), int) and spec["max_steps"] >= 1
        assert isinstance(spec.get("hint"), str) and spec["hint"]
    # rollenspezifische Hints unterscheiden sich
    assert role_loop_spec("research")["hint"] != role_loop_spec("code")["hint"]
    # unbekannte Rolle -> general-Fallback
    assert role_loop_spec("quatsch")["hint"] == role_loop_spec("general")["hint"]


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


def test_subagent_applies_loop_spec_hint_and_step_cap():
    """Der Rollen-Hint landet in der Persona und der Rollen-Cap begrenzt die Schritte."""
    import backend.orchestrator.core as core

    seen = {"personas": [], "tool_calls": 0}

    def fake_chat(messages, system_extra, tools_override):
        seen["personas"].append(system_extra)
        # nie abschliessen -> Schleife laeuft bis zum (Rollen-)Cap
        return {"type": "tool_call", "tool_calls": [{"function": {"name": "git_status", "arguments": "{}"}}], "content": ""}

    def fake_exec(name, params):
        seen["tool_calls"] += 1
        return {"success": True, "data": "ok"}

    async def _emit(_ev):
        return None

    res = asyncio.run(core._run_subagent(
        "a1", "code", "Analysiere das Repo",
        mode="thorough", chat_fn=fake_chat, execute_tool_fn=fake_exec,
        emit=_emit, max_steps=20, step_timeout=None,
    ))
    # Rollen-Cap (code=6) begrenzt, obwohl global 20 erlaubt waeren.
    assert seen["tool_calls"] == 6
    assert res["status"] == "incomplete"
    # Vorgehens-Hint der code-Rolle ist in der Persona enthalten.
    assert any("VORGEHEN:" in p and "git_status" in p for p in seen["personas"])
