import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_chat


DEGREE = chr(176)
COMPLEX_DAY_PLAN = (
    f"Ich plane morgen einen Arbeitstag in Hamburg. Das Wetter ist ungefaehr 15{DEGREE}C, klar, "
    "hohe Luftfeuchtigkeit und leichter Wind. Ich muss von 9 bis 17 Uhr arbeiten, "
    "habe 3 wichtige Aufgaben: Rechnung schreiben, Projekt planen, Wohnung aufraeumen. "
    "Ausserdem will ich 45 Minuten Sport machen und abends nicht zu spaet schlafen. "
    "Mach mir einen realistischen Tagesplan mit Uhrzeiten. Beruecksichtige das Wetter bei Kleidung "
    "und Weg nach draussen. Rechne aus, wie viel freie Zeit ungefaehr bleibt. "
    "Sag mir ausserdem, was ich weglassen sollte, falls ich muede bin."
)


def _client_with_weather_history(monkeypatch):
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    degree = chr(176)
    monkeypatch.setattr(router_chat, "conversation_history", [
        {"role": "user", "content": "wie ist wetter in hamburg"},
        {
            "role": "assistant",
            "content": f"Hamburg: 14.9{degree}C, Klar. Gefuehlt 14.9{degree}C. Luftfeuchtigkeit 87%, Wind 6.5 km/h.",
        },
    ])
    return TestClient(app)


def _client_with_day_plan_history(monkeypatch):
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    ctx = router_chat._day_plan_context_from_text(COMPLEX_DAY_PLAN)
    monkeypatch.setattr(router_chat, "conversation_history", [
        {"role": "user", "content": COMPLEX_DAY_PLAN},
        {"role": "assistant", "content": router_chat._day_plan_full_reply(ctx)},
    ])
    return TestClient(app)


def _client_with_math_history(monkeypatch):
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [
        {"role": "user", "content": "was sind 60% von 5000"},
        {"role": "assistant", "content": "60 % von 5000 = 3000."},
    ])
    return TestClient(app)


def test_weather_clothing_followup_uses_latest_weather_context(monkeypatch):
    client = _client_with_weather_history(monkeypatch)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("weather clothing follow-up should not call provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = client.post("/chat", json={"message": "WAS kann man dazu anziehen"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] is None
    assert payload["requires_confirmation"] is False
    assert "Hamburg" in payload["reply"]
    assert "14.9" in payload["reply"]
    assert "leichte Jacke" in payload["reply"]
    assert "Luftfeuchtigkeit" in payload["reply"] or "kuehler" in payload["reply"]
    assert router_chat.conversation_history[-1]["content"] == payload["reply"]


def test_weather_clothing_typo_uses_weather_context_after_other_topics(monkeypatch):
    client = _client_with_weather_history(monkeypatch)
    router_chat.conversation_history.extend([
        {"role": "user", "content": "was sind 60% von 5000"},
        {"role": "assistant", "content": "60 % von 5000 = 3000."},
        {"role": "user", "content": "und 19% davon?"},
        {"role": "assistant", "content": "19 % von 3000 = 570."},
    ])

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("clothing follow-up should use weather context")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = client.post("/chat", json={"message": "was kann ich anziehn"})

    assert response.status_code == 200
    payload = response.json()
    assert "Hamburg" in payload["reply"]
    assert "leichte Jacke" in payload["reply"]
    assert "Geld" not in payload["reply"]


def test_weather_correction_after_clothing_question_uses_weather_context(monkeypatch):
    client = _client_with_weather_history(monkeypatch)
    router_chat.conversation_history.extend([
        {"role": "user", "content": "was kann ich anziehn"},
        {"role": "assistant", "content": "Bei 19 % von 3000 EUR ist das irrelevant."},
    ])

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("weather correction should not call provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = client.post("/chat", json={"message": "bei wetter"})

    assert response.status_code == 200
    assert "Hamburg" in response.json()["reply"]
    assert "leichte Jacke" in response.json()["reply"]


def test_weather_clothing_followup_streams_without_tool_fallback(monkeypatch):
    client = _client_with_weather_history(monkeypatch)

    def fail_stream(*_args, **_kwargs):
        raise AssertionError("weather clothing follow-up should not create provider stream")

    monkeypatch.setattr(router_chat, "chat_stream", fail_stream)

    response = client.post("/chat/stream", json={"message": "was soll ich dazu anziehen?"})

    assert response.status_code == 200
    body = response.text
    assert "Hamburg" in body
    assert "leichte Jacke" in body
    assert '"action": null' in body
    assert "Ich bin da. Sag mir kurz" not in body


def test_complex_day_plan_is_answered_with_consistent_planning(monkeypatch):
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [])

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("deterministic day plan should not call provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)
    client = TestClient(app)

    response = client.post("/chat", json={"message": COMPLEX_DAY_PLAN})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "Projekt planen (zuerst" in reply
    assert "Freie Zeit/Puffer" in reply
    assert "Wenn du muede bist" in reply
    assert "Essen und Schlaf bleiben drin" in reply
    assert "13 Stunden 30" not in reply
    assert "Abendessen weg" not in reply


def test_day_plan_shorter_followup_preserves_constraints(monkeypatch):
    client = _client_with_day_plan_history(monkeypatch)
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no provider")))

    response = client.post("/chat", json={"message": "mach ihn kuerzer"})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "09:00-17:00" in reply
    assert "Puffer/Freizeit" in reply
    assert "nicht Essen oder Schlaf" in reply


def test_day_plan_late_start_followup_shifts_work_window(monkeypatch):
    client = _client_with_day_plan_history(monkeypatch)
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no provider")))

    response = client.post("/chat", json={"message": "und wenn ich erst um 10 starte?"})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "10:00-18:00" in reply
    assert "Projekt planen zuerst" in reply
    assert "Schlaf nicht" in reply


def test_day_plan_todo_followup_does_not_invent_tasks(monkeypatch):
    client = _client_with_day_plan_history(monkeypatch)
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no provider")))

    response = client.post("/chat", json={"message": "mach daraus eine todo liste"})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "Projekt planen" in reply
    assert "Rechnung schreiben" in reply
    assert "Wohnung aufraeumen" in reply
    assert "Toilette" not in reply
    assert "Handtuch" not in reply


def test_day_plan_clothing_followup_understands_zieh(monkeypatch):
    client = _client_with_day_plan_history(monkeypatch)
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no provider")))

    response = client.post("/chat", json={"message": "was zieh ich dazu an?"})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "15" in reply
    assert "Hoodie oder leichte Jacke" in reply
    assert "Sport" in reply


def test_day_plan_priority_followup_targets_real_tasks(monkeypatch):
    client = _client_with_day_plan_history(monkeypatch)
    monkeypatch.setattr(router_chat, "chat", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no provider")))

    response = client.post("/chat", json={"message": "welche aufgabe zuerst und warum?"})

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert reply.startswith("Zuerst Projekt planen")
    assert "Aufstehen" not in reply
    assert "Rechnung schreiben" in reply


def test_percent_of_previous_result_is_contextual(monkeypatch):
    client = _client_with_math_history(monkeypatch)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("percent follow-up should not call provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = client.post("/chat", json={"message": "und 19% davon?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "19 % von 3000 = 570."
    assert payload["action"] is None


def test_net_gross_followup_uses_previous_percent_context(monkeypatch):
    client = _client_with_math_history(monkeypatch)
    router_chat.conversation_history.extend([
        {"role": "user", "content": "und 19% davon?"},
        {"role": "assistant", "content": "19 % von 3000 = 570."},
    ])

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("net/gross follow-up should not call provider")

    monkeypatch.setattr(router_chat, "chat", fail_chat)

    response = client.post("/chat", json={"message": "mach daraus netto und brutto"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"] == "Wenn die 570 EUR die 19 % MwSt sind: Netto 3000 EUR, MwSt 570 EUR, Brutto 3570 EUR."


def test_chat_endpoint_reuses_cached_context_free_text_answer(monkeypatch):
    from backend.response_cache import clear_response_cache

    clear_response_cache()
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [])
    calls = {"count": 0}

    def fake_chat(*_args, **_kwargs):
        calls["count"] += 1
        return {"type": "text", "content": "Der Mond entfernt sich langsam von der Erde."}

    monkeypatch.setattr(router_chat, "chat", fake_chat)
    client = TestClient(app)

    first = client.post("/chat", json={"message": "Erzaehl mir einen kurzen Fakt ueber den Mond."})
    second = client.post("/chat", json={"message": "Erzaehl mir einen kurzen Fakt ueber den Mond bitte."})

    clear_response_cache()
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1
    assert second.json()["reply"] == "Der Mond entfernt sich langsam von der Erde."


def test_chat_endpoint_does_not_cache_tool_calls(monkeypatch):
    from backend.response_cache import clear_response_cache

    clear_response_cache()
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [])
    calls = {"count": 0}

    def fake_chat(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "type": "tool_call",
            "content": "",
            "tool_calls": [{"id": "1", "name": "system_info", "arguments": {}}],
        }

    monkeypatch.setattr(router_chat, "chat", fake_chat)
    client = TestClient(app)

    first = client.post("/chat", json={"message": "Pruefe bitte den Systemstatus."})
    second = client.post("/chat", json={"message": "Pruefe bitte den Systemstatus."})

    clear_response_cache()
    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 2


def test_desktop_click_typo_routes_to_hermes_worker():
    assert router_chat._is_hermes_desktop_control_request("kilcke auf mikro")
    assert router_chat._is_hermes_desktop_control_request("klcike auf mikro")
    assert router_chat._is_hermes_desktop_control_request("klicke auf Bearbeiten")


def test_confirmed_ui_click_reply_clips_multiline_target():
    reply = router_chat._format_confirmed_action_reply(
        "ui_click",
        {
            "success": True,
            "data": {
                "matched_text": "Play\n[App] Data directory: C:\\Users\\admin\\AppData\\Roaming\\lexa-ai " * 3,
                "x": 10,
                "y": 20,
            },
        },
    )

    assert "\n" not in reply
    assert len(reply) < 150
    assert "X=10, Y=20" in reply


def test_stream_confirmation_executes_pending_action_server_side(monkeypatch):
    from backend.shared import clear_pending_confirmation, set_pending_confirmation

    clear_pending_confirmation()
    app = FastAPI()
    app.include_router(router_chat.router)
    monkeypatch.setattr(router_chat, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_chat, "audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(router_chat, "conversation_history", [])
    seen = {}

    def fake_execute_action(action, source="unknown", confirmed=False):
        seen.update({"action": action, "source": source, "confirmed": confirmed})
        return {
            "success": True,
            "data": {"matched_text": "Mikrofon", "x": -1150, "y": 20},
        }

    monkeypatch.setattr("backend.action_executor.execute_action", fake_execute_action)
    set_pending_confirmation({"action": "desktop_click_text", "params": {"text": "Mikrofon"}})
    client = TestClient(app)

    response = client.post("/chat/stream", json={"message": "ja"})

    try:
        assert response.status_code == 200
        assert "Mikrofon" in response.text
        assert '"action": null' in response.text
        assert seen == {
            "action": {"action": "desktop_click_text", "params": {"text": "Mikrofon"}},
            "source": "chat_stream_confirm",
            "confirmed": True,
        }
    finally:
        clear_pending_confirmation()


def test_inline_confirmation_executes_pending_ui_action(monkeypatch):
    from backend.shared import clear_pending_confirmation, set_pending_confirmation

    clear_pending_confirmation()
    seen = {}

    def fake_execute_action(action, source="unknown", confirmed=False):
        seen.update({"action": action, "source": source, "confirmed": confirmed})
        return {
            "success": True,
            "data": {"matched_text": "Pause", "x": 450, "y": 120},
        }

    monkeypatch.setattr("backend.action_executor.execute_action", fake_execute_action)
    set_pending_confirmation({"action": "ui_click", "params": {"text": "darauf"}})

    try:
        reply = asyncio.run(router_chat._maybe_execute_inline_confirmation(
            "klick darauf ich bestaetige es",
            "Bestaetigung noetig fuer ui_click",
            "chat_stream_inline_confirm",
        ))

        assert "Pause" in reply
        assert "X=450, Y=120" in reply
        assert seen == {
            "action": {"action": "ui_click", "params": {"text": "darauf"}},
            "source": "chat_stream_inline_confirm",
            "confirmed": True,
        }
    finally:
        clear_pending_confirmation()
