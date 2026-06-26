"""Regressionstests aus dem Gedächtnis-Audit — Bereich F."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.embeddings as embeddings
import backend.memory as memory
from backend import router_memory


def _client():
    app = FastAPI()
    app.include_router(router_memory.router)
    return TestClient(app)


# ── MED: falsch getyptes JSON darf keinen 500 ausloesen (str()-Cast) ─────────

def test_clipboard_add_non_string_text_no_500(monkeypatch):
    monkeypatch.setattr(router_memory.memory, "clipboard_add", lambda text: "added:1")
    client = _client()
    for bad in (123, True, ["a"], {"x": 1}):
        r = client.post("/clipboard/add", json={"text": bad})
        assert r.status_code == 200, f"text={bad!r} -> {r.status_code}"


def test_snippets_create_non_string_no_500(monkeypatch):
    monkeypatch.setattr(router_memory.memory, "snippet_create", lambda name, text: "created")
    client = _client()
    # nicht-String name/text: kein AttributeError-500; str()-Cast macht sie nutzbar
    r = client.post("/snippets", json={"name": 5, "text": True})
    assert r.status_code == 200, r.text
    # echte Leerwerte weiterhin 400
    r2 = client.post("/snippets", json={"name": "", "text": ""})
    assert r2.status_code == 400


# ── LOW: auto_remember waehlt das textlich ZUERST vorkommende Merk-Kommando ──

def test_auto_remember_picks_earliest_command_by_position(monkeypatch):
    saved = []
    monkeypatch.setattr(memory, "add_memory",
                        lambda content, **kw: saved.append(content) or 1)
    # "speicher" steht VOR "merke dir" -> Inhalt muss ab "speicher" extrahiert werden,
    # nicht ab "merke dir" (Listen-Reihenfolge wuerde faelschlich "merke dir" waehlen).
    memory.auto_remember("Bitte speicher Projekt Alpha ab und merke dir sonst nichts", "")
    assert saved, "es wurde nichts gespeichert"
    joined = " ".join(saved)
    assert "Projekt Alpha" in joined


# ── LOW: lokale Embeddings kappen die Eingabe (Konsistenz mit OpenAI-Pfad) ───

def test_local_embedding_caps_input_length():
    long_text = "wort " * 5000          # ~25k Zeichen
    vec_long = embeddings._embed_local(long_text)
    vec_capped = embeddings._embed_local(long_text[:8000])
    assert isinstance(vec_long, list) and len(vec_long) > 0
    # identischer Vektor, da intern auf 8000 Zeichen gekappt wird
    assert vec_long == vec_capped
