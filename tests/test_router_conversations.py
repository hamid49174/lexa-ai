"""Tests for backend/router_conversations.py conversation persistence endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import backend.memory as mem
    import backend.shared as shared
    from backend.router_conversations import router

    mem.close_db()
    monkeypatch.setattr(mem, "DB_PATH", tmp_path / "test_conversations.db")
    monkeypatch.setattr(mem, "_tables_ready", False)
    shared.conversation_history.clear()

    app = FastAPI()
    app.include_router(router)
    test_client = TestClient(app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        shared.conversation_history.clear()
        mem.close_db()


class TestConversationEndpoints:
    def test_markdown_answer_roundtrips_and_loads_active_history(self, client):
        import backend.shared as shared

        create = client.post("/conversations", json={"title": "Release persistence smoke"})
        assert create.status_code == 200
        conv_id = create.json()["id"]

        raw_answer = (
            "## Persisted Answer\n\n"
            "- Fact: Saved assistant answers keep raw Markdown.\n"
            "- Evidence: Backend roundtrip smoke.\n\n"
            "```js\nconst persisted = true;\n```"
        )
        messages = [
            {"role": "user", "content": "Save this answer for reload."},
            {
                "role": "assistant",
                "content": raw_answer,
                "meta": {"agent": "local-ui-only"},
            },
        ]

        update = client.put(f"/conversations/{conv_id}", json={"messages": messages})
        assert update.status_code == 200
        assert update.json()["status"] == "ok"

        loaded = client.get(f"/conversations/{conv_id}")
        assert loaded.status_code == 200
        data = loaded.json()
        assert data["status"] == "ok"
        assert data["message_count"] == 2
        assert data["messages"] == [
            {"role": "user", "content": "Save this answer for reload."},
            {"role": "assistant", "content": raw_answer},
        ]
        assert "meta" not in data["messages"][1]

        listed = client.get("/conversations")
        assert listed.status_code == 200
        row = listed.json()["conversations"][0]
        assert row["id"] == conv_id
        assert row["message_count"] == 2
        assert "messages" not in row
        assert "Persisted Answer" in row["last_message"]
        assert row["last_role"] == "assistant"

        load = client.post(f"/conversations/{conv_id}/load")
        assert load.status_code == 200
        assert load.json() == {"status": "loaded", "message_count": 2}
        assert shared.conversation_history[-1] == {"role": "assistant", "content": raw_answer}

    @pytest.mark.parametrize(
        "payload,detail",
        [
            ({"messages": "not-a-list"}, "messages must be a list"),
            ({"messages": ["bad"]}, "messages[0] must be an object"),
            ({"messages": [{"role": "tool", "content": "x"}]}, "messages[0].role is invalid"),
            ({"messages": [{"role": "assistant", "content": "   "}]}, "messages[0].content is required"),
        ],
    )
    def test_update_rejects_unrenderable_message_payloads(self, client, payload, detail):
        conv_id = client.post("/conversations", json={"title": "Invalid payload smoke"}).json()["id"]

        response = client.put(f"/conversations/{conv_id}", json=payload)

        assert response.status_code == 400
        assert response.json()["detail"] == detail
