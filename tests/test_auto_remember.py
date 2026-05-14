"""Tests for auto_remember() in backend/memory.py — identity extraction,
explicit remember, preference detection, and hallucination safety."""

import pytest


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Redirect memory.DB_PATH to a temporary database for every test."""
    import backend.memory as mem
    mem.close_db()
    tmp_db = tmp_path / "test_auto_remember.db"
    monkeypatch.setattr(mem, "DB_PATH", tmp_db)
    mem._tables_ready = False
    yield
    mem.close_db()


# ---------------------------------------------------------------------------
#  Explicit "remember" commands
# ---------------------------------------------------------------------------

class TestExplicitRemember:
    def test_merke_dir_saves_memory(self):
        """'merke dir ich mag Pizza' should save a memory."""
        from backend.memory import auto_remember, search_memory
        auto_remember("merke dir ich mag Pizza", "Okay, gemerkt!")
        results = search_memory("Pizza")
        assert len(results) >= 1
        assert any("Pizza" in r["content"] for r in results)

    def test_dass_stripped_as_word_not_chars(self):
        """'merke dir dass ich morgen frei habe' should strip 'dass' as word,
        not strip d/a/s characters from the content."""
        from backend.memory import auto_remember, search_memory
        auto_remember("merke dir dass ich morgen frei habe", "Gemerkt!")
        results = search_memory("morgen frei")
        assert len(results) >= 1
        content = results[0]["content"]
        # "ich morgen frei habe" should be intact, not "ich morgen frei hbe" (stripped 'a')
        assert "morgen frei habe" in content.lower() or "morgen frei" in content.lower()

    def test_dass_only_strips_leading_dass(self):
        """Content starting with 'dass' after prefix should have 'dass' removed."""
        from backend.memory import auto_remember, search_memory
        auto_remember("erinnere dich dass der Termin am Montag ist", "Gemerkt!")
        results = search_memory("Termin Montag")
        assert len(results) >= 1
        content = results[0]["content"]
        # Should contain "der Termin am Montag" not "der Termin m Montg"
        assert "Termin" in content

    def test_too_long_message_ignored(self):
        """Messages > 300 chars should not trigger explicit remember."""
        from backend.memory import auto_remember, search_memory
        long_msg = "merke dir " + "x" * 300
        auto_remember(long_msg, "OK")
        results = search_memory("xxx")
        assert len(results) == 0


# ---------------------------------------------------------------------------
#  Identity extraction from USER messages
# ---------------------------------------------------------------------------

class TestIdentityExtraction:
    def test_ich_heisse_extracts_name(self):
        from backend.memory import auto_remember, search_memory
        auto_remember("ich heiße Alexander", "Hallo Alexander!")
        results = search_memory("Name Alexander")
        assert len(results) >= 1
        assert any("Alexander" in r["content"] for r in results)

    def test_ich_arbeite_bei_extracts_employer(self):
        from backend.memory import auto_remember, search_memory
        auto_remember("ich arbeite bei Google", "Cool!")
        results = search_memory("Arbeitgeber Google")
        assert len(results) >= 1
        assert any("Google" in r["content"] for r in results)

    def test_ich_wohne_in_extracts_location(self):
        from backend.memory import auto_remember, search_memory
        auto_remember("ich wohne in Berlin", "Schöne Stadt!")
        results = search_memory("Wohnort Berlin")
        assert len(results) >= 1
        assert any("Berlin" in r["content"] for r in results)


# ---------------------------------------------------------------------------
#  AI-reply hallucination safety
# ---------------------------------------------------------------------------

class TestHallucinationSafety:
    def test_ai_hallucinated_name_not_saved(self):
        """If AI says 'dein Name ist Max' but user never said that,
        it should NOT be saved to memory."""
        from backend.memory import auto_remember, search_memory
        # User says something generic, AI hallucinates a name
        auto_remember(
            "erzähl mir einen Witz",
            "Klar! Ach übrigens, dein Name ist Max, richtig?"
        )
        results = search_memory("Name Max")
        # Should NOT find any AI-inferred identity facts
        ai_inferred = [r for r in results if "von KI erkannt" in r["content"]]
        assert len(ai_inferred) == 0


# ---------------------------------------------------------------------------
#  Preference extraction
# ---------------------------------------------------------------------------

class TestPreferenceExtraction:
    def test_ich_mag_saves_preference(self):
        from backend.memory import auto_remember, search_memory
        auto_remember("ich mag Python sehr gerne", "Gute Wahl!")
        results = search_memory("Python")
        assert len(results) >= 1

    def test_ich_liebe_saves_preference(self):
        from backend.memory import auto_remember, search_memory
        auto_remember("ich liebe Kaffee", "Ich auch!")
        results = search_memory("Kaffee")
        assert len(results) >= 1
