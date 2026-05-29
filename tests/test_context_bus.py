from backend.context_bus import (
    clear_shared_context,
    get_shared_context_snapshot,
    publish_chat_context,
    suggest_personal_os_topic,
)
from backend.intent_engine import ConversationIntentContext


def setup_function():
    clear_shared_context()


def teardown_function():
    clear_shared_context()


def test_publish_chat_context_exposes_recent_intents_and_entities():
    context = ConversationIntentContext(
        recent_intents=["file_ops", "file_delete"],
        active_domain="file_ops",
        entities={"path": r"C:\Users\admin\Desktop\plan.txt"},
    )

    snapshot = publish_chat_context("Wir arbeiten am Projekt Alpha", intent_context=context, source="unit")

    assert snapshot["fresh"] is True
    assert snapshot["activeDomain"] == "file_ops"
    assert snapshot["recentIntents"] == ["file_ops", "file_delete"]
    assert snapshot["entities"]["path"].endswith("plan.txt")
    assert snapshot["topic"] == "Wir arbeiten am Projekt Alpha"
    assert suggest_personal_os_topic() == "Wir arbeiten am Projekt Alpha"


def test_context_bus_does_not_promote_action_or_secret_text_to_topic():
    publish_chat_context("Loesch die Datei C:\\temp\\secret.txt", source="unit")
    assert suggest_personal_os_topic("fallback") == "fallback"

    publish_chat_context("Mein API key ist sk-test-secret", source="unit")
    assert suggest_personal_os_topic("fallback") == "fallback"


def test_stale_context_is_not_suggested(monkeypatch):
    publish_chat_context("Projekt Beta Recherche", source="unit")

    import backend.context_bus as context_bus

    monkeypatch.setitem(context_bus._shared_context, "updatedAt", 1.0)
    snapshot = get_shared_context_snapshot(max_age_seconds=1)

    assert snapshot["fresh"] is False
    assert suggest_personal_os_topic("fallback") == "fallback"
