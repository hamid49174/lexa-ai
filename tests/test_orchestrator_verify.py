"""Tests fuer die Verifier-Schicht (Phase 48 B): LLM-as-Judge + adversarisch."""
import asyncio

from backend.orchestrator.core import _PLANNER_PERSONA, _SYNTH_PERSONA, run_orchestration
from backend.orchestrator.verify import (
    _JUDGE_PERSONA,
    _REFUTE_PERSONA,
    adversarial_judge,
    judge_result,
    verify_results,
)

_OK = {"agent_id": "a1", "role": "research", "objective": "X", "summary": "Solider Befund mit Quelle.", "status": "done"}


def test_judge_result_parses_verdict():
    def fake_chat(messages, system_extra, tools_override):
        assert system_extra == _JUDGE_PERSONA and tools_override == []
        return {"type": "text", "content": '{"score": 0.9, "passed": true, "reasons": ["belegt"]}'}

    v = asyncio.run(judge_result("Frage", _OK, chat_fn=fake_chat))
    assert v["passed"] is True and v["score"] == 0.9 and v["reasons"] == ["belegt"]


def test_judge_result_fallback_on_garbage():
    def fake_chat(messages, system_extra, tools_override):
        return {"type": "text", "content": "kein json"}

    v = asyncio.run(judge_result("Frage", _OK, chat_fn=fake_chat))
    assert v["passed"] is True and v["score"] == 0.5  # wohlwollend, blockiert nie


def test_judge_skips_failed_subagent_without_llm():
    called = {"n": 0}

    def fake_chat(messages, system_extra, tools_override):
        called["n"] += 1
        return {"type": "text", "content": "{}"}

    failed = {**_OK, "status": "failed"}
    v = asyncio.run(judge_result("Frage", failed, chat_fn=fake_chat))
    assert v["passed"] is False and v["score"] == 0.0 and called["n"] == 0


def test_adversarial_majority_refutes():
    def fake_chat(messages, system_extra, tools_override):
        return {"type": "text", "content": '{"refuted": true, "reason": "unbelegt"}'}

    adv = asyncio.run(adversarial_judge("Frage", _OK, chat_fn=fake_chat, rounds=2))
    assert adv["refuted"] is True and adv["refute_votes"] == 2


def test_verify_results_fast_mode_skips():
    out = asyncio.run(verify_results("Frage", [_OK], mode="fast", chat_fn=lambda *a: {"type": "text", "content": "{}"}))
    assert out == []


def test_verify_results_low_score_triggers_adversarial():
    def fake_chat(messages, system_extra, tools_override):
        if system_extra == _JUDGE_PERSONA:
            return {"type": "text", "content": '{"score": 0.2, "passed": false, "reasons": ["schwach"]}'}
        if system_extra == _REFUTE_PERSONA:
            return {"type": "text", "content": '{"refuted": true, "reason": "luecke"}'}
        return {"type": "text", "content": "{}"}

    out = asyncio.run(verify_results("Frage", [_OK], mode="thorough", chat_fn=fake_chat))
    assert len(out) == 1
    assert out[0]["passed"] is False
    assert out[0]["adversarial"] is not None and out[0]["adversarial"]["refuted"] is True


def _collect(agen):
    async def _run():
        return [ev async for ev in agen]

    return asyncio.run(_run())


def _full_fake_chat(messages, system_extra, tools_override):
    if system_extra == _PLANNER_PERSONA:
        return {"type": "text", "content": '[{"role":"research","objective":"Finde X"}]'}
    if system_extra == _SYNTH_PERSONA:
        return {"type": "text", "content": "FINALE ANTWORT."}
    if system_extra == _JUDGE_PERSONA:
        return {"type": "text", "content": '{"score": 0.95, "passed": true, "reasons": ["gut"]}'}
    if system_extra == _REFUTE_PERSONA:
        return {"type": "text", "content": '{"refuted": false, "reason": ""}'}
    # Sub-Agent: direkt Text (kein Tool noetig)
    return {"type": "text", "content": "Sub-Agent Befund."}


def test_thorough_mode_emits_verification_events():
    events = _collect(run_orchestration("Frage", mode="thorough", chat_fn=_full_fake_chat,
                                        execute_tool_fn=lambda *a: {"success": True, "data": "x"}))
    types = [e["type"] for e in events]
    assert "verification" in types
    done = events[-1]["run"]
    assert len(done["verdicts"]) == 1 and done["verdicts"][0]["passed"] is True


def test_fast_mode_has_no_verification():
    events = _collect(run_orchestration("Frage", mode="fast", chat_fn=_full_fake_chat,
                                        execute_tool_fn=lambda *a: {"success": True, "data": "x"}))
    types = [e["type"] for e in events]
    assert "verification" not in types
    assert events[-1]["run"]["verdicts"] == []
