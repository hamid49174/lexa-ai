"""Scan-Fix: offene Bestaetigung an die Konversation binden (kein Cross-Conversation-Leak)."""
from backend import shared


def _reset():
    shared.clear_pending_confirmation()
    shared.set_active_conversation_id(None)


def test_pending_confirmation_not_returned_for_other_conversation():
    _reset()
    try:
        shared.set_pending_confirmation({"action": "file_delete"}, conversation_id=1)
        # Gleiche Konversation -> wird zurueckgegeben
        assert shared.get_pending_confirmation(conversation_id=1) == {"action": "file_delete"}
        # Andere Konversation -> KEIN Leak
        assert shared.get_pending_confirmation(conversation_id=2) is None
    finally:
        _reset()


def test_pending_confirmation_follows_active_conversation_switch():
    _reset()
    try:
        shared.set_active_conversation_id(10)
        shared.set_pending_confirmation({"action": "x"})  # bindet an aktive Konversation 10
        shared.set_active_conversation_id(20)             # Nutzer wechselt zu 20
        assert shared.get_pending_confirmation() is None  # "ja" in 20 fuehrt 10 NICHT aus
        shared.set_active_conversation_id(10)
        assert shared.get_pending_confirmation() == {"action": "x"}
    finally:
        _reset()


def test_pending_confirmation_backward_compatible_with_unknown_ids():
    _reset()
    try:
        # Kein conv-Kontext beim Setzen (Legacy/ad-hoc) -> keine Filterung
        shared.set_pending_confirmation({"action": "z"})
        assert shared.get_pending_confirmation(conversation_id=5) == {"action": "z"}
    finally:
        _reset()
