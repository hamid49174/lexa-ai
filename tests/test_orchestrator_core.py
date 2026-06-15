"""Unit-Tests fuer den Orchestrator-Kern (Phase 48 A).

LLM und Tool-Ausfuehrung werden injiziert (deterministische Fakes) — kein Gemini noetig.
"""
import asyncio

import backend.orchestrator.core as core
from backend.orchestrator.core import (
    _PLANNER_PERSONA,
    _SYNTH_PERSONA,
    _extract_json,
    _parse_plan,
    plan_task,
    run_orchestration,
    synthesize_results,
)
from backend.orchestrator.roles import is_role_tool_allowed, normalize_role, role_tool_defs


# ── reine Helfer ─────────────────────────────────────────────────────────
def test_extract_json_handles_fences_and_noise():
    assert _extract_json('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert _extract_json('hier: [{"role":"research","objective":"x"}] ende') == [
        {"role": "research", "objective": "x"}
    ]
    assert _extract_json("kein json") is None


def test_parse_plan_normalizes_roles_and_caps():
    raw = (
        '[{"role":"research","objective":"A"},'
        '{"role":"unbekannt","objective":"B"},'
        '{"role":"knowledge","objective":""},'
        '{"objective":"C"}]'
    )
    plan = _parse_plan(raw, max_subagents=10)
    # leeres objective faellt raus; unbekannte Rolle -> general; fehlende Rolle -> Default (research)
    assert [p["role"] for p in plan] == ["research", "general", "research"]
    assert [p["objective"] for p in plan] == ["A", "B", "C"]
    # Cap greift
    capped = _parse_plan('[{"role":"research","objective":"A"},{"role":"research","objective":"B"}]', max_subagents=1)
    assert len(capped) == 1


def test_role_tool_defs_research_has_web_search():
    names = [t["function"]["name"] for t in role_tool_defs("research")]
    assert "web_search" in names
    assert is_role_tool_allowed("research", "web_search") is True
    # Schreib-/Fremd-Tool ist NICHT erlaubt
    assert is_role_tool_allowed("research", "file_delete") is False
    assert normalize_role("voelliger_unsinn") == "general"


# ── plan_task ────────────────────────────────────────────────────────────
def test_plan_task_parses_llm_plan():
    def fake_chat(messages, system_extra, tools_override):
        assert tools_override == []  # Planner laeuft ohne Tools
        return {"type": "text", "content": '[{"role":"research","objective":"Finde X"},{"role":"knowledge","objective":"Suche Y"}]'}

    plan = asyncio.run(plan_task("Vergleiche X und Y", chat_fn=fake_chat))
    assert [s["role"] for s in plan["subtasks"]] == ["research", "knowledge"]


def test_plan_task_falls_back_to_single_subtask_on_garbage():
    def fake_chat(messages, system_extra, tools_override):
        return {"type": "text", "content": "kein gueltiges json"}

    plan = asyncio.run(plan_task("Was ist die Hauptstadt von Frankreich?", chat_fn=fake_chat))
    assert len(plan["subtasks"]) == 1
    assert plan["subtasks"][0]["role"] == "research"


# ── End-to-End Orchestrierung ────────────────────────────────────────────
def _collect(agen):
    async def _run():
        out = []
        async for ev in agen:
            out.append(ev)
        return out

    return asyncio.run(_run())


def test_run_orchestration_end_to_end():
    calls = {"tools": [], "planner_tools": None, "synth_tools": None}

    def fake_chat(messages, system_extra, tools_override):
        names = [t["function"]["name"] for t in (tools_override or [])]
        if system_extra == _PLANNER_PERSONA:
            calls["planner_tools"] = names
            return {"type": "text", "content": '[{"role":"research","objective":"Finde X"},{"role":"knowledge","objective":"Suche Y"}]'}
        if system_extra == _SYNTH_PERSONA:
            calls["synth_tools"] = names
            return {"type": "text", "content": "FINALE ANTWORT aus beiden Agenten."}
        # Sub-Agent: erst ein Tool, dann Text
        has_result = any("[TOOL-ERGEBNIS" in str(m.get("content", "")) for m in messages)
        if has_result:
            return {"type": "text", "content": "Sub-Agent fertig."}
        tool = "web_search" if "RECHERCHE" in system_extra else "memory_search"
        return {"type": "tool_call", "tool_calls": [{"function": {"name": tool, "arguments": '{"query":"x"}'}}], "content": ""}

    def fake_exec(name, params):
        calls["tools"].append(name)
        return {"success": True, "data": f"daten von {name}"}

    events = _collect(run_orchestration("Vergleiche X und Y", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    types = [e["type"] for e in events]

    assert types[0] == "orchestrator_start"
    assert "plan" in types
    assert types.count("subagent_start") == 2
    assert types.count("subagent_done") == 2
    assert "subagent_step" in types
    assert types[-1] == "done"

    done = events[-1]["run"]
    assert done["subagent_count"] == 2
    assert done["answer"] == "FINALE ANTWORT aus beiden Agenten."
    assert done["partial"] is False
    # Planner + Synthese liefen ohne Tools, Sub-Agenten fuehrten ihre Read-Tools aus
    assert calls["planner_tools"] == [] and calls["synth_tools"] == []
    assert "web_search" in calls["tools"] and "memory_search" in calls["tools"]
    # agents nach index sortiert
    assert [a["agent_id"] for a in done["agents"]] == ["a1", "a2"]


def test_subagent_read_only_guard_blocks_mutating_tool():
    calls = {"tools": []}

    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _PLANNER_PERSONA:
            return {"type": "text", "content": '[{"role":"research","objective":"Finde X"}]'}
        if system_extra == _SYNTH_PERSONA:
            return {"type": "text", "content": "Finale Antwort."}
        has_result = any("nicht erlaubt" in str(m.get("content", "")) or "NICHT erlaubt" in str(m.get("content", "")) for m in messages)
        if has_result:
            return {"type": "text", "content": "Ok, nur Text."}
        # Versucht ein mutierendes Tool, das NICHT in der Allowlist ist
        return {"type": "tool_call", "tool_calls": [{"function": {"name": "file_delete", "arguments": "{}"}}], "content": ""}

    def fake_exec(name, params):
        calls["tools"].append(name)
        return {"success": True, "data": "sollte nie passieren"}

    events = _collect(run_orchestration("Test", chat_fn=fake_chat, execute_tool_fn=fake_exec))
    steps = [e for e in events if e["type"] == "subagent_step"]

    assert "file_delete" not in calls["tools"]  # Guard hat die Ausfuehrung verhindert
    assert any(s["step"]["status"] == "blocked" for s in steps)
    assert events[-1]["type"] == "done"


def test_synthesize_results_fallback_when_chat_fails():
    def boom(messages, system_extra, tools_override):
        raise RuntimeError("kein modell")

    out = asyncio.run(
        synthesize_results(
            "Frage",
            [{"agent_id": "a1", "role": "research", "objective": "X", "summary": "Befund A", "status": "done"}],
            chat_fn=boom,
        )
    )
    assert "Befund A" in out  # Fallback nutzt die Sub-Agent-Summaries


def test_empty_task_yields_error():
    events = _collect(run_orchestration("   ", chat_fn=lambda *a: {"type": "text", "content": "x"}))
    assert any(e["type"] == "error" for e in events)
