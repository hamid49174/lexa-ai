"""Regressionstests aus dem Gesamt-Scan — Bereich D (STT)."""
import voice.stt as stt


def test_get_model_wrapper_exists():
    # Scan-Fix D: main.py importierte ein nicht existierendes get_model -> Pre-Warm tot.
    assert callable(getattr(stt, "get_model", None))


def test_circuit_breaker_respects_threshold():
    # Scan-Fix D: CB oeffnete schon nach 1 Fehler; CB_MAX_FAILURES wurde nie benutzt.
    stt._fail_counts["deepgram"] = 0
    stt._last_fail_times["deepgram"] = 0.0
    try:
        for _ in range(stt.CB_MAX_FAILURES - 1):
            stt._record_failure("deepgram")
        assert stt._circuit_open("deepgram") is False  # unter der Schwelle: offen lassen
        stt._record_failure("deepgram")                # Schwelle erreicht
        assert stt._fail_counts["deepgram"] == stt.CB_MAX_FAILURES
        assert stt._circuit_open("deepgram") is True    # jetzt gesperrt
        stt._record_success("deepgram")
        assert stt._circuit_open("deepgram") is False    # Erfolg setzt zurueck
    finally:
        stt._fail_counts["deepgram"] = 0
        stt._last_fail_times["deepgram"] = 0.0


def test_set_language_validates():
    assert stt.set_language("de")["success"] is True
    assert stt.set_language("de-de")["success"] is True
    assert stt.set_language("auto")["success"] is True
    assert stt.set_language("xx-INVALID")["success"] is False
    assert stt.set_language("'; DROP TABLE")["success"] is False
    assert stt.set_language("")["success"] is False


def test_delete_key_invalidates_cache_on_missing(monkeypatch):
    import keyring
    from keyring.errors import PasswordDeleteError
    stt._keys["groq"] = "cached-key"
    stt._keys_loaded["groq"] = True
    monkeypatch.setattr(keyring, "delete_password",
                        lambda *a, **k: (_ for _ in ()).throw(PasswordDeleteError("nicht vorhanden")))
    res = stt.delete_groq_key()
    assert res["success"] is True          # fehlender Key = bereits geloescht = Erfolg
    assert stt._keys["groq"] is None        # Cache trotzdem geleert (kein weiter-aktiver Key)
    assert stt._keys_loaded["groq"] is True
