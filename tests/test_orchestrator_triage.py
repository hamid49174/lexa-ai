"""Tests fuer die LLM-Triage (Phase 49 #2): Modell entscheidet ueber Multi-Agent."""
import asyncio

from backend.config import ORCHESTRATOR_MAX_SUBAGENTS
from backend.orchestrator import triage as tr


def test_triage_needs_agents_true():
    def fake_chat(messages, system_extra, tools_override):
        assert tools_override == []  # Triage laeuft ohne Tools (billig)
        return {"type": "text", "content": '{"needs_agents": true, "subagents": 4, "mode": "thorough", "reason": "Vergleich"}'}

    d = asyncio.run(tr.triage_task("Vergleiche A und B ausfuehrlich", chat_fn=fake_chat))
    assert d["needs_agents"] is True and d["subagents"] == 4 and d["mode"] == "thorough" and d["source"] == "llm"


def test_triage_needs_agents_false():
    def fake_chat(*a):
        return {"type": "text", "content": '{"needs_agents": false, "subagents": 1, "mode": "fast"}'}

    d = asyncio.run(tr.triage_task("wie geht es dir heute", chat_fn=fake_chat))
    assert d["needs_agents"] is False


def test_triage_caps_subagents():
    def fake_chat(*a):
        return {"type": "text", "content": '{"needs_agents": true, "subagents": 99, "mode": "fast"}'}

    d = asyncio.run(tr.triage_task("x" * 40, chat_fn=fake_chat))
    assert 1 <= d["subagents"] <= ORCHESTRATOR_MAX_SUBAGENTS


def test_triage_fallback_on_garbage():
    def fake_chat(*a):
        return {"type": "text", "content": "kein json hier"}

    d = asyncio.run(tr.triage_task("x" * 40, chat_fn=fake_chat))
    assert d["needs_agents"] is False and d["source"] == "fallback"


def test_triage_fallback_on_error():
    def boom(*a):
        raise RuntimeError("modell weg")

    d = asyncio.run(tr.triage_task("x" * 40, chat_fn=boom))
    assert d["needs_agents"] is False and d["source"] == "fallback"


def test_triage_empty_task():
    d = asyncio.run(tr.triage_task("   "))
    assert d["needs_agents"] is False and d["source"] == "fallback"
