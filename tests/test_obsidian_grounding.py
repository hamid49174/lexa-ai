"""Coverage for Obsidian/Personal-OS auto-grounding in chat.

Verifies the conservative trigger heuristic (_obsidian_context_query) and the
grounding-block builder (_build_obsidian_grounding) with a mocked vault payload.
"""
import backend.router_chat as rc


def test_trigger_fires_on_explicit_vault_and_personal_questions():
    for msg in [
        "Was steht in meinem Obsidian zu Projekt X?",
        "Was weiß ich über Machine Learning?",
        "Zeig mir meine Notizen zu Lexa",
        "Laut meinem OS ist der Status grün",
        "Hab ich Notizen zu Hermes?",
        "In meinen Notizen zu Telegram steht was?",
        "Was hab ich über den Release notiert?",
    ]:
        assert rc._obsidian_context_query(msg), f"should trigger: {msg}"


def test_trigger_stays_conservative():
    # 'was weisst DU' (model) must NOT trigger the vault; generic questions neither.
    for msg in [
        "Was weißt du über Machine Learning?",
        "Wie spät ist es?",
        "Schreib mir eine Funktion in Python",
        "Was ist Photosynthese?",
        "Starte Spotify",
        "",
    ]:
        assert not rc._obsidian_context_query(msg), f"should NOT trigger: {msg}"


def test_build_grounding_returns_block_and_files(monkeypatch):
    import backend.obsidian_context as oc
    payload = {
        "ok": True,
        "files": [
            {"path": "08_Lexa/INDEX.md", "title": "Lexa Index"},
            {"path": "05_Memory/Rollups/Current_AI_Brief.md", "title": "Brief"},
        ],
    }
    monkeypatch.setattr(oc, "build_obsidian_context_payload", lambda **kw: payload)
    monkeypatch.setattr(oc, "format_obsidian_context_for_prompt", lambda p, **kw: "VAULT-CONTEXT-BODY")

    block, used = rc._build_obsidian_grounding("was steht in meinem os")
    assert "VAULT-CONTEXT-BODY" in block
    assert "READ-ONLY Kontext" in block  # system instruction prepended
    assert "[OS:" in block               # cite-with-file instruction present
    assert used == ["08_Lexa/INDEX.md", "05_Memory/Rollups/Current_AI_Brief.md"]


def test_build_grounding_empty_when_vault_unreachable(monkeypatch):
    import backend.obsidian_context as oc
    monkeypatch.setattr(oc, "build_obsidian_context_payload", lambda **kw: {"ok": False, "files": []})
    block, used = rc._build_obsidian_grounding("topic")
    assert block == "" and used == []


def test_build_grounding_empty_when_no_files(monkeypatch):
    import backend.obsidian_context as oc
    monkeypatch.setattr(oc, "build_obsidian_context_payload", lambda **kw: {"ok": True, "files": []})
    block, used = rc._build_obsidian_grounding("topic")
    assert block == "" and used == []


def test_build_grounding_survives_builder_exception(monkeypatch):
    import backend.obsidian_context as oc
    def boom(**kw):
        raise RuntimeError("vault read failed")
    monkeypatch.setattr(oc, "build_obsidian_context_payload", boom)
    block, used = rc._build_obsidian_grounding("topic")
    assert block == "" and used == []
