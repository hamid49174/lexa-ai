"""SQLite schema and migration helpers for backend.memory."""

from __future__ import annotations

import logging
import sqlite3
from typing import Callable

from backend.memory_core.nlp import classify_memory_type, normalize_memory_type

logger = logging.getLogger("lexa.memory.schema")

VALID_TABLES = frozenset({
    "notes", "memories", "user_profile", "interactions", "routines",
    "snippets", "conversations", "clipboard_entries", "session_state", "timers",
    "conversation_summaries",
})

VALID_COLUMNS = {
    "notes": {"id", "title", "content", "category", "created_at", "updated_at", "embedding"},
    "memories": {
        "id", "content", "category", "memory_type", "importance", "source", "created_at",
        "embedding", "embedding_provider", "embedding_model", "embedding_dimension",
        "embedding_created_at", "access_count", "last_accessed_at",
    },
    "user_profile": {"key", "value", "updated_at"},
    "interactions": {"id", "user_message", "ai_reply", "had_action", "created_at"},
    "routines": {"id", "name", "description", "schedule", "actions", "enabled", "last_run", "created_at"},
    "snippets": {"name", "text", "use_count", "created_at"},
    "conversations": {"id", "title", "messages", "message_count", "created_at", "updated_at"},
    "clipboard_entries": {"id", "text", "created_at"},
    "session_state": {"key", "value", "updated_at"},
    "timers": {"id", "message", "fire_at", "fired", "acknowledged", "created_at"},
    "conversation_summaries": {"id", "conversation_id", "summary", "message_range", "created_at"},
}


def _backfill_memory_types(db: sqlite3.Connection, *, force: bool = False) -> int:
    """Backfill missing/invalid memory_type values from existing row data."""
    rows = db.execute(
        "SELECT id, content, category, source, memory_type FROM memories"
    ).fetchall()
    updated = 0
    for row in rows:
        current = normalize_memory_type(row["memory_type"])
        if current and not force:
            continue
        resolved = classify_memory_type(
            row["content"],
            row["category"],
            row["source"],
        )
        if current != resolved:
            db.execute(
                "UPDATE memories SET memory_type = ? WHERE id = ?",
                (resolved, row["id"]),
            )
            updated += 1
    if updated:
        db.commit()
        logger.info("Memory type migration: backfilled %s memory rows", updated)
    return updated


def _ensure_memory_type_schema(db: sqlite3.Connection) -> None:
    """Add memory_type to existing DBs and keep the new index migration-safe."""
    added_column = False
    try:
        db.execute("SELECT memory_type FROM memories LIMIT 1")
    except sqlite3.OperationalError:
        try:
            db.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'semantic'")
            db.commit()
            added_column = True
            logger.info("Memory migration: added 'memory_type' column to memories")
        except Exception as e:
            logger.warning(f"Memory type column migration skipped: {e}")
            return

    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        db.commit()
    except Exception as e:
        logger.warning(f"Memory type index migration skipped: {e}")

    try:
        _backfill_memory_types(db, force=added_column)
    except Exception as e:
        logger.warning(f"Memory type backfill skipped: {e}")


def _ensure_embedding_metadata_schema(db: sqlite3.Connection) -> None:
    """Add embedding metadata columns and backfill legacy vector rows safely."""
    migrations = [
        ("embedding_provider", "TEXT"),
        ("embedding_model", "TEXT"),
        ("embedding_dimension", "INTEGER"),
        ("embedding_created_at", "TEXT"),
    ]
    for column, column_type in migrations:
        try:
            db.execute(f"SELECT {column} FROM memories LIMIT 1")
        except sqlite3.OperationalError:
            try:
                db.execute(f"ALTER TABLE memories ADD COLUMN {column} {column_type}")
                db.commit()
                logger.info("Embedding metadata migration: added '%s' column", column)
            except Exception as e:
                logger.warning(f"Embedding metadata column migration skipped for {column}: {e}")

    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_memories_embedding_meta ON memories(embedding_provider, embedding_model, embedding_dimension)")
        db.commit()
    except Exception as e:
        logger.warning(f"Embedding metadata index migration skipped: {e}")

    try:
        _backfill_embedding_metadata(db)
    except Exception as e:
        logger.warning(f"Embedding metadata backfill skipped: {e}")


def _backfill_embedding_metadata(db: sqlite3.Connection) -> int:
    """Backfill legacy embedding metadata from vector dimensions when possible."""
    try:
        from backend.embeddings import blob_to_vector, infer_embedding_metadata_from_dimension
    except ImportError:
        return 0

    rows = db.execute(
        """SELECT id, embedding, embedding_provider, embedding_model,
                  embedding_dimension, embedding_created_at, created_at
           FROM memories
           WHERE embedding IS NOT NULL"""
    ).fetchall()
    updated = 0
    for row in rows:
        existing_dimension = row["embedding_dimension"]
        existing_provider = row["embedding_provider"]
        existing_model = row["embedding_model"]
        if existing_provider and existing_model and existing_dimension:
            continue

        vector = blob_to_vector(row["embedding"])
        if vector is None:
            logger.warning("Skipping corrupt legacy memory embedding metadata backfill: id=%s", row["id"])
            continue
        inferred = infer_embedding_metadata_from_dimension(len(vector))
        if not inferred:
            logger.warning(
                "Skipping unknown legacy memory embedding metadata backfill: id=%s dimension=%s",
                row["id"],
                len(vector),
            )
            continue

        db.execute(
            """UPDATE memories
               SET embedding_provider = ?,
                   embedding_model = ?,
                   embedding_dimension = ?,
                   embedding_created_at = COALESCE(embedding_created_at, created_at, datetime('now', 'localtime'))
               WHERE id = ?""",
            (
                inferred["provider"],
                inferred["model"],
                inferred["dimension"],
                row["id"],
            ),
        )
        updated += 1

    if updated:
        db.commit()
        logger.info("Embedding metadata migration: backfilled %s memory rows", updated)
    return updated


def _ensure_memory_ranking_schema(db: sqlite3.Connection) -> None:
    """Add lightweight ranking/access tracking columns to existing DBs."""
    migrations = [
        ("access_count", "INTEGER DEFAULT 0"),
        ("last_accessed_at", "TEXT"),
    ]
    for column, column_type in migrations:
        try:
            db.execute(f"SELECT {column} FROM memories LIMIT 1")
        except sqlite3.OperationalError:
            try:
                db.execute(f"ALTER TABLE memories ADD COLUMN {column} {column_type}")
                db.commit()
                logger.info("Memory ranking migration: added '%s' column", column)
            except Exception as e:
                logger.warning(f"Memory ranking column migration skipped for {column}: {e}")

    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_memories_access ON memories(access_count DESC, last_accessed_at DESC)")
        db.commit()
    except Exception as e:
        logger.warning(f"Memory ranking index migration skipped: {e}")


def initialize_memory_schema(db: sqlite3.Connection, *, rebuild_fts_once: Callable[[], None] | None = None) -> None:
    """Initialize all memory tables."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'fact',
            memory_type TEXT DEFAULT 'semantic'
                CHECK(memory_type IN ('working', 'episodic', 'semantic', 'procedural', 'preference', 'system')),
            importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            source TEXT DEFAULT 'auto',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            embedding BLOB,
            embedding_provider TEXT,
            embedding_model TEXT,
            embedding_dimension INTEGER,
            embedding_created_at TEXT,
            access_count INTEGER DEFAULT 0,
            last_accessed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT NOT NULL,
            ai_reply TEXT NOT NULL,
            had_action INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            schedule TEXT NOT NULL,
            actions TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_run TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS snippets (
            name TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            use_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Neuer Chat',
            messages TEXT NOT NULL DEFAULT '[]',
            message_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS clipboard_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS session_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        -- Original indexes
        CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_clipboard_id ON clipboard_entries(id DESC);

        -- Additional performance indexes
        CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
        CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);

        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL DEFAULT 'Timer abgelaufen!',
            fire_at REAL NOT NULL,
            fired INTEGER DEFAULT 0,
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_timers_fire_at ON timers(fire_at);

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            summary TEXT NOT NULL,
            message_range TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_conv_summary_conv ON conversation_summaries(conversation_id);
    """)

    db.commit()
    _ensure_memory_type_schema(db)
    _ensure_memory_ranking_schema(db)

    # Phase 42: Add embedding BLOB column to memories before FTS triggers
    # exist, so legacy metadata backfill cannot trip stale FTS state.
    try:
        db.execute("SELECT embedding FROM memories LIMIT 1")
    except sqlite3.OperationalError:
        try:
            db.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
            db.commit()
            logger.info("Phase 42 migration: Added 'embedding' column to memories")
        except Exception as e:
            logger.warning(f"Embedding column migration skipped: {e}")

    _ensure_embedding_metadata_schema(db)

    # FTS5 full-text search indexes
    try:
        db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                title, content, category,
                content='notes', content_rowid='id'
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, category,
                content='memories', content_rowid='id'
            );
        """)

        # Triggers to keep FTS in sync
        db.executescript("""
            CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(rowid, title, content, category)
                VALUES (new.id, new.title, new.content, new.category);
            END;
            CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, content, category)
                VALUES ('delete', old.id, old.title, old.content, old.category);
            END;
            CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, content, category)
                VALUES ('delete', old.id, old.title, old.content, old.category);
                INSERT INTO notes_fts(rowid, title, content, category)
                VALUES (new.id, new.title, new.content, new.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.id, new.content, new.category);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.id, new.content, new.category);
            END;
        """)
    except Exception as e:
        logger.warning(f"FTS5 setup skipped (not supported?): {e}")

    db.commit()

    # Phase 42: Add embedding BLOB column to notes (migration-safe)
    try:
        db.execute("SELECT embedding FROM notes LIMIT 1")
    except sqlite3.OperationalError:
        try:
            db.execute("ALTER TABLE notes ADD COLUMN embedding BLOB")
            db.commit()
            logger.info("Phase 42 migration: Added 'embedding' column to notes")
        except Exception as e:
            logger.warning(f"Notes embedding column migration skipped: {e}")

    # Rebuild FTS index once on first init; the facade owns the process-wide guard.
    if rebuild_fts_once is not None:
        rebuild_fts_once()
