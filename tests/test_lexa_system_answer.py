import asyncio

from backend import lexa_system_answer as answer


def test_lexa_system_answer_detects_os_hermes_opinion_questions():
    assert answer.looks_like_lexa_system_question("wie findest du mein os und hermes")
    assert answer.looks_like_lexa_system_question("was bringt das spaeter fuer Lexa wenn ich die app veroeffentliche")
    assert answer.looks_like_lexa_system_question("was h\u00e4ltst du sp\u00e4ter von Lexa wenn ich sie ver\u00f6ffentliche")
    assert not answer.looks_like_lexa_system_question("wie findest du kuenstliche intelligenz")


def test_lexa_system_answer_does_not_steal_memory_or_planning_prompts():
    assert not answer.looks_like_lexa_system_question(
        "Merke dir fuer diesen Chat: Mein Hauptziel ist, Lexa stabil und hochwertig zu machen."
    )
    assert not answer.looks_like_lexa_system_question(
        "Mach aus dieser chaotischen Idee einen klaren Plan: Lexa besser machen, Bugs finden, "
        "morgen testen, spaeter Website, keine halben Sachen."
    )


def test_lexa_system_answer_uses_live_status_shape(monkeypatch):
    monkeypatch.setattr(answer, "get_hermes_status", lambda: {
        "health_state": "ready",
        "gateway": {"configured": True},
        "obsidian_context": {"ok": True},
    })
    monkeypatch.setattr(answer, "get_hermes_gateway_autostart_status", lambda: {"enabled": True})
    monkeypatch.setattr(answer, "get_hermes_gateway_log_summary", lambda lines: {
        "status": "ok",
        "health_state": "ok",
        "summary": "Keine Fehler im Testfenster.",
    })

    async def fake_drafts():
        return {"pending": 0, "approved": 11, "rejected": 3}

    monkeypatch.setattr(answer, "_draft_counts", fake_drafts)

    result = asyncio.run(answer.try_lexa_system_answer("wie findest du mein os und hermes"))

    assert result is not None
    assert "Architektur ist stark" in result
    assert "Drafts 0 pending, 11 approved, 3 rejected" in result
    assert "Naechster sichtbarer Schritt" in result
