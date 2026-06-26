"""Regressionstests aus dem Orchestrator-Audit — Bereich E."""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.orchestrator.core as core
from backend import router_orchestrator


def _run_subagent(**kw):
    async def _emit(_ev):
        return None
    defaults = dict(
        agent_id="a1", role="research", objective="x", mode="thorough",
        emit=_emit, max_steps=10, step_timeout=None,
    )
    defaults.update(kw)
    agent_id = defaults.pop("agent_id")
    role = defaults.pop("role")
    objective = defaults.pop("objective")
    return asyncio.run(core._run_subagent(agent_id, role, objective, **defaults))


# ── HIGH 1: alle Tool-Calls eines Turns werden ausgefuehrt ──────────────────

def test_subagent_executes_all_tool_calls_in_one_turn():
    # Vorher wurde still nur tool_calls[0] ausgefuehrt -> Recherche-Tiefe degradierte.
    state = {"turn": 0, "execs": []}

    def fake_chat(messages, system_extra, tools_override):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"type": "tool_call", "tool_calls": [
                {"function": {"name": "git_status", "arguments": "{}"}},
                {"function": {"name": "git_status", "arguments": "{}"}},
            ], "content": ""}
        return {"type": "text", "content": "fertig"}

    def fake_exec(name, params):
        state["execs"].append(name)
        return {"success": True, "data": "ok"}

    res = _run_subagent(role="code", chat_fn=fake_chat, execute_tool_fn=fake_exec)
    assert len(state["execs"]) == 2          # BEIDE Calls ausgefuehrt (vorher nur 1)
    assert res["summary"] == "fertig"
    assert len(res["steps"]) == 2


def test_subagent_caps_tool_calls_per_turn():
    # Ein einzelner Turn darf nicht unbegrenzt Tools feuern.
    state = {"turn": 0, "execs": 0}

    def fake_chat(messages, system_extra, tools_override):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"type": "tool_call", "tool_calls": [
                {"function": {"name": "git_status", "arguments": "{}"}} for _ in range(9)
            ], "content": ""}
        return {"type": "text", "content": "ok"}

    def fake_exec(name, params):
        state["execs"] += 1
        return {"success": True, "data": "ok"}

    res = _run_subagent(role="code", chat_fn=fake_chat, execute_tool_fn=fake_exec)
    assert state["execs"] == core._MAX_TOOL_CALLS_PER_TURN   # auf das Limit gedeckelt
    assert res["summary"] == "ok"


# ── MED 4: run_orchestration respektiert max_subagents (Effort-Scaling) ──────

def _collect(agen):
    async def _run():
        return [ev async for ev in agen]
    return asyncio.run(_run())


def test_run_orchestration_respects_max_subagents():
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == core._PLANNER_PERSONA:
            return {"type": "text", "content": (
                '[{"role":"research","objective":"A"},{"role":"research","objective":"B"},'
                '{"role":"research","objective":"C"},{"role":"research","objective":"D"},'
                '{"role":"research","objective":"E"}]'
            )}
        return {"type": "text", "content": "sub fertig"}  # Sub-Agent ohne Tool -> sofort fertig

    def fake_exec(name, params):
        return {"success": True, "data": "ok"}

    events = _collect(core.run_orchestration(
        "breite Recherche", mode="fast", chat_fn=fake_chat, execute_tool_fn=fake_exec, max_subagents=2,
    ))
    types = [e["type"] for e in events]
    assert types.count("subagent_start") == 2          # trotz 5 geplanter Teilaufgaben auf 2 begrenzt
    assert events[-1]["run"]["subagent_count"] == 2


# ── MED 4 (Plumbing): Router reicht subagents durch und klemmt gegen den Cap ──

def test_router_forwards_and_clamps_subagents(monkeypatch):
    captured = {}

    def fake_run(task, *, mode="thorough", max_subagents=None):
        captured["max_subagents"] = max_subagents

        async def gen():
            yield {"type": "done", "run_id": "r1", "run": {
                "run_id": "r1", "mode": mode, "goal": task, "answer": "A",
                "subagent_count": 1, "agents": [], "verdicts": [], "partial": False, "elapsed_seconds": 0.1,
            }}
        return gen()

    monkeypatch.setattr(router_orchestrator, "run_orchestration", fake_run)
    monkeypatch.setattr(router_orchestrator.store, "save_run", lambda record: True)
    monkeypatch.setattr(router_orchestrator, "check_rate_limit", lambda _b: True)
    monkeypatch.setattr(router_orchestrator, "ORCHESTRATOR_ENABLED", True)

    app = FastAPI()
    app.include_router(router_orchestrator.router)
    client = TestClient(app)

    # zu grosser Wert wird gegen den Cap geklemmt statt mit 422 abgelehnt
    resp = client.post("/orchestrator/run", json={"task": "breite Recherche", "subagents": 99})
    assert resp.status_code == 200
    assert captured["max_subagents"] == router_orchestrator.ORCHESTRATOR_MAX_SUBAGENTS

    # ohne Feld bleibt es beim Default (None -> globaler Cap im Lauf)
    resp2 = client.post("/orchestrator/run", json={"task": "breite Recherche"})
    assert resp2.status_code == 200
    assert captured["max_subagents"] is None

    # 0/negativ darf den Lauf NICHT mit 422 verwerfen, sondern faellt auf Default zurueck
    for bad in (0, -3):
        captured["max_subagents"] = "SENTINEL"
        r = client.post("/orchestrator/run", json={"task": "breite Recherche", "subagents": bad})
        assert r.status_code == 200, f"subagents={bad} sollte 200 sein, war {r.status_code}"
        assert captured["max_subagents"] is None

    # gueltiger Wuschwert wird unveraendert (innerhalb Cap) durchgereicht
    captured["max_subagents"] = "SENTINEL"
    r = client.post("/orchestrator/run", json={"task": "breite Recherche", "subagents": 2})
    assert r.status_code == 200
    assert captured["max_subagents"] == 2
