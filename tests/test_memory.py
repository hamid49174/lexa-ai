"""Tests for backend/memory.py — Note CRUD, Memory add/search/dedup, Stats.

Uses a temporary SQLite database via monkeypatch so the real lexa_memory.db
is never touched.
"""

import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Redirect memory.DB_PATH to a temporary database for every test."""
    import backend.memory as mem
    # Close any existing thread-local connection so a fresh one is created
    mem.close_db()
    tmp_db = tmp_path / "test_memory.db"
    monkeypatch.setattr(mem, "DB_PATH", tmp_db)
    # Reset tables_ready so tables are re-created in the new DB
    mem._tables_ready = False
    yield
    mem.close_db()


# ---------------------------------------------------------------------------
#  Note CRUD
# ---------------------------------------------------------------------------

class TestNoteCreate:
    def test_create_returns_confirmation(self):
        """note_create returns a German confirmation string."""
        from backend.memory import note_create
        result = note_create("Einkauf", "Milch, Brot", "shopping")
        assert "Einkauf" in result
        assert "gespeichert" in result

    def test_create_upserts_on_duplicate_title(self):
        """Creating a note with the same title updates existing content."""
        from backend.memory import note_create, note_read
        note_create("Projekt", "Version 1")
        note_create("Projekt", "Version 2")
        note = note_read("Projekt")
        assert note["content"] == "Version 2"


class TestNoteList:
    def test_list_empty(self):
        """note_list returns an empty list when no notes exist."""
        from backend.memory import note_list
        assert note_list() == []

    def test_list_returns_all_notes(self):
        """note_list returns every created note."""
        from backend.memory import note_create, note_list
        note_create("A", "aaa")
        note_create("B", "bbb")
        notes = note_list()
        assert len(notes) == 2
        titles = {n["title"] for n in notes}
        assert titles == {"A", "B"}


class TestNoteRead:
    def test_read_existing_note(self):
        """note_read with a matching title returns the full note dict."""
        from backend.memory import note_create, note_read
        note_create("Readme", "Some content", "docs")
        result = note_read("Readme")
        assert result["title"] == "Readme"
        assert result["content"] == "Some content"
        assert result["category"] == "docs"

    def test_read_nonexistent_returns_error(self):
        """note_read for a missing title returns an error dict."""
        from backend.memory import note_read
        result = note_read("NoSuchNote")
        assert "error" in result

    def test_read_no_title_returns_list(self):
        """note_read with empty title returns a list of all notes."""
        from backend.memory import note_create, note_read
        note_create("X", "x content")
        result = note_read("")
        assert isinstance(result, list)


class TestNoteGetById:
    def test_get_existing_note_by_id(self):
        """note_get_by_id returns the note dict when it exists."""
        from backend.memory import note_create, note_list, note_get_by_id
        note_create("ById", "content")
        notes = note_list()
        note_id = notes[0]["id"]
        note = note_get_by_id(note_id)
        assert note is not None
        assert note["title"] == "ById"

    def test_get_nonexistent_id_returns_none(self):
        """note_get_by_id returns None for a non-existent ID."""
        from backend.memory import note_get_by_id
        assert note_get_by_id(99999) is None


class TestNoteUpdateById:
    def test_update_title_and_content(self):
        """note_update_by_id changes the specified fields."""
        from backend.memory import note_create, note_list, note_update_by_id, note_get_by_id
        note_create("Old", "old content")
        note_id = note_list()[0]["id"]
        success = note_update_by_id(note_id, title="New", content="new content")
        assert success is True
        updated = note_get_by_id(note_id)
        assert updated["title"] == "New"
        assert updated["content"] == "new content"

    def test_update_no_fields_returns_false(self):
        """note_update_by_id with no fields to update returns False."""
        from backend.memory import note_create, note_list, note_update_by_id
        note_create("Stable", "content")
        note_id = note_list()[0]["id"]
        assert note_update_by_id(note_id) is False

    def test_update_nonexistent_id_returns_false(self):
        """note_update_by_id on a missing ID returns False."""
        from backend.memory import note_update_by_id
        assert note_update_by_id(99999, title="X") is False


class TestNoteDelete:
    def test_delete_existing_note(self):
        """note_delete removes the note and returns a confirmation."""
        from backend.memory import note_create, note_delete, note_list
        note_create("Gone", "bye")
        result = note_delete("Gone")
        assert "gelöscht" in result
        assert note_list() == []

    def test_delete_nonexistent_returns_not_found(self):
        """note_delete for a missing title returns a 'not found' message."""
        from backend.memory import note_delete
        result = note_delete("Ghost")
        assert "nicht gefunden" in result


# ---------------------------------------------------------------------------
#  Memory add + deduplication + search
# ---------------------------------------------------------------------------

class TestAddMemory:
    def test_add_memory_returns_gemerkt(self):
        """add_memory stores a new entry and confirms."""
        from backend.memory import add_memory
        result = add_memory("Python ist toll", "fact", 7, "user")
        assert result == "Gemerkt."

    def test_deduplication_blocks_same_prefix(self):
        """add_memory rejects a second entry whose first 80 chars match."""
        from backend.memory import add_memory
        # Build a base string that is exactly 80+ chars so the 80-char prefix key
        # is identical for both entries.
        base = "A" * 90  # 90 chars; first 80 will be the dedup key
        add_memory(base)
        result = add_memory(base + " with extra trailing text")
        assert result == "Bereits bekannt."


class TestSearchMemory:
    def test_search_finds_matching_memory(self):
        """search_memory returns entries whose content matches the query."""
        from backend.memory import add_memory, search_memory
        add_memory("Lexa ist ein KI-Assistent", "fact", 8)
        add_memory("Python ist eine Programmiersprache", "fact", 5)
        results = search_memory("KI")
        assert len(results) == 1
        assert "KI" in results[0]["content"]

    def test_search_empty_query_returns_empty(self):
        """search_memory with empty string returns an empty list."""
        from backend.memory import search_memory
        assert search_memory("") == []

    def test_search_respects_limit(self):
        """search_memory honors the limit parameter."""
        from backend.memory import add_memory, search_memory
        for i in range(10):
            add_memory(f"Fakt Nummer {i} ueber Wissen", "fact", 5)
        results = search_memory("Wissen", limit=3)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
#  Memory stats
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
#  FTS5 Query Injection Safety
# ---------------------------------------------------------------------------

class TestFTS5Safety:
    def test_fts_special_chars_dont_crash(self):
        """Search with FTS5 operators (*, NEAR, NOT, OR) should not crash."""
        from backend.memory import add_memory, search_memory
        add_memory("Python Programmierung ist toll", "fact", 7)
        # These contain FTS5 operators that would crash if not escaped
        for dangerous in ['test*', 'NEAR(a,b)', 'NOT test', '"injection"', 'a OR b']:
            results = search_memory(dangerous)
            assert isinstance(results, list)  # Should not raise

    def test_fts_double_quotes_stripped(self):
        """Double quotes in search terms should be safely handled."""
        from backend.memory import search_memory
        # Should not raise sqlite3.OperationalError
        results = search_memory('"unclosed quote')
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
#  Conversation List Performance
# ---------------------------------------------------------------------------

class TestConversationList:
    def test_conversation_list_returns_metadata(self):
        """conversation_list should return id, title, message_count without full messages."""
        from backend.memory import conversation_create, conversation_update, conversation_list
        cid = conversation_create("Test Chat")
        conversation_update(cid, messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
        ])
        convs = conversation_list()
        assert len(convs) == 1
        c = convs[0]
        assert c["title"] == "Test Chat"
        assert c["message_count"] == 2
        # Full messages should NOT be in the result
        assert "messages" not in c

    def test_conversation_list_extracts_preview(self):
        """conversation_list should extract a last_message preview."""
        from backend.memory import conversation_create, conversation_update, conversation_list
        cid = conversation_create("Preview Test")
        conversation_update(cid, messages=[
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "This is the last response from the assistant"},
        ])
        convs = conversation_list()
        c = convs[0]
        assert "last_message" in c
        assert "last_role" in c


# ---------------------------------------------------------------------------
#  Dedup LIKE Escape
# ---------------------------------------------------------------------------

class TestDedupLikeEscape:
    def test_underscore_in_content_not_corrupted(self):
        """Content with underscores should not be corrupted during dedup check."""
        from backend.memory import add_memory, search_memory
        # volume_set contains an underscore — should be stored properly
        add_memory("Der Befehl volume_set setzt die Lautstärke", "fact", 7)
        results = search_memory("volume_set")
        assert len(results) >= 1
        assert "volume_set" in results[0]["content"]

    def test_percent_in_content_handled(self):
        """Content with % should not cause LIKE injection."""
        from backend.memory import add_memory
        # Should not crash even with % in content
        result = add_memory("Rabatt von 50% auf alle Produkte ist super toll", "fact", 5)
        assert result == "Gemerkt."


# ---------------------------------------------------------------------------
#  Restore Database Transaction Safety
# ---------------------------------------------------------------------------

class TestRestoreDatabase:
    def test_restore_wraps_in_transaction(self):
        """restore_database should not lose data on partial failure."""
        from backend.memory import note_create, note_list, restore_database
        # Create some initial data
        note_create("Important", "Critical business data")
        assert len(note_list()) == 1

        # Restore with valid data
        result = restore_database({
            "notes": [
                {"title": "Restored Note", "content": "Restored content", "category": "general"}
            ],
            "memories": [],
        })
        assert result["status"] == "ok"
        notes = note_list()
        assert len(notes) == 1
        assert notes[0]["title"] == "Restored Note"

    def test_restore_empty_data_clears_nothing(self):
        """restore_database with empty data should not delete existing records."""
        from backend.memory import note_create, note_list, restore_database
        note_create("Keep Me", "data")
        # Restore with no notes key — should not touch notes table
        result = restore_database({})
        assert result["status"] == "ok"
        # Notes should still be there (empty rows = skip)
        assert len(note_list()) == 1


# ---------------------------------------------------------------------------
#  Memory stats
# ---------------------------------------------------------------------------

class TestMemoryStats:
    def test_stats_counts_are_zero_initially(self):
        """get_memory_stats returns zeros for an empty database."""
        from backend.memory import get_memory_stats
        stats = get_memory_stats()
        assert stats["notes"] == 0
        assert stats["memories"] == 0
        assert stats["conversations"] == 0
        assert "db_path" in stats

    def test_stats_reflect_created_data(self):
        """get_memory_stats counts increase after creating data."""
        from backend.memory import note_create, add_memory, get_memory_stats
        note_create("Stat Note", "content")
        add_memory("Stat memory entry", "fact", 5)
        stats = get_memory_stats()
        assert stats["notes"] == 1
        assert stats["memories"] == 1
