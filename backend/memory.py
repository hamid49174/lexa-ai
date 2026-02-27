"""Lexa AI — SQLite Memory System
Langzeitgedächtnis: Notizen, User-Profil, Kontext-Erinnerungen, Auto-Learning
"""

import sqlite3
import logging
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("lexa.memory")

DB_PATH = Path(__file__).resolve().parent.parent / "lexa_memory.db"


def _get_db() -> sqlite3.Connection:
    """Get database connection with auto-init."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _init_tables(db)
    return db


def _init_tables(db: sqlite3.Connection):
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
            importance INTEGER DEFAULT 5,
            source TEXT DEFAULT 'auto',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
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

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Neuer Chat',
            messages TEXT NOT NULL DEFAULT '[]',
            message_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
    """)
    db.commit()


# ══════════════════════════════════════════════════
#  NOTIZEN
# ══════════════════════════════════════════════════

def note_create(title: str, content: str, category: str = "general") -> str:
    """Create or update a note."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO notes (title, content, category)
               VALUES (?, ?, ?)
               ON CONFLICT(title) DO UPDATE SET
               content=excluded.content, category=excluded.category,
               updated_at=datetime('now','localtime')""",
            (title, content, category),
        )
        db.commit()
        return f"Notiz '{title}' gespeichert."
    finally:
        db.close()


def note_read(title: str = "") -> dict | list:
    """Read a specific note or search by title."""
    db = _get_db()
    try:
        if title:
            row = db.execute(
                "SELECT * FROM notes WHERE title LIKE ?",
                (f"%{title}%",),
            ).fetchone()
            if row:
                return dict(row)
            return {"error": f"Notiz '{title}' nicht gefunden."}
        return [dict(r) for r in db.execute(
            "SELECT id, title, category, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()]
    finally:
        db.close()


def note_list() -> list[dict]:
    """List all notes."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT id, title, category, created_at FROM notes ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def note_delete(title: str) -> str:
    """Delete a note by title."""
    db = _get_db()
    try:
        result = db.execute("DELETE FROM notes WHERE title = ?", (title,))
        db.commit()
        if result.rowcount:
            return f"Notiz '{title}' gelöscht."
        return f"Notiz '{title}' nicht gefunden."
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  GEDÄCHTNIS (Auto-Learning Memories)
# ══════════════════════════════════════════════════

def add_memory(content: str, category: str = "fact", importance: int = 5, source: str = "user") -> str:
    """Add a memory entry."""
    db = _get_db()
    try:
        db.execute(
            "INSERT INTO memories (content, category, importance, source) VALUES (?, ?, ?, ?)",
            (content, category, importance, source),
        )
        db.commit()
        return "Gemerkt."
    finally:
        db.close()


def search_memory(query: str, limit: int = 5) -> list[dict]:
    """Search memories by content (simple LIKE search)."""
    db = _get_db()
    try:
        words = query.lower().split()
        if not words:
            return []

        # Build search: any word match, ordered by importance
        conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
        params = [f"%{w}%" for w in words]

        rows = db.execute(
            f"""SELECT content, category, importance, created_at
                FROM memories
                WHERE {conditions}
                ORDER BY importance DESC, created_at DESC
                LIMIT ?""",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def auto_remember(user_msg: str, ai_reply: str):
    """Auto-extract and save important facts from conversations."""
    db = _get_db()
    try:
        # Save interaction
        has_action = 1 if '"action"' in ai_reply else 0
        db.execute(
            "INSERT INTO interactions (user_message, ai_reply, had_action) VALUES (?, ?, ?)",
            (user_msg, ai_reply[:1000], has_action),
        )

        # Auto-detect preferences and facts
        msg_lower = user_msg.lower()

        # Detect preference patterns
        preference_patterns = [
            "ich mag", "ich liebe", "ich hasse", "ich bevorzuge",
            "mein lieblings", "meine lieblings", "ich arbeite",
            "ich bin", "ich wohne", "mein name",
        ]
        for pattern in preference_patterns:
            if pattern in msg_lower and len(user_msg) < 200:
                db.execute(
                    "INSERT INTO memories (content, category, importance, source) VALUES (?, 'preference', 7, 'auto')",
                    (f"User sagte: {user_msg}",),
                )
                break

        # Detect names/places mentioned
        if any(w in msg_lower for w in ["heißt", "name ist", "wohne in", "arbeite bei"]):
            db.execute(
                "INSERT INTO memories (content, category, importance, source) VALUES (?, 'identity', 9, 'auto')",
                (f"User Info: {user_msg}",),
            )

        db.commit()

        # Keep interactions table from growing too large (last 500)
        db.execute(
            "DELETE FROM interactions WHERE id NOT IN (SELECT id FROM interactions ORDER BY id DESC LIMIT 500)"
        )
        db.commit()
    except Exception as e:
        logger.debug(f"Auto-remember failed: {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  USER-PROFIL
# ══════════════════════════════════════════════════

def set_profile(key: str, value: str) -> str:
    """Set a user profile entry."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO user_profile (key, value)
               VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET
               value=excluded.value, updated_at=datetime('now','localtime')""",
            (key, value),
        )
        db.commit()
        return f"Profil '{key}' gespeichert."
    finally:
        db.close()


def get_user_profile() -> str | None:
    """Get compact user profile string for AI context."""
    db = _get_db()
    try:
        rows = db.execute("SELECT key, value FROM user_profile").fetchall()
        if not rows:
            return None
        return ", ".join(f"{r['key']}={r['value']}" for r in rows)
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  ROUTINEN / TAGESPLANUNG
# ══════════════════════════════════════════════════

def routine_create(name: str, description: str, schedule: str, actions: list[dict]) -> str:
    """Create a daily routine/plan."""
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO routines (name, description, schedule, actions)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
               description=excluded.description, schedule=excluded.schedule,
               actions=excluded.actions""",
            (name, description, schedule, json.dumps(actions)),
        )
        db.commit()
        return f"Routine '{name}' erstellt."
    finally:
        db.close()


def routine_list() -> list[dict]:
    """List all routines."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT id, name, description, schedule, enabled, last_run FROM routines ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def routine_get(name: str) -> dict | None:
    """Get a specific routine with its actions."""
    db = _get_db()
    try:
        row = db.execute("SELECT * FROM routines WHERE name = ?", (name,)).fetchone()
        if row:
            d = dict(row)
            d["actions"] = json.loads(d["actions"])
            return d
        return None
    finally:
        db.close()


def routine_delete(name: str) -> str:
    """Delete a routine."""
    db = _get_db()
    try:
        result = db.execute("DELETE FROM routines WHERE name = ?", (name,))
        db.commit()
        if result.rowcount:
            return f"Routine '{name}' gelöscht."
        return f"Routine '{name}' nicht gefunden."
    finally:
        db.close()


def routine_toggle(name: str) -> str:
    """Enable/disable a routine."""
    db = _get_db()
    try:
        db.execute(
            "UPDATE routines SET enabled = CASE WHEN enabled=1 THEN 0 ELSE 1 END WHERE name = ?",
            (name,),
        )
        db.commit()
        return f"Routine '{name}' umgeschaltet."
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  CONVERSATIONS
# ══════════════════════════════════════════════════

def conversation_create(title: str = "Neuer Chat") -> int:
    """Create a new conversation, return its ID."""
    db = _get_db()
    try:
        cursor = db.execute(
            "INSERT INTO conversations (title) VALUES (?)", (title,)
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


def conversation_list(limit: int = 50) -> list[dict]:
    """List conversations ordered by last update."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT id, title, message_count, created_at, updated_at "
            "FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def conversation_get(conv_id: int) -> dict | None:
    """Get a conversation with its messages."""
    db = _get_db()
    try:
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d["messages"] = json.loads(d["messages"])
            return d
        return None
    finally:
        db.close()


def conversation_update(conv_id: int, title: str | None = None, messages: list | None = None) -> str:
    """Update conversation title and/or messages."""
    db = _get_db()
    try:
        if title is not None:
            db.execute(
                "UPDATE conversations SET title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (title, conv_id),
            )
        if messages is not None:
            db.execute(
                "UPDATE conversations SET messages = ?, message_count = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (json.dumps(messages, ensure_ascii=False), len(messages), conv_id),
            )
        db.commit()
        return "ok"
    finally:
        db.close()


def conversation_delete(conv_id: int) -> str:
    """Delete a conversation."""
    db = _get_db()
    try:
        result = db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        db.commit()
        if result.rowcount:
            return "deleted"
        return "not_found"
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  GLOBAL SEARCH
# ══════════════════════════════════════════════════

def global_search(query: str, limit: int = 30) -> dict:
    """Search across conversations, notes, and memories."""
    db = _get_db()
    try:
        words = query.lower().split()
        if not words:
            return {"conversations": [], "notes": [], "memories": []}

        # Search conversations (title + messages content)
        conv_conditions = " OR ".join(
            ["LOWER(title) LIKE ? OR LOWER(messages) LIKE ?" for _ in words]
        )
        conv_params = []
        for w in words:
            conv_params.extend([f"%{w}%", f"%{w}%"])
        convs = db.execute(
            f"SELECT id, title, message_count, updated_at FROM conversations "
            f"WHERE {conv_conditions} ORDER BY updated_at DESC LIMIT ?",
            conv_params + [limit],
        ).fetchall()

        # Search notes (title + content)
        note_conditions = " OR ".join(
            ["LOWER(title) LIKE ? OR LOWER(content) LIKE ?" for _ in words]
        )
        note_params = []
        for w in words:
            note_params.extend([f"%{w}%", f"%{w}%"])
        notes = db.execute(
            f"SELECT id, title, category, created_at FROM notes "
            f"WHERE {note_conditions} ORDER BY updated_at DESC LIMIT ?",
            note_params + [limit],
        ).fetchall()

        # Search memories
        mem_conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
        mem_params = [f"%{w}%" for w in words]
        mems = db.execute(
            f"SELECT id, content, category, importance, created_at FROM memories "
            f"WHERE {mem_conditions} ORDER BY importance DESC LIMIT ?",
            mem_params + [limit],
        ).fetchall()

        return {
            "conversations": [dict(r) for r in convs],
            "notes": [dict(r) for r in notes],
            "memories": [dict(r) for r in mems],
        }
    finally:
        db.close()


def conversation_export(conv_id: int, fmt: str = "markdown") -> str | None:
    """Export a conversation as markdown or plain text."""
    db = _get_db()
    try:
        row = db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if not row:
            return None

        conv = dict(row)
        messages = json.loads(conv["messages"])
        title = conv["title"]
        created = conv["created_at"]

        if fmt == "markdown":
            lines = [f"# {title}", f"*Erstellt: {created}*", ""]
            for msg in messages:
                role = "**Du**" if msg.get("role") == "user" else "**Lexa**"
                lines.append(f"{role}: {msg.get('content', '')}")
                lines.append("")
            return "\n".join(lines)
        else:
            lines = [f"{title}", f"Erstellt: {created}", "=" * 40, ""]
            for msg in messages:
                role = "Du" if msg.get("role") == "user" else "Lexa"
                lines.append(f"[{role}] {msg.get('content', '')}")
                lines.append("")
            return "\n".join(lines)
    finally:
        db.close()


# ══════════════════════════════════════════════════
#  ZUSAMMENFASSUNG (Summary)
# ══════════════════════════════════════════════════

def summarize_text(text: str) -> str:
    """Summarize text using the AI engine."""
    from backend.ai_engine import _chat_groq, _chat_ollama

    messages = [
        {"role": "system", "content": "Du bist ein Zusammenfassungs-Assistent. Fasse den folgenden Text in maximal 3-5 Sätzen auf Deutsch zusammen. Sei präzise und halte die wichtigsten Punkte fest."},
        {"role": "user", "content": text},
    ]
    reply = _chat_groq(messages)
    if not reply:
        reply = _chat_ollama(messages)
    return reply or "Zusammenfassung nicht möglich — KI nicht erreichbar."


# ══════════════════════════════════════════════════
#  STATISTIKEN
# ══════════════════════════════════════════════════

def get_memory_stats() -> dict:
    """Get memory database statistics."""
    db = _get_db()
    try:
        notes = db.execute("SELECT COUNT(*) as c FROM notes").fetchone()["c"]
        memories = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        interactions = db.execute("SELECT COUNT(*) as c FROM interactions").fetchone()["c"]
        routines = db.execute("SELECT COUNT(*) as c FROM routines").fetchone()["c"]
        conversations = db.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
        return {
            "notes": notes,
            "memories": memories,
            "interactions": interactions,
            "routines": routines,
            "conversations": conversations,
            "db_path": str(DB_PATH),
        }
    finally:
        db.close()
