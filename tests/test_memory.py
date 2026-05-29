"""Tests for backend/memory.py — Note CRUD, Memory add/search/dedup, Stats.

Uses a temporary SQLite database via monkeypatch so the real lexa_memory.db
is never touched.
"""

import pytest
import sqlite3
from datetime import datetime, timedelta
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


def test_memory_facade_uses_extracted_core_helpers():
    import backend.memory as mem
    import backend.memory_core.connection as connection
    import backend.memory_core.nlp as nlp
    import backend.memory_core.ranking as ranking
    import backend.memory_core.schema as schema

    assert mem.MEMORY_TYPES is nlp.MEMORY_TYPES
    assert mem._extract_search_terms is nlp.extract_search_terms
    assert mem._normalize_for_dedup is nlp.normalize_for_dedup
    assert mem._rank_memory_results is ranking.rank_memory_results
    assert mem.initialize_memory_schema is schema.initialize_memory_schema
    assert mem.get_thread_memory_connection is connection.get_thread_memory_connection
    assert mem._VALID_TABLES is schema.VALID_TABLES


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

    def test_add_memory_accepts_explicit_memory_type(self):
        """Explicit valid memory_type overrides deterministic classification."""
        from backend.memory import add_memory, search_memory
        add_memory("Manual override memory entry", "fact", 5, "user", memory_type="working")
        results = search_memory("override memory")
        assert results[0]["category"] == "fact"
        assert results[0]["memory_type"] == "working"

    def test_deduplication_blocks_same_prefix(self):
        """add_memory rejects a second entry whose first 80 chars match."""
        from backend.memory import add_memory
        # Build a base string that is exactly 80+ chars so the 80-char prefix key
        # is identical for both entries.
        base = "A" * 90  # 90 chars; first 80 will be the dedup key
        add_memory(base)
        result = add_memory(base + " with extra trailing text")
        assert result == "Bereits bekannt."


class TestMemoryTypeClassification:
    def test_classifies_each_memory_type(self):
        """Deterministic rules cover every explicit memory type."""
        from backend.memory import classify_memory_type
        examples = {
            "working": ("Merkzettel: Follow up with Alex", "explicit", "auto"),
            "episodic": ("Meeting: Projektstand am Montag", "event", "auto"),
            "semantic": ("Python ist eine Programmiersprache", "fact", "user"),
            "procedural": ("Der Befehl volume_set setzt die Lautstaerke", "fact", "user"),
            "preference": ("Praeferenz: mag Kaffee", "fact", "auto"),
            "system": ("Lexa: fallback provider configured", "fact", "system"),
        }
        for expected_type, (content, category, source) in examples.items():
            assert classify_memory_type(content, category, source) == expected_type

    def test_invalid_explicit_memory_type_falls_back_to_classification(self):
        """Unknown memory_type values do not enter the database."""
        from backend.memory import add_memory, search_memory
        add_memory("Praeferenz: mag Tee", "fact", 5, "user", memory_type="unknown")
        results = search_memory("Tee")
        assert results[0]["memory_type"] == "preference"


class TestSearchMemory:
    def test_search_finds_matching_memory(self):
        """search_memory returns entries whose content matches the query."""
        from backend.memory import add_memory, search_memory
        add_memory("Lexa ist ein KI-Assistent", "fact", 8)
        add_memory("Python ist eine Programmiersprache", "fact", 5)
        results = search_memory("KI")
        assert len(results) == 1
        assert "KI" in results[0]["content"]

    def test_search_returns_memory_type_and_preserves_category(self):
        """Search includes memory_type without replacing the legacy category."""
        from backend.memory import add_memory, search_memory
        add_memory("Lieblingssprache: Python", "preference", 7)
        results = search_memory("Python")
        assert results[0]["category"] == "preference"
        assert results[0]["memory_type"] == "preference"

    def test_global_search_returns_memory_type(self):
        """Global search exposes the new type for memory results."""
        from backend.memory import add_memory, global_search
        add_memory("Der Befehl volume_set setzt die Lautstaerke", "command", 7)
        results = global_search("volume_set")
        assert results["memories"][0]["category"] == "command"
        assert results["memories"][0]["memory_type"] == "procedural"

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


class TestMemoryRanking:
    def _set_created_at(self, content_like: str, modifier: str) -> None:
        import backend.memory as mem
        db = mem._get_db()
        db.execute(
            "UPDATE memories SET created_at = datetime('now', ?, 'localtime') WHERE content LIKE ?",
            (modifier, f"%{content_like}%"),
        )
        db.commit()

    def test_recent_important_memory_outranks_old_generic(self, monkeypatch):
        """Recent critical memories should outrank old generic matches."""
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("Project Alpha generic planning note", "fact", 3)
        add_memory("Project Alpha critical launch blocker", "explicit", 10)
        self._set_created_at("generic", "-400 days")
        self._set_created_at("critical", "-1 hours")

        results = search_memory("project alpha")

        assert results[0]["content"] == "Project Alpha critical launch blocker"
        assert results[0]["memory_type"] == "working"

    def test_preference_memory_ranks_high_for_personalization_query(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("Coffee prefer is a useful general fact", "fact", 8)
        add_memory("Praeferenz: coffee prefer dunkel geroestet", "preference", 5)

        results = search_memory("coffee prefer")

        assert results[0]["memory_type"] == "preference"
        assert "coffee" in results[0]["content"]

    def test_procedural_memory_ranks_high_for_workflow_query(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("volume_set exists in the audio system", "fact", 8)
        add_memory("Der Befehl volume_set setzt die Lautstaerke", "command", 5)

        results = search_memory("how do I use volume_set workflow")

        assert results[0]["memory_type"] == "procedural"

    def test_episodic_memory_ranks_high_for_event_query(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("Roadmap review is a general planning topic", "fact", 8)
        add_memory("Meeting: Roadmap Review mit Alex", "event", 5)

        results = search_memory("roadmap review meeting history")

        assert results[0]["memory_type"] == "episodic"

    def test_semantic_memory_ranks_high_for_factual_query(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("System: Python provider diagnostic note", "system", 8, "system")
        add_memory("Python ist eine Programmiersprache", "fact", 6)

        results = search_memory("what fact Python")

        assert results[0]["memory_type"] == "semantic"

    def test_ranking_metadata_is_opt_in(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory
        add_memory("Praeferenz: mag gruene Tasse", "preference", 6)

        default_results = search_memory("tasse preference")
        debug_results = search_memory("tasse preference", include_ranking=True)

        assert "_ranking" not in default_results[0]
        ranking = debug_results[0]["_ranking"]
        assert set(ranking) == {
            "lexical_score",
            "semantic_score",
            "recency_score",
            "importance_score",
            "access_score",
            "memory_type_weight",
            "final_score",
        }

    def test_specific_semantic_query_outranks_recent_keyword_noise(self):
        from backend.memory import _rank_memory_results

        old = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d %H:%M:%S")
        recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ranked = _rank_memory_results(
            [
                {
                    "id": 1,
                    "content": "Detailed migration architecture from the Q4 project plan",
                    "importance": 5,
                    "memory_type": "semantic",
                    "created_at": old,
                    "access_count": 0,
                    "_semantic_score": 0.95,
                },
                {
                    "id": 2,
                    "content": "Q4 project plan migration status noise",
                    "importance": 5,
                    "memory_type": "semantic",
                    "created_at": recent,
                    "access_count": 0,
                    "_semantic_score": 0.0,
                },
            ],
            "Was war der detaillierte Q4 project plan fuer migration architecture?",
            ["detaillierte", "project", "migration", "architecture", "plan"],
        )

        assert ranked[0]["id"] == 1

    def test_short_memory_query_can_still_prefer_recent_context(self):
        from backend.memory import _rank_memory_results

        old = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
        recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ranked = _rank_memory_results(
            [
                {
                    "id": 1,
                    "content": "news archive",
                    "importance": 5,
                    "memory_type": "semantic",
                    "created_at": old,
                    "access_count": 0,
                    "_semantic_score": 0.40,
                },
                {
                    "id": 2,
                    "content": "news fresh",
                    "importance": 5,
                    "memory_type": "semantic",
                    "created_at": recent,
                    "access_count": 0,
                    "_semantic_score": 0.30,
                },
            ],
            "news",
            ["news"],
        )

        assert ranked[0]["id"] == 2

    def test_access_tracking_updates_returned_memory(self, monkeypatch):
        monkeypatch.setattr("backend.config.EMBEDDING_ENABLED", False)
        from backend.memory import add_memory, search_memory, _get_db
        add_memory("Access tracking kiwi marker", "fact", 5)

        search_memory("kiwi marker")

        row = _get_db().execute(
            "SELECT access_count, last_accessed_at FROM memories WHERE content LIKE ?",
            ("%kiwi%",),
        ).fetchone()
        assert row["access_count"] >= 1
        assert row["last_accessed_at"]

    def test_stop_words_cover_german_and_english(self):
        from backend.memory import _extract_search_terms

        assert _extract_search_terms("the and about python memory") == ["python", "memory"]
        assert "und" not in _extract_search_terms("und der python speicher")


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
#  Memory Graph
# ---------------------------------------------------------------------------

class TestMemoryGraph:
    def test_memory_graph_returns_read_only_compact_payload(self):
        """memory_graph exposes a compact read-only graph without full bodies."""
        from backend.memory import (
            add_memory,
            conversation_create,
            conversation_update,
            get_memory_stats,
            memory_graph,
            note_create,
            routine_create,
            snippet_create,
        )

        hidden_tail = "TAIL_SHOULD_NOT_LEAK_" * 12
        note_create(
            "Graph Project",
            "Visible graph note " + ("shared topology " * 90) + hidden_tail,
            "project",
        )
        add_memory(
            "Preference: Nutzer mag dunkle Obsidian Graphen mit lokalen Knoten",
            "preference",
            8,
            "user",
        )
        snippet_create("Graph Snippet", "shared topology snippet for graph display")
        routine_create(
            "Graph Routine",
            "shared topology review routine",
            "daily 09:00",
            [{"tool": "noop", "params": {}}],
        )
        cid = conversation_create("Graph Chat")
        conversation_update(cid, messages=[
            {"role": "user", "content": "Bitte zeig shared topology"},
            {"role": "assistant", "content": "Ich zeige den lokalen Graphen."},
        ])
        before = get_memory_stats()

        graph = memory_graph(140)
        after = get_memory_stats()

        assert before["notes"] == after["notes"]
        assert before["memories"] == after["memories"]
        assert graph["status"] == "ok"
        assert graph["source"] == "local_sqlite_readonly"
        assert len(graph["nodes"]) >= 8
        assert len(graph["links"]) >= 5
        node_ids = {node["id"] for node in graph["nodes"]}
        node_types = {node["type"] for node in graph["nodes"]}
        assert "hub:memory" in node_ids
        assert any(node_id.startswith("note:") for node_id in node_ids)
        assert any(node_id.startswith("memory:") for node_id in node_ids)
        assert any(node_id.startswith("conversation:") for node_id in node_ids)
        assert any(node_id.startswith("routine:") for node_id in node_ids)
        assert any(node_id.startswith("snippet:") for node_id in node_ids)
        assert {"hub", "group", "memory", "note", "conversation"}.issubset(node_types)
        assert all("content" not in node for node in graph["nodes"])
        assert all(len(node.get("preview", "")) <= 160 for node in graph["nodes"])
        assert hidden_tail not in str(graph)


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
    def test_old_memory_table_migrates_memory_type(self):
        """Existing DBs without memory_type are classified during init."""
        import backend.memory as mem
        mem.close_db()
        conn = sqlite3.connect(mem.DB_PATH)
        conn.execute(
            """CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'fact',
                importance INTEGER DEFAULT 5,
                source TEXT DEFAULT 'auto',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )"""
        )
        conn.execute(
            "INSERT INTO memories (content, category, importance, source) VALUES (?, ?, ?, ?)",
            ("Praeferenz: mag Tee", "fact", 6, "auto"),
        )
        conn.commit()
        conn.close()
        mem._tables_ready = False

        db = mem._get_db()
        row = db.execute(
            "SELECT category, memory_type, access_count, last_accessed_at FROM memories WHERE content LIKE ?",
            ("%Tee%",),
        ).fetchone()
        assert row["category"] == "fact"
        assert row["memory_type"] == "preference"
        assert row["access_count"] == 0
        assert row["last_accessed_at"] is None

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

    def test_restore_old_memory_rows_classifies_missing_memory_type(self):
        """Old backups without memory_type restore with classified types."""
        from backend.memory import restore_database, search_memory
        result = restore_database({
            "memories": [
                {
                    "content": "Der Befehl volume_set setzt die Lautstaerke",
                    "category": "fact",
                    "importance": 7,
                    "source": "user",
                }
            ]
        })
        assert result["status"] == "ok"
        rows = search_memory("volume_set")
        assert rows[0]["category"] == "fact"
        assert rows[0]["memory_type"] == "procedural"


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
