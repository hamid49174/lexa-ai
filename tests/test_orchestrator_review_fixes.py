"""Regressionstests fuer die Self-Review-Fixes (Phase 48 H)."""
import asyncio

import backend.orchestrator.core as core
from backend.orchestrator.core import _PLANNER_PERSONA, _SYNTH_PERSONA, run_orchestration


def _collect(agen):
    async def _run():
        return [ev async for ev in agen]
    return asyncio.run(_run())


# ── web_search-Executor (Kern-Fix: research-Agent kann das Web wieder nutzen) ──
def test_web_search_executor_uses_gather_sources(monkeypatch):
    import backend.web_research as wr
    monkeypatch.setattr(wr, "gather_sources", lambda q, n=4: [{"title": "T", "url": "https://x", "snippet": "s"}])
    res = asyncio.run(core._default_execute_tool_fn("web_search", {"query": "wer ist x"}))
    assert res["success"] is True
    assert res["data"]["sources"][0]["url"] == "https://x"


def test_web_search_executor_empty_and_missing_query(monkeypatch):
    import backend.web_research as wr
    monkeypatch.setattr(wr, "gather_sources", lambda q, n=4: [])
    empty = asyncio.run(core._default_execute_tool_fn("web_search", {"query": "x"}))
    assert empty["success"] is True and empty["data"]["sources"] == []
    missing = asyncio.run(core._default_execute_tool_fn("web_search", {}))
    assert missing["success"] is False


# ── Tier-Gate (read-only Haerte) ──
def test_role_tool_tier_rejects_confirmation_required(monkeypatch):
    import backend.security as sec
    monkeypatch.setattr(sec, "is_command_allowed", lambda n: "confirmation_required" if n == "web_search" else "allowed")
    from backend.orchestrator.roles import is_role_tool_allowed, role_tool_defs
    assert is_role_tool_allowed("research", "web_search") is False
    assert "web_search" not in [t["function"]["name"] for t in role_tool_defs("research")]


# ── tool_calls als Nicht-Liste crasht den Sub-Agenten nicht ──
def test_subagent_handles_non_list_tool_calls():
    calls = {"tools": []}

    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"research","objective":"X"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "OK"}
        if any("[TOOL-ERGEBNIS" in str(m.get("content", "")) for m in messages):
            return {"type": "text", "content": "fertig"}
        # tool_calls als DICT statt Liste (abweichende Provider-Form)
        return {"type": "tool_call", "tool_calls": {"function": {"name": "web_search", "arguments": "{}"}}}

    def fake_exec(name, params):
        calls["tools"].append(name)
        return {"success": True, "data": "ok"}

    events = _collect(run_orchestration("t", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    assert events[-1]["type"] == "done"
    assert "web_search" in calls["tools"]  # Dict wurde zu [dict] coerced + ausgefuehrt


# ── Timeout: fehlende Sub-Agenten werden aufgefuellt, Deadline gilt fuer Synthese ──
def test_run_timeout_backfills_missing_subagents():
    async def slow_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"research","objective":"X"},{"role":"knowledge","objective":"Y"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "OK"}
        await asyncio.sleep(0.6)  # laenger als run_timeout -> Lauf laeuft in den Timeout
        return {"type": "text", "content": "spaet"}

    events = _collect(run_orchestration(
        "t", mode="fast", chat_fn=slow_chat,
        execute_tool_fn=lambda *a: {"success": True, "data": "x"},
        run_timeout=0.15, step_timeout=5, max_concurrency=2,
    ))
    done = events[-1]["run"]
    assert done["partial"] is True
    assert done["subagent_count"] == 2  # beide Subtasks aufgefuellt
    assert any(a["status"] == "timeout" for a in done["agents"])
    # Synthese lief trotz Budget-0 (Fallback) und lieferte eine Antwort.
    assert isinstance(done["answer"], str) and done["answer"]
