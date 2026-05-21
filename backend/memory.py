"""Lexa AI — SQLite Memory System (Production-Grade)
Langzeitgedächtnis: Notizen, User-Profil, Kontext-Erinnerungen, Auto-Learning

Improvements over v0.20.0:
- Removed db.close() from individual functions (thread-local connections persist)
- Thread-safe _auto_remember_counter with lock
- Connection timeout (10s) to avoid hanging on locked DB
- FTS5 fallback to LIKE search on failure
- Additional indexes for performance
- Foreign key enforcement
- Column constraints (importance CHECK, title NOT NULL)
- Context manager for DB error handling
- Pagination support (limit/offset)
- Validated table/column names in backup restore
- Type hints on all public functions
- Consistent function aliases for backward compat

v0.21.0 — Intelligent Memory Management:
- _extract_search_terms(): German stop-word removal, max 5 keywords
- _score_memory_relevance(): keyword + importance weighted scoring
- search_memory(): uses smart term extraction + relevance scoring
- auto_remember(): proper JSON parsing, 20+ preference patterns, fact extraction
- add_memory(): smarter dedup (normalized key, 120-char prefix, 80% similarity)
"""

import os
import sqlite3
import logging
import json
import re
import math
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Any, Optional

from backend.i18n import t

logger = logging.getLogger("lexa.memory")

import threading as _threading

_auto_remember_counter: int = 0
_tables_ready: bool = False
_tables_lock = _threading.Lock()

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
DB_PATH = Path(_DATA_DIR) / "lexa_memory.db"

MEMORY_TYPES: tuple[str, ...] = (
    "working",
    "episodic",
    "semantic",
    "procedural",
    "preference",
    "system",
)
MEMORY_GRAPH_MAX_NODES = 220
MEMORY_GRAPH_KEYWORD_NODES = 24
MEMORY_GRAPH_MAX_LINKS = 420
_VALID_MEMORY_TYPES: frozenset[str] = frozenset(MEMORY_TYPES)
_MEMORY_TYPE_CATEGORY_MAP: dict[str, str] = {
    "preference": "preference",
    "preferences": "preference",
    "explicit": "working",
    "task": "working",
    "todo": "working",
    "reminder": "working",
    "working": "working",
    "scratch": "working",
    "session": "working",
    "event": "episodic",
    "meeting": "episodic",
    "appointment": "episodic",
    "calendar": "episodic",
    "routine": "procedural",
    "procedure": "procedural",
    "workflow": "procedural",
    "howto": "procedural",
    "command": "procedural",
    "system": "system",
    "config": "system",
    "diagnostic": "system",
    "fact": "semantic",
    "identity": "semantic",
    "person": "semantic",
}
_MEMORY_SYSTEM_PREFIXES: tuple[str, ...] = (
    "system:",
    "lexa:",
    "config:",
    "configuration:",
    "diagnostic:",
)
_MEMORY_WORKING_PREFIXES: tuple[str, ...] = (
    "merkzettel:",
    "todo:",
    "aufgabe:",
    "notiz:",
    "scratch:",
)
_MEMORY_EPISODIC_MARKERS: tuple[str, ...] = (
    "termin:",
    "meeting:",
    "event:",
    "gestern",
    "heute",
    "morgen",
)
_MEMORY_PROCEDURAL_MARKERS: tuple[str, ...] = (
    "der befehl ",
    "befehl ",
    "command ",
    "workflow:",
    "routine:",
    "how to ",
    "wie man ",
    "schritt ",
)
_MEMORY_PREFERENCE_MARKERS: tuple[str, ...] = (
    "praeferenz:",
    "präferenz:",
    "lieblings",
    "ich mag ",
    "ich liebe ",
    "interesse",
    "hobby",
)
_MEMORY_RANKING_WEIGHTS: dict[str, float] = {
    "lexical_score": 0.34,
    "semantic_score": 0.24,
    "recency_score": 0.10,
    "importance_score": 0.14,
    "access_score": 0.06,
    "memory_type_weight": 0.12,
}
_MEMORY_ACCESS_THROTTLE_SECONDS = 30


# ══════════════════════════════════════════════════
#  GERMAN STOP WORDS & INTELLIGENT TEXT PROCESSING
# ══════════════════════════════════════════════════

_GERMAN_STOP_WORDS: frozenset = frozenset({
    # Articles & pronouns
    "der", "die", "das", "ein", "eine", "den", "dem", "des",
    "ich", "du", "er", "sie", "es", "wir", "ihr", "mir", "mich",
    "dir", "dich", "sich", "mein", "dein", "sein", "unser", "euer",
    # Verbs (common)
    "ist", "sind", "war", "hat", "haben", "wird", "werden",
    "kannst", "könntest", "würdest", "soll", "kann", "möchte",
    "will", "lass", "mach",
    # Conjunctions & particles
    "und", "oder", "nicht", "kein", "keine", "bitte", "mal",
    "auch", "noch", "ja", "nein", "doch", "nur", "schon", "sehr",
    # Greetings & addressing
    "hey", "lexa", "hallo", "guten", "morgen", "tag", "abend",
    # Question words
    "was", "wie", "wo", "wann", "warum", "wer", "welche", "welcher", "welches",
    # Prepositions
    "im", "am", "um", "zu", "von", "mit", "für", "auf", "in", "an",
    "bei", "nach", "über", "unter", "vor", "hinter", "zwischen",
    "durch", "gegen", "ohne", "bis", "seit", "während",
})
_ENGLISH_STOP_WORDS: frozenset = frozenset({
    "the", "a", "an", "and", "or", "not", "no", "yes", "to", "of", "for",
    "with", "without", "in", "on", "at", "by", "from", "about", "into",
    "over", "under", "between", "through", "since", "during", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "can", "could", "should", "would", "will", "just", "please", "my",
    "your", "his", "her", "their", "our", "me", "you", "we", "they", "it",
    "this", "that", "these", "those", "what", "when", "where", "why", "how",
})
_MEMORY_STOP_WORDS: frozenset = _GERMAN_STOP_WORDS | _ENGLISH_STOP_WORDS
_MEMORY_QUERY_TYPE_MARKERS: dict[str, tuple[str, ...]] = {
    "preference": (
        "preference", "preferences", "prefer", "favorite", "favourite",
        "personality", "personalization", "like", "love", "mag", "liebe",
        "lieblings", "praeferenz", "präferenz", "vorliebe", "geschmack",
    ),
    "procedural": (
        "how", "workflow", "tool", "command", "steps", "process", "procedure",
        "use", "wie", "befehl", "ablauf", "schritte", "anleitung", "nutze",
    ),
    "episodic": (
        "meeting", "event", "history", "happened", "timeline", "appointment",
        "termin", "ereignis", "verlauf", "wann", "gestern", "heute", "morgen",
    ),
    "semantic": (
        "fact", "facts", "know", "knowledge", "explain", "what", "fakt",
        "wissen", "erkläre", "erklaere",
    ),
    "system": (
        "system", "config", "configuration", "diagnostic", "diagnostics",
        "lexa", "provider", "konfiguration", "diagnose",
    ),
    "working": (
        "todo", "task", "remember", "note", "scratch", "aufgabe", "merkzettel",
        "notiz", "erinner",
    ),
}


def _escape_fts5_query(terms: list[str]) -> str:
    """Escape search terms for safe FTS5 MATCH usage.

    Each term is wrapped in double quotes so FTS5 treats it as a literal phrase,
    preventing operators like *, NEAR, NOT, OR, AND from being interpreted.
    Internal double quotes are stripped to prevent query syntax injection.
    Returns terms joined with OR.
    """
    escaped = []
    for term in terms:
        safe = term.replace('"', '')
        if safe:
            escaped.append(f'"{safe}"')
    return " OR ".join(escaped) if escaped else ""


def _extract_search_terms(query: str) -> list[str]:
    """Extract meaningful search keywords from a German query.

    - Removes German stop words
    - Removes words shorter than 3 characters
    - Returns max 5 most meaningful keywords (longest first, as longer words
      tend to be more specific/meaningful)
    """
    words = query.lower().split()
    keywords = []
    for w in words:
        # Strip punctuation from edges
        w = w.strip(".,;:!?\"'()[]{}/-")
        if len(w) < 3:
            continue
        if w in _MEMORY_STOP_WORDS:
            continue
        if w not in keywords:  # deduplicate
            keywords.append(w)
    # Sort by length descending (longer = more specific), take max 5
    keywords.sort(key=len, reverse=True)
    return keywords[:5]


def _score_memory_relevance(memory_content: str, query_keywords: list[str],
                            importance: int = 5) -> float:
    """Score how relevant a memory is to the given search keywords.

    Returns a float between 0.0 and 1.0.
    - Counts how many keywords appear in the memory content
    - Weights by the memory's importance field (1-10)
    - Higher score = more relevant
    """
    if not query_keywords:
        return 0.0
    content_lower = memory_content.lower()
    matches = sum(1 for kw in query_keywords if kw in content_lower)
    if matches == 0:
        return 0.0
    # keyword_ratio: fraction of keywords that matched (0-1)
    keyword_ratio = matches / len(query_keywords)
    # importance_factor: normalized importance (0.1 - 1.0)
    importance_factor = max(0.1, importance / 10.0)
    # Combined score: 70% keyword match, 30% importance
    score = 0.7 * keyword_ratio + 0.3 * importance_factor
    return min(1.0, score)


def _score_memory_lexical(memory_content: str, query_keywords: list[str], query: str = "") -> float:
    """Score direct lexical overlap without importance or recency weighting."""
    if not query_keywords:
        return 0.0
    content_lower = str(memory_content or "").lower()
    matches = sum(1 for kw in query_keywords if kw in content_lower)
    if matches == 0:
        return 0.0
    score = matches / len(query_keywords)
    query_lower = str(query or "").strip().lower()
    if query_lower and len(query_lower) >= 8 and query_lower in content_lower:
        score = max(score, 1.0)
    return min(1.0, score)


def _parse_memory_timestamp(value: Any) -> Optional[datetime]:
    """Parse SQLite localtime strings for deterministic ranking."""
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _score_memory_recency(created_at: Any) -> float:
    """Score recent memories higher while keeping old memories discoverable."""
    created = _parse_memory_timestamp(created_at)
    if created is None:
        return 0.0
    age_days = max(0.0, (datetime.now() - created).total_seconds() / 86400.0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.85
    if age_days <= 30:
        return 0.60
    if age_days <= 90:
        return 0.35
    if age_days <= 365:
        return 0.15
    return 0.05


def _score_memory_importance(importance: Any) -> float:
    try:
        value = int(importance)
    except (TypeError, ValueError):
        value = 5
    return max(0.1, min(1.0, value / 10.0))


def _score_memory_access(access_count: Any) -> float:
    try:
        count = max(0, int(access_count or 0))
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return 0.0
    return min(1.0, math.log1p(count) / math.log1p(20))


def _detect_memory_query_types(query: str, keywords: list[str]) -> set[str]:
    query_lower = str(query or "").lower()
    keyword_text = " ".join(keywords).lower()
    detected: set[str] = set()
    for memory_type, markers in _MEMORY_QUERY_TYPE_MARKERS.items():
        if any(marker in query_lower or marker in keyword_text for marker in markers):
            detected.add(memory_type)
    return detected


def _score_memory_type_weight(memory_type: str, query_types: set[str]) -> float:
    normalized = normalize_memory_type(memory_type) or "semantic"
    if normalized in query_types:
        return 1.0
    if normalized == "system":
        return 0.20 if "system" in query_types else 0.05
    if query_types:
        return 0.35
    return 0.50 if normalized != "system" else 0.10


def _rank_memory_results(
    memories: list[dict],
    query: str,
    keywords: list[str],
    *,
    include_ranking: bool = False,
) -> list[dict]:
    """Apply Memory Ranking v1 to memory result dictionaries."""
    query_types = _detect_memory_query_types(query, keywords)
    ranked: list[dict] = []
    for mem in memories:
        lexical_score = _score_memory_lexical(mem.get("content", ""), keywords, query)
        semantic_score = max(0.0, min(1.0, float(mem.get("_semantic_score", 0.0) or 0.0)))
        recency_score = _score_memory_recency(mem.get("created_at"))
        importance_score = _score_memory_importance(mem.get("importance", 5))
        access_score = _score_memory_access(mem.get("access_count", 0))
        memory_type_weight = _score_memory_type_weight(mem.get("memory_type", "semantic"), query_types)
        final_score = (
            _MEMORY_RANKING_WEIGHTS["lexical_score"] * lexical_score
            + _MEMORY_RANKING_WEIGHTS["semantic_score"] * semantic_score
            + _MEMORY_RANKING_WEIGHTS["recency_score"] * recency_score
            + _MEMORY_RANKING_WEIGHTS["importance_score"] * importance_score
            + _MEMORY_RANKING_WEIGHTS["access_score"] * access_score
            + _MEMORY_RANKING_WEIGHTS["memory_type_weight"] * memory_type_weight
        )
        mem["_final_score"] = round(final_score, 6)
        if include_ranking:
            mem["_ranking"] = {
                "lexical_score": round(lexical_score, 6),
                "semantic_score": round(semantic_score, 6),
                "recency_score": round(recency_score, 6),
                "importance_score": round(importance_score, 6),
                "access_score": round(access_score, 6),
                "memory_type_weight": round(memory_type_weight, 6),
                "final_score": round(final_score, 6),
            }
        ranked.append(mem)
    ranked.sort(
        key=lambda m: (
            m.get("_final_score", 0.0),
            _score_memory_importance(m.get("importance", 5)),
            str(m.get("created_at") or ""),
        ),
        reverse=True,
    )
    return ranked


def _track_memory_access(db: sqlite3.Connection, memory_ids: list[int]) -> None:
    """Track returned-memory access with a short write throttle."""
    ids = sorted({int(memory_id) for memory_id in memory_ids if memory_id})
    if not ids:
        return
    placeholders = ", ".join(["?"] * len(ids))
    db.execute(
        f"""UPDATE memories
            SET access_count = COALESCE(access_count, 0) + 1,
                last_accessed_at = datetime('now', 'localtime')
            WHERE id IN ({placeholders})
              AND (
                last_accessed_at IS NULL
                OR last_accessed_at < datetime('now', '-' || ? || ' seconds', 'localtime')
              )""",
        ids + [_MEMORY_ACCESS_THROTTLE_SECONDS],
    )
    db.commit()


def _finalize_memory_results(
    db: sqlite3.Connection,
    memories: list[dict],
    *,
    include_ranking: bool = False,
    expose_id: bool = False,
    track_access: bool = True,
) -> list[dict]:
    """Strip internal ranking fields and optionally track returned memories."""
    returned = memories
    if track_access:
        _track_memory_access(db, [m.get("id") for m in returned if m.get("id")])
    finalized: list[dict] = []
    for mem in returned:
        item = dict(mem)
        if not expose_id:
            item.pop("id", None)
        for key in (
            "_final_score",
            "_semantic_score",
            "source",
            "access_count",
            "last_accessed_at",
        ):
            item.pop(key, None)
        if not include_ranking:
            item.pop("_ranking", None)
        finalized.append(item)
    return finalized


def _normalize_for_dedup(content: str) -> str:
    """Normalize content string for deduplication comparison.

    Lowercase, strip, collapse whitespace, take first 120 chars.
    """
    normalized = content.strip().lower()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized[:120]


def _similarity_ratio(a: str, b: str) -> float:
    """Compute a similarity ratio between two strings.

    Returns 0.0 to 1.0.
    Strategy:
    1. Check if the shorter string is a substring/prefix of the longer one
    2. Use word-level overlap (Dice coefficient) when there are multiple words
    3. Fall back to character-level prefix overlap for single-word strings
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)

    # If shorter string is fully contained in longer, high similarity
    if shorter in longer:
        # Scale by length ratio — if shorter is 80%+ of longer's length, very similar
        return len(shorter) / len(longer)

    words_a = set(a.split())
    words_b = set(b.split())

    # Word-level: use Dice coefficient (2*overlap / total) — more forgiving than Jaccard
    if words_a and words_b:
        overlap = len(words_a & words_b)
        total = len(words_a) + len(words_b)
        if total > 0:
            return (2 * overlap) / total

    # Single-word: character-level common prefix
    common = 0
    for ca, cb in zip(shorter, longer):
        if ca == cb:
            common += 1
        else:
            break
    return common / len(longer) if len(longer) > 0 else 0.0


def normalize_memory_type(memory_type: str | None) -> str | None:
    """Return a valid canonical memory type, or None for unknown input."""
    value = str(memory_type or "").strip().lower()
    return value if value in _VALID_MEMORY_TYPES else None


def classify_memory_type(content: str, category: str = "fact", source: str = "user") -> str:
    """Classify a memory into Lexa's explicit memory type taxonomy.

    The legacy category remains the user-facing/domain category. This helper adds
    a deterministic type layer used for search, migration, and future UI filters.
    """
    source_key = str(source or "").strip().lower()
    category_key = str(category or "").strip().lower()
    category_type = _MEMORY_TYPE_CATEGORY_MAP.get(category_key)
    text = str(content or "").strip().lower()

    if source_key == "system":
        return "system"
    if category_type and category_type != "semantic":
        return category_type
    if any(text.startswith(prefix) for prefix in _MEMORY_SYSTEM_PREFIXES):
        return "system"
    if any(text.startswith(prefix) for prefix in _MEMORY_WORKING_PREFIXES):
        return "working"
    if any(marker in text for marker in _MEMORY_PREFERENCE_MARKERS):
        return "preference"
    if any(marker in text for marker in _MEMORY_PROCEDURAL_MARKERS):
        return "procedural"
    if (
        any(marker in text for marker in _MEMORY_EPISODIC_MARKERS)
        or re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text)
    ):
        return "episodic"
    if category_type:
        return category_type
    return "semantic"


# ══════════════════════════════════════════════════
#  CONNECTION MANAGEMENT
# ══════════════════════════════════════════════════

_thread_local = _threading.local()

# Whitelist of valid table names for backup/restore operations
_VALID_TABLES = frozenset({
    "notes", "memories", "user_profile", "interactions", "routines",
    "snippets", "conversations", "clipboard_entries", "session_state", "timers",
    "conversation_summaries",
})

# Whitelist of valid column names per table (for restore validation)
_VALID_COLUMNS = {
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


def _get_db() -> sqlite3.Connection:
    """Get database connection with auto-init. Reuses connection per thread."""
    db = getattr(_thread_local, "db", None)
    if db is not None:
        try:
            db.execute("SELECT 1")
            return db
        except Exception:
            # Connection broken, recreate
            try:
                db.close()
            except Exception:
                pass
            _thread_local.db = None

    db = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    db.row_factory = sqlite3.Row
    # Performance PRAGMAs — WAL mode for concurrent reads, reduced sync for speed
    wal_result = db.execute("PRAGMA journal_mode=WAL").fetchone()
    if wal_result and wal_result[0].lower() != "wal":
        logger.warning(
            f"WAL mode not enabled — journal_mode is '{wal_result[0]}'. "
            "Performance may be degraded. This can happen on network drives."
        )
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")  # 64MB cache
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
    db.execute("PRAGMA foreign_keys=ON")
    _init_tables(db)
    _thread_local.db = db
    return db


@contextmanager
def _db_session():
    """Context manager that yields a DB connection and handles errors.

    Usage:
        with _db_session() as db:
            db.execute(...)
            db.commit()

    The connection is NOT closed — it persists in thread-local storage.
    On exception, a rollback is attempted before re-raising.
    """
    db = _get_db()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise


def close_db() -> None:
    """Explicitly close the thread-local DB connection (call on shutdown only)."""
    db = getattr(_thread_local, "db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
        _thread_local.db = None


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


def _init_tables(db: sqlite3.Connection) -> None:
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

    # Rebuild FTS index once on first init (thread-safe)
    global _tables_ready
    with _tables_lock:
        if not _tables_ready:
            _tables_ready = True
            _rebuild_fts(db)


def _rebuild_fts(db: Optional[sqlite3.Connection] = None) -> None:
    """Rebuild the FTS5 indexes from existing data (internal)."""
    if db is None:
        db = _get_db()
    try:
        db.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
        db.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        db.commit()
        logger.info("FTS indexes rebuilt")
    except Exception as e:
        logger.warning(f"FTS rebuild skipped: {e}")


def rebuild_fts() -> str:
    """Rebuild FTS indexes from existing data (run once after upgrade)."""
    db = _get_db()
    try:
        db.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")
        db.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        db.commit()
        return "FTS indexes rebuilt."
    except Exception as e:
        logger.warning(f"FTS rebuild failed: {e}")
        return f"FTS rebuild failed: {e}"


def full_text_search(query: str, limit: int = 20) -> dict:
    """Search across notes and memories using FTS5.
    Falls back to LIKE search when FTS5 is unavailable or fails.
    """
    db = _get_db()
    try:
        # Escape user query for FTS5 safety
        terms = _extract_search_terms(query)
        if not terms:
            terms = [w.strip(".,;:!?\"'()[]{}/-") for w in query.split() if len(w.strip(".,;:!?\"'()[]{}/-")) >= 2]
        fts_query = _escape_fts5_query(terms)
        if not fts_query:
            return _like_search_all(db, query, limit)
        notes = [dict(r) for r in db.execute(
            "SELECT n.* FROM notes n JOIN notes_fts f ON n.id = f.rowid WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, limit)
        ).fetchall()]
        memories = [dict(r) for r in db.execute(
            """SELECT m.id, m.content, m.category, m.memory_type, m.importance, m.source,
                      m.created_at, m.access_count, m.last_accessed_at
               FROM memories m JOIN memories_fts f ON m.id = f.rowid
               WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?""",
            (fts_query, limit)
        ).fetchall()]
        memories = _rank_memory_results(memories, query, terms)
        memories = _finalize_memory_results(db, memories[:limit], expose_id=True)
        return {"notes": notes, "memories": memories, "total": len(notes) + len(memories)}
    except Exception as e:
        logger.warning(f"FTS search failed, falling back to LIKE: {e}")
        # Fallback to LIKE search if FTS not available
        return _like_search_all(db, query, limit)


def _like_search_all(db: sqlite3.Connection, query: str, limit: int = 20) -> dict:
    """Fallback LIKE search for when FTS5 is unavailable."""
    words = _extract_search_terms(query)
    if not words:
        words = query.lower().split()
    if not words:
        return {"notes": [], "memories": [], "total": 0, "fallback": True}

    # Notes fallback
    note_conditions = " OR ".join(
        ["LOWER(title) LIKE ? OR LOWER(content) LIKE ?" for _ in words]
    )
    note_params: list[Any] = []
    for w in words:
        note_params.extend([f"%{w}%", f"%{w}%"])
    try:
        notes = [dict(r) for r in db.execute(
            f"SELECT * FROM notes WHERE {note_conditions} ORDER BY updated_at DESC LIMIT ?",
            note_params + [limit],
        ).fetchall()]
    except Exception:
        notes = []

    # Memories fallback
    mem_conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
    mem_params = [f"%{w}%" for w in words]
    try:
        memories = [dict(r) for r in db.execute(
            f"""SELECT id, content, category, memory_type, importance, source,
                       created_at, access_count, last_accessed_at
                FROM memories WHERE {mem_conditions} ORDER BY importance DESC LIMIT ?""",
            mem_params + [limit],
        ).fetchall()]
        memories = _rank_memory_results(memories, query, words)
        memories = _finalize_memory_results(db, memories[:limit], expose_id=True)
    except Exception:
        memories = []

    return {"notes": notes, "memories": memories, "total": len(notes) + len(memories), "fallback": True}


# ══════════════════════════════════════════════════
#  NOTIZEN
# ══════════════════════════════════════════════════

def note_create(title: str, content: str, category: str = "general") -> str:
    """Create or update a note."""
    db = _get_db()
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


def note_read(title: str = "", *, limit: Optional[int] = None, offset: int = 0) -> "dict | list":
    """Read a specific note or search by title.

    When title is empty, lists all notes. Supports optional pagination via
    limit/offset. Default: no limit (backward compat).
    """
    db = _get_db()
    if title:
        row = db.execute(
            "SELECT * FROM notes WHERE title LIKE ?",
            (f"%{title}%",),
        ).fetchone()
        if row:
            return dict(row)
        return {"error": f"Notiz '{title}' nicht gefunden."}

    if limit is not None:
        rows = db.execute(
            "SELECT id, title, category, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, title, category, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
    return [dict(r) for r in rows]


def note_list(limit: int = 200, offset: int = 0) -> list[dict]:
    """List notes with pagination.

    Args:
        limit: Maximum number of notes to return (default 200, max 1000).
        offset: Number of notes to skip (default 0).
    """
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    db = _get_db()
    rows = db.execute(
        "SELECT id, title, category, created_at FROM notes ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def note_get_by_id(note_id: int) -> "dict | None":
    """Get a single note by ID."""
    db = _get_db()
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    return dict(row) if row else None


# Alias for consistent naming
get_note = note_get_by_id


def note_update_by_id(note_id: int, title: str = "", content: str = "", category: str = "") -> bool:
    """Update a note by ID. Returns True if found and updated."""
    db = _get_db()
    updates: list[str] = []
    params: list[Any] = []
    if title:
        updates.append("title = ?")
        params.append(title[:500])
    if content:
        updates.append("content = ?")
        params.append(content[:50000])
    if category:
        updates.append("category = ?")
        params.append(category[:100])
    if not updates:
        return False
    updates.append("updated_at = datetime('now', 'localtime')")
    params.append(note_id)
    result = db.execute(f"UPDATE notes SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    return result.rowcount > 0


# Alias for consistent naming
update_note = note_update_by_id


def note_delete(title: str) -> str:
    """Delete a note by title."""
    db = _get_db()
    result = db.execute("DELETE FROM notes WHERE title = ?", (title,))
    db.commit()
    if result.rowcount:
        return f"Notiz '{title}' gelöscht."
    return f"Notiz '{title}' nicht gefunden."


# ══════════════════════════════════════════════════
#  GEDÄCHTNIS (Auto-Learning Memories)
# ══════════════════════════════════════════════════

def add_memory(
    content: str,
    category: str = "fact",
    importance: int = 5,
    source: str = "user",
    memory_type: str | None = None,
) -> str:
    """Add a memory entry with intelligent deduplication.

    Dedup strategy:
    1. Check for exact full-content match (skip if exists)
    2. Normalize content (lowercase, strip, collapse whitespace, 120 chars)
       and check for prefix match
    3. For prefix matches, require >= 80% word-level similarity to count as duplicate
    """
    # Clamp importance to valid range
    importance = max(1, min(10, importance))
    db = _get_db()

    content_stripped = content.strip()
    if not content_stripped:
        return "Leerer Inhalt."
    resolved_memory_type = (
        normalize_memory_type(memory_type)
        or classify_memory_type(content_stripped, category, source)
    )

    # 1. Exact full-content match — definite duplicate
    exact_match = db.execute(
        "SELECT id FROM memories WHERE LOWER(TRIM(content)) = ? LIMIT 1",
        (content_stripped.lower(),),
    ).fetchone()
    if exact_match:
        return "Bereits bekannt."

    # 2. Normalized prefix match with similarity check
    norm_key = _normalize_for_dedup(content_stripped)
    if norm_key:
        # Get candidates whose content starts with a similar prefix
        # Use LIKE with the first 60 chars as a broad filter, then check similarity in Python
        # Properly escape LIKE wildcards (%, _, \) using backslash as ESCAPE char
        prefix_raw = norm_key[:60]
        prefix_search = (
            prefix_raw
            .replace("\\", "\\\\")  # escape backslash first
            .replace("%", "\\%")    # escape % wildcard
            .replace("_", "\\_")    # escape _ wildcard
        )
        if len(prefix_raw) >= 10:
            candidates = db.execute(
                "SELECT id, content FROM memories WHERE LOWER(content) LIKE ? ESCAPE '\\' LIMIT 10",
                (f"{prefix_search}%",),
            ).fetchall()
            for candidate in candidates:
                # Check similarity — skip if >= 75% similar (covers prefix-overlap cases)
                sim = _similarity_ratio(
                    _normalize_for_dedup(content_stripped),
                    _normalize_for_dedup(candidate["content"])
                )
                if sim >= 0.75:
                    return "Bereits bekannt."

    db.execute(
        "INSERT INTO memories (content, category, memory_type, importance, source) VALUES (?, ?, ?, ?, ?)",
        (content_stripped, category, resolved_memory_type, importance, source),
    )
    db.commit()

    # Phase 42: Auto-embed new memory in background (non-blocking)
    try:
        from backend.config import EMBEDDING_ENABLED
        if EMBEDDING_ENABLED:
            row = db.execute(
                "SELECT id FROM memories WHERE content = ? ORDER BY id DESC LIMIT 1",
                (content_stripped,),
            ).fetchone()
            if row:
                _embed_memory_row(db, row["id"], content_stripped)
                db.commit()
    except Exception as e:
        logger.debug(f"Auto-embed skipped for new memory: {e}")

    return "Gemerkt."


def search_memory(
    query: str,
    limit: int = 5,
    *,
    include_ranking: bool = False,
    track_access: bool = True,
    expose_id: bool = False,
) -> list[dict]:
    """Search memories by content using intelligent keyword extraction.

    Uses _extract_search_terms() to filter out German stop words and extract
    meaningful keywords, then searches via FTS5 (with LIKE fallback).
    Results are re-ranked by _score_memory_relevance() for better ordering.
    """
    db = _get_db()
    keywords = _extract_search_terms(query)
    if not keywords:
        # Fallback: if all words were stop words, try the original words >= 2 chars
        keywords = [w.strip(".,;:!?\"'()[]{}/-") for w in query.lower().split() if len(w.strip(".,;:!?\"'()[]{}/-")) >= 2][:3]
    if not keywords:
        return []

    # Fetch more candidates than needed, then re-rank
    fetch_limit = max(limit * 3, 15)

    # Try FTS5 first for faster search
    results: list[dict] = []
    try:
        fts_query = _escape_fts5_query(keywords)
        if not fts_query:
            raise ValueError("No safe keywords")
        rows = db.execute(
            """SELECT m.id, m.content, m.category, m.memory_type, m.importance, m.source,
                      m.created_at, m.access_count, m.last_accessed_at
               FROM memories m
               JOIN memories_fts ON m.id = memories_fts.rowid
               WHERE memories_fts MATCH ?
               LIMIT ?""",
            (fts_query, fetch_limit),
        ).fetchall()
        results = [dict(r) for r in rows]
    except Exception:
        pass

    if not results:
        # Fallback: LIKE search with extracted keywords
        conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in keywords])
        params: list[Any] = [f"%{w}%" for w in keywords]
        rows = db.execute(
            f"""SELECT id, content, category, memory_type, importance, source,
                       created_at, access_count, last_accessed_at
                FROM memories
                WHERE {conditions}
                LIMIT ?""",
            params + [fetch_limit],
        ).fetchall()
        results = [dict(r) for r in rows]

    ranked = _rank_memory_results(results, query, keywords, include_ranking=include_ranking)
    return _finalize_memory_results(
        db,
        ranked[:limit],
        include_ranking=include_ranking,
        expose_id=expose_id,
        track_access=track_access,
    )


# ══════════════════════════════════════════════════
#  SEMANTIC MEMORY SEARCH (Phase 42)
# ══════════════════════════════════════════════════

def search_memory_semantic(
    query: str,
    limit: int = 5,
    *,
    include_ranking: bool = False,
    track_access: bool = True,
) -> list[dict]:
    """Search memories using embedding-based semantic similarity.

    Flow:
    1. Embed the query text
    2. Load all memories with embeddings from DB
    3. Compute cosine similarity for each
    4. Return top-K by similarity score
    5. Falls back to keyword search if embeddings unavailable

    This finds semantically similar results that keyword search would miss:
    - "Was soll ich bestellen?" → finds "Chef mag Pizza"
    - "Browser-Problem" → finds "Chrome stuerzt ab"
    """
    try:
        from backend.embeddings import (
            EmbeddingDimensionMismatchError,
            blob_to_vector,
            cosine_similarity,
            embed_text_with_metadata,
            embedding_metadata_compatible,
            infer_embedding_metadata_from_dimension,
        )
    except ImportError:
        logger.debug("Embeddings module not available, falling back to keyword search")
        return search_memory(query, limit)

    # Embed the query
    query_result = embed_text_with_metadata(query)
    if query_result is None:
        logger.warning("Semantic memory search degraded: query embedding unavailable")
        return search_memory(query, limit)
    query_vector = query_result["vector"]
    keywords = _extract_search_terms(query)
    if not keywords:
        keywords = [w.strip(".,;:!?\"'()[]{}/-") for w in query.lower().split() if len(w.strip(".,;:!?\"'()[]{}/-")) >= 2][:3]
    query_metadata = {
        "provider": query_result["provider"],
        "model": query_result["model"],
        "dimension": query_result["dimension"],
    }

    db = _get_db()

    # Load memories with embeddings
    rows = db.execute(
        """SELECT id, content, category, memory_type, importance, source, created_at,
                  access_count, last_accessed_at, embedding, embedding_provider,
                  embedding_model, embedding_dimension
           FROM memories
           WHERE embedding IS NOT NULL"""
    ).fetchall()

    if not rows:
        # No embeddings yet — fall back to keyword search
        logger.debug("No embedded memories found, falling back to keyword search")
        return search_memory(query, limit)

    # Score each compatible memory by cosine similarity.
    scored: list[tuple[float, dict]] = []
    skipped_incompatible = 0
    skipped_corrupt = 0
    skipped_missing_metadata = 0
    for row in rows:
        mem_vector = blob_to_vector(row["embedding"])
        if mem_vector is None:
            skipped_corrupt += 1
            continue
        stored_dimension = row["embedding_dimension"]
        try:
            stored_dimension_int = int(stored_dimension or 0)
        except (TypeError, ValueError):
            stored_dimension_int = 0
        stored_metadata = None
        if (
            row["embedding_provider"]
            and row["embedding_model"]
            and stored_dimension_int == len(mem_vector)
        ):
            stored_metadata = {
                "provider": row["embedding_provider"],
                "model": row["embedding_model"],
                "dimension": stored_dimension_int,
            }
        else:
            stored_metadata = infer_embedding_metadata_from_dimension(len(mem_vector))
            if stored_metadata:
                logger.warning(
                    "Semantic memory search using inferred legacy embedding metadata: id=%s dimension=%s",
                    row["id"],
                    len(mem_vector),
                )

        if not stored_metadata:
            skipped_missing_metadata += 1
            continue
        if not embedding_metadata_compatible(query_metadata, stored_metadata):
            skipped_incompatible += 1
            continue
        try:
            sim = cosine_similarity(query_vector, mem_vector)
        except EmbeddingDimensionMismatchError:
            skipped_incompatible += 1
            continue
        scored.append((sim, {
            "id": row["id"],
            "content": row["content"],
            "category": row["category"],
            "memory_type": row["memory_type"],
            "importance": row["importance"],
            "source": row["source"],
            "created_at": row["created_at"],
            "access_count": row["access_count"],
            "last_accessed_at": row["last_accessed_at"],
            "_semantic_score": round(sim, 6),
        }))

    if skipped_corrupt or skipped_missing_metadata or skipped_incompatible:
        logger.warning(
            "Semantic memory search degraded: skipped_corrupt=%s skipped_missing_metadata=%s "
            "skipped_incompatible=%s query_provider=%s query_model=%s query_dimension=%s",
            skipped_corrupt,
            skipped_missing_metadata,
            skipped_incompatible,
            query_metadata["provider"],
            query_metadata["model"],
            query_metadata["dimension"],
        )

    if not scored:
        logger.warning("Semantic memory search degraded: no compatible embeddings, falling back to keyword search")
        return search_memory(query, limit)

    # Take top results with minimum similarity threshold
    min_similarity = 0.1
    results = []
    for sim, mem in scored:
        if sim < min_similarity:
            continue
        results.append(mem)

    # If semantic search returned too few results, supplement with keyword search
    if len(results) < limit:
        keyword_results = search_memory(
            query,
            limit - len(results),
            include_ranking=include_ranking,
            track_access=False,
            expose_id=True,
        )
        # Deduplicate by content
        existing_content = {m["content"][:80] for m in results}
        for km in keyword_results:
            if km["content"][:80] not in existing_content:
                results.append(km)
                if len(results) >= limit:
                    break

    ranked = _rank_memory_results(results, query, keywords, include_ranking=include_ranking)
    return _finalize_memory_results(
        db,
        ranked[:limit],
        include_ranking=include_ranking,
        track_access=track_access,
    )


def _embed_memory_row(db: 'sqlite3.Connection', memory_id: int, content: str) -> bool:
    """Embed a single memory row and store the vector in the DB.

    Returns True if successful, False otherwise.
    """
    try:
        from backend.embeddings import embed_text_with_metadata, vector_to_blob
        result = embed_text_with_metadata(content)
        if result:
            blob = vector_to_blob(result["vector"])
            db.execute(
                """UPDATE memories
                   SET embedding = ?,
                       embedding_provider = ?,
                       embedding_model = ?,
                       embedding_dimension = ?,
                       embedding_created_at = datetime('now', 'localtime')
                   WHERE id = ?""",
                (
                    blob,
                    result["provider"],
                    result["model"],
                    result["dimension"],
                    memory_id,
                ),
            )
            return True
    except Exception as e:
        logger.debug(f"Failed to embed memory {memory_id}: {e}")
    return False


def reindex_embeddings(batch_size: int = 50) -> dict:
    """Re-embed all memories that don't have embeddings yet.

    Processes in batches for efficiency. Returns progress info.
    """
    try:
        from backend.embeddings import embed_batch_with_metadata, vector_to_blob
    except ImportError:
        return {"error": "Embeddings module not available"}

    db = _get_db()

    # Count total and unindexed
    total = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    unindexed = db.execute(
        """SELECT COUNT(*) FROM memories
           WHERE embedding IS NULL
              OR embedding_provider IS NULL
              OR embedding_model IS NULL
              OR embedding_dimension IS NULL"""
    ).fetchone()[0]

    if unindexed == 0:
        return {"total": total, "indexed": total, "newly_indexed": 0, "status": "complete"}

    # Process in batches
    newly_indexed = 0
    offset = 0

    while True:
        rows = db.execute(
            """SELECT id, content FROM memories
               WHERE embedding IS NULL
                  OR embedding_provider IS NULL
                  OR embedding_model IS NULL
                  OR embedding_dimension IS NULL
               LIMIT ? OFFSET ?""",
            (batch_size, 0),  # Always offset 0 since we UPDATE them
        ).fetchall()

        if not rows:
            break

        texts = [row["content"] for row in rows]
        ids = [row["id"] for row in rows]

        vectors = embed_batch_with_metadata(texts)

        for row_id, result in zip(ids, vectors):
            if result:
                blob = vector_to_blob(result["vector"])
                db.execute(
                    """UPDATE memories
                       SET embedding = ?,
                           embedding_provider = ?,
                           embedding_model = ?,
                           embedding_dimension = ?,
                           embedding_created_at = datetime('now', 'localtime')
                       WHERE id = ?""",
                    (
                        blob,
                        result["provider"],
                        result["model"],
                        result["dimension"],
                        row_id,
                    ),
                )
                newly_indexed += 1

        db.commit()
        offset += batch_size
        logger.info(f"Embedding reindex: {newly_indexed}/{unindexed} done")

    indexed_now = db.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL").fetchone()[0]

    return {
        "total": total,
        "indexed": indexed_now,
        "newly_indexed": newly_indexed,
        "status": "complete",
    }


def get_embedding_stats() -> dict:
    """Return statistics about memory embeddings."""
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    indexed = db.execute("SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL").fetchone()[0]
    metadata_missing = db.execute(
        """SELECT COUNT(*) FROM memories
           WHERE embedding IS NOT NULL
             AND (
                embedding_provider IS NULL
                OR embedding_model IS NULL
                OR embedding_dimension IS NULL
             )"""
    ).fetchone()[0]
    by_provider = {
        row["provider"]: row["c"]
        for row in db.execute(
            """SELECT COALESCE(embedding_provider, 'unknown') AS provider, COUNT(*) AS c
               FROM memories
               WHERE embedding IS NOT NULL
               GROUP BY COALESCE(embedding_provider, 'unknown')"""
        ).fetchall()
    }
    by_dimension = {
        str(row["dimension"]): row["c"]
        for row in db.execute(
            """SELECT COALESCE(CAST(embedding_dimension AS TEXT), 'unknown') AS dimension, COUNT(*) AS c
               FROM memories
               WHERE embedding IS NOT NULL
               GROUP BY COALESCE(CAST(embedding_dimension AS TEXT), 'unknown')"""
        ).fetchall()
    }

    try:
        from backend.embeddings import get_embedding_status
        provider_info = get_embedding_status()
    except ImportError:
        provider_info = {"provider": "unavailable"}

    return {
        "total_memories": total,
        "indexed_memories": indexed,
        "unindexed_memories": total - indexed,
        "embedding_metadata_missing": metadata_missing,
        "embedding_provider_counts": by_provider,
        "embedding_dimension_counts": by_dimension,
        "coverage_pct": round(indexed / total * 100, 1) if total > 0 else 0.0,
        **provider_info,
    }


def auto_remember(user_msg: str, ai_reply: str) -> None:
    """Intelligently extract and save important facts from conversations.

    Improvements over v0.20.0:
    - Proper JSON parsing for action detection
    - 20+ preference/identity patterns with categorized extraction
    - Fact extraction from AI responses (identity facts)
    - Structured memory content instead of raw "User sagte: ..."
    - Explicit remember commands get high importance (9)
    """
    global _auto_remember_counter
    db = _get_db()
    try:
        # --- Detect action in AI reply (proper JSON parsing) ---
        has_action = 0
        try:
            parsed_reply = json.loads(ai_reply)
            if isinstance(parsed_reply, dict) and "action" in parsed_reply:
                has_action = 1
        except (json.JSONDecodeError, TypeError):
            # Fallback: check for action pattern in text (e.g. markdown-wrapped JSON)
            if '"action"' in ai_reply:
                has_action = 1

        db.execute(
            "INSERT INTO interactions (user_message, ai_reply, had_action) VALUES (?, ?, ?)",
            (user_msg, ai_reply[:1000], has_action),
        )

        msg_lower = user_msg.lower().strip()
        saved_something = False

        # --- HIGH PRIORITY: Explicit "remember this" commands (importance 9) ---
        explicit_remember_patterns = [
            "erinnere dich", "merke dir", "vergiss nicht", "denk daran",
            "behalte", "speicher", "merk dir",
        ]
        if any(p in msg_lower for p in explicit_remember_patterns) and len(user_msg) < 300:
            # Extract what to remember (strip the command prefix)
            content = user_msg
            for p in explicit_remember_patterns:
                idx = msg_lower.find(p)
                if idx >= 0:
                    content = user_msg[idx + len(p):]
                    # Strip leading punctuation, whitespace, and the word "dass"
                    content = re.sub(r"^[\s,.:!]+", "", content)
                    content = re.sub(r"^dass\s+", "", content, flags=re.IGNORECASE)
                    content = content.strip()
                    break
            if content and len(content) > 3:
                add_memory(f"Merkzettel: {content}", category="explicit", importance=9, source="auto")
                saved_something = True

        # --- IDENTITY EXTRACTION from user message (importance 8-9) ---
        if not saved_something and len(user_msg) < 300:
            identity_extractions = [
                # (pattern_in_msg, regex_to_extract_value, label, importance)
                ("ich heiße", r"ich heiße\s+(.+?)(?:\.|,|!|$)", "Name", 9),
                ("mein name ist", r"mein name ist\s+(.+?)(?:\.|,|!|$)", "Name", 9),
                ("ich bin der", r"ich bin (?:der|die)\s+(.+?)(?:\.|,|!|$)", "Name", 9),
                ("ich arbeite bei", r"ich arbeite bei\s+(.+?)(?:\.|,|!|$)", "Arbeitgeber", 8),
                ("ich arbeite als", r"ich arbeite als\s+(.+?)(?:\.|,|!|$)", "Beruf", 8),
                ("ich arbeite mit", r"ich arbeite mit\s+(.+?)(?:\.|,|!|$)", "Tools", 7),
                ("ich bin von beruf", r"ich bin von beruf\s+(.+?)(?:\.|,|!|$)", "Beruf", 8),
                ("ich wohne in", r"ich wohne in\s+(.+?)(?:\.|,|!|$)", "Wohnort", 8),
                ("ich lebe in", r"ich lebe in\s+(.+?)(?:\.|,|!|$)", "Wohnort", 8),
                ("ich komme aus", r"ich komme aus\s+(.+?)(?:\.|,|!|$)", "Herkunft", 7),
                ("ich bin aus", r"ich bin aus\s+(.+?)(?:\.|,|!|$)", "Herkunft", 7),
                ("ich spreche", r"ich spreche\s+(.+?)(?:\.|,|!|$)", "Sprache", 7),
                ("meine sprache", r"meine sprache(?:n)?\s+(?:ist|sind)\s+(.+?)(?:\.|,|!|$)", "Sprache", 7),
                ("ich benutze", r"ich benutze\s+(.+?)(?:\.|,|!|$)", "Tool", 6),
                ("ich nutze", r"ich nutze\s+(.+?)(?:\.|,|!|$)", "Tool", 6),
            ]
            for pattern, regex, label, imp in identity_extractions:
                if pattern in msg_lower:
                    match = re.search(regex, msg_lower, re.IGNORECASE)
                    if match:
                        value = match.group(1).strip()
                        if value and len(value) > 1:
                            # Use original casing from user_msg
                            value_clean = user_msg[match.start(1):match.end(1)].strip()
                            add_memory(
                                f"{label}: {value_clean}",
                                category="identity", importance=imp, source="auto"
                            )
                            saved_something = True
                    break  # Only match first identity pattern

        # --- PREFERENCE EXTRACTION (importance 6-7) ---
        if not saved_something and len(user_msg) < 300:
            preference_patterns = [
                # (pattern, regex, label, importance)
                ("ich mag", r"ich mag\s+(.+?)(?:\.|,|!|$)", "Präferenz: mag", 6),
                ("ich liebe", r"ich liebe\s+(.+?)(?:\.|,|!|$)", "Präferenz: liebt", 7),
                ("ich hasse", r"ich hasse\s+(.+?)(?:\.|,|!|$)", "Präferenz: hasst", 6),
                ("ich bevorzuge", r"ich bevorzuge\s+(.+?)(?:\.|,|!|$)", "Präferenz: bevorzugt", 6),
                ("mein lieblings", r"mein(?:e)? lieblings(\w+)\s+(?:ist|sind)\s+(.+?)(?:\.|,|!|$)", None, 7),
                ("ich bin fan von", r"ich bin fan von\s+(.+?)(?:\.|,|!|$)", "Präferenz: Fan von", 6),
                ("am liebsten", r"am liebsten\s+(.+?)(?:\.|,|!|$)", "Präferenz: am liebsten", 6),
                ("ich interessiere mich", r"ich interessiere mich für\s+(.+?)(?:\.|,|!|$)", "Interesse", 6),
                ("mein hobby", r"mein(?:e)? hobbys?\s+(?:ist|sind)\s+(.+?)(?:\.|,|!|$)", "Hobby", 6),
            ]
            for pattern, regex, label, imp in preference_patterns:
                if pattern in msg_lower:
                    match = re.search(regex, msg_lower, re.IGNORECASE)
                    if match:
                        if label is None:
                            # Special handling for "mein Lieblings..."
                            thing = match.group(1).strip()
                            value = match.group(2).strip()
                            value_orig = user_msg[match.start(2):match.end(2)].strip()
                            add_memory(
                                f"Lieblings{thing}: {value_orig}",
                                category="preference", importance=imp, source="auto"
                            )
                        else:
                            value = match.group(1).strip()
                            if value and len(value) > 1:
                                value_orig = user_msg[match.start(1):match.end(1)].strip()
                                add_memory(
                                    f"{label} {value_orig}",
                                    category="preference", importance=imp, source="auto"
                                )
                        saved_something = True
                    break  # Only match first preference pattern

        # NOTE: AI-reply identity extraction was removed — the AI can hallucinate
        # facts like "dein Name ist Max" and those would persist in memory,
        # self-reinforcing in future conversations. Only user-stated facts are safe.

        db.commit()

        # Thread-safe counter increment — used for periodic maintenance
        with _tables_lock:
            _auto_remember_counter += 1
            counter_val = _auto_remember_counter

        # Keep interactions table from growing too large (last 500)
        # Only check every 50 calls — avoids expensive DELETE + subquery on every message
        if counter_val % 50 == 0:
            row_count = db.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
            if row_count > 600:  # Only DELETE when meaningfully over limit
                db.execute(
                    "DELETE FROM interactions WHERE id NOT IN "
                    "(SELECT id FROM interactions ORDER BY id DESC LIMIT 500)"
                )
                db.commit()
                logger.debug(f"Interactions cleanup: {row_count} → 500")

        # Periodically clean up old low-importance memories (every 100 calls)
        if counter_val % 100 == 0:
            db.execute(
                """DELETE FROM memories WHERE
                   importance < 4 AND
                   created_at < datetime('now', '-90 days', 'localtime')"""
            )
            db.commit()
            logger.info("Auto-Cleanup: Alte unwichtige Erinnerungen bereinigt")
    except Exception as e:
        logger.debug(f"Auto-remember failed: {e}", exc_info=True)


# ══════════════════════════════════════════════════
#  USER-PROFIL
# ══════════════════════════════════════════════════

def set_profile(key: str, value: str) -> str:
    """Set a user profile entry."""
    db = _get_db()
    db.execute(
        """INSERT INTO user_profile (key, value)
           VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET
           value=excluded.value, updated_at=datetime('now','localtime')""",
        (key, value),
    )
    db.commit()
    return f"Profil '{key}' gespeichert."


def get_user_profile() -> "str | None":
    """Get compact user profile string for AI context."""
    db = _get_db()
    rows = db.execute("SELECT key, value FROM user_profile").fetchall()
    if not rows:
        return None
    return ", ".join(f"{r['key']}={r['value']}" for r in rows)


# Alias for consistent naming
profile_get = get_user_profile
profile_set = set_profile


# ══════════════════════════════════════════════════
#  ROUTINEN / TAGESPLANUNG
# ══════════════════════════════════════════════════

def routine_create(name: str, description: str, schedule: str, actions: list[dict]) -> str:
    """Create a daily routine/plan."""
    db = _get_db()
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


def routine_list() -> list[dict]:
    """List all routines."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, name, description, schedule, enabled, last_run FROM routines ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def routine_get(name: str) -> "dict | None":
    """Get a specific routine with its actions."""
    db = _get_db()
    row = db.execute("SELECT * FROM routines WHERE name = ?", (name,)).fetchone()
    if row:
        d = dict(row)
        try:
            d["actions"] = json.loads(d["actions"])
        except (json.JSONDecodeError, TypeError):
            d["actions"] = []
        return d
    return None


def routine_delete(name: str) -> str:
    """Delete a routine."""
    db = _get_db()
    result = db.execute("DELETE FROM routines WHERE name = ?", (name,))
    db.commit()
    if result.rowcount:
        return f"Routine '{name}' gelöscht."
    return f"Routine '{name}' nicht gefunden."


def routine_toggle(name: str) -> str:
    """Enable/disable a routine."""
    db = _get_db()
    db.execute(
        "UPDATE routines SET enabled = CASE WHEN enabled=1 THEN 0 ELSE 1 END WHERE name = ?",
        (name,),
    )
    db.commit()
    return f"Routine '{name}' umgeschaltet."


# ══════════════════════════════════════════════════
#  CONVERSATIONS
# ══════════════════════════════════════════════════

def conversation_create(title: str = "Neuer Chat") -> int:
    """Create a new conversation, return its ID."""
    db = _get_db()
    cursor = db.execute(
        "INSERT INTO conversations (title) VALUES (?)", (title,)
    )
    db.commit()
    return cursor.lastrowid


def conversation_list(limit: int = 50, offset: int = 0) -> list[dict]:
    """List conversations ordered by last update, with last message preview.

    IMPORTANT: Does NOT fetch the full messages JSON blob — this is critical
    for performance when the user has many conversations with long histories.
    Instead, uses a lightweight SQL approach to extract the last message preview.

    Args:
        limit: Maximum number of conversations to return (default 50).
        offset: Number of conversations to skip (default 0).
    """
    db = _get_db()
    # Only select metadata columns — never fetch full messages for listing
    rows = db.execute(
        "SELECT id, title, message_count, created_at, updated_at, "
        "SUBSTR(messages, -500) AS tail_fragment "
        "FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        # Extract last message preview from the tail fragment
        tail = d.pop("tail_fragment", "") or ""
        last_message = ""
        last_role = ""
        try:
            # The tail fragment contains the end of the JSON array.
            # Find the last complete message object in it.
            # Look for the last {"role": pattern
            last_obj_idx = tail.rfind('{"role"')
            if last_obj_idx >= 0:
                # Try to parse from the last object to end of array
                snippet = tail[last_obj_idx:].rstrip().rstrip("]").rstrip(",").strip()
                # Ensure it ends with }
                brace_idx = snippet.rfind("}")
                if brace_idx >= 0:
                    snippet = snippet[:brace_idx + 1]
                    obj = json.loads(snippet)
                    last_message = str(obj.get("content", ""))[:80]
                    last_role = obj.get("role", "")
        except Exception:
            pass
        d["last_message"] = last_message
        d["last_role"] = last_role
        result.append(d)
    return result


def conversation_get(conv_id: int) -> "dict | None":
    """Get a conversation with its messages."""
    db = _get_db()
    row = db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if row:
        d = dict(row)
        try:
            d["messages"] = json.loads(d["messages"])
        except (json.JSONDecodeError, TypeError):
            d["messages"] = []
        return d
    return None


def conversation_update(conv_id: int, title: "str | None" = None, messages: "list | None" = None) -> str:
    """Update conversation title and/or messages."""
    db = _get_db()
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


def conversation_delete(conv_id: int) -> str:
    """Delete a conversation."""
    db = _get_db()
    result = db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    db.commit()
    if result.rowcount:
        return "deleted"
    return "not_found"


# ══════════════════════════════════════════════════
#  QUICK TEXT SNIPPETS
# ══════════════════════════════════════════════════

def snippet_create(name: str, text: str) -> str:
    """Create or update a text snippet."""
    db = _get_db()
    db.execute(
        """INSERT INTO snippets (name, text)
           VALUES (?, ?)
           ON CONFLICT(name) DO UPDATE SET text=excluded.text""",
        (name, text),
    )
    db.commit()
    return f"Snippet '{name}' gespeichert."


def snippet_list() -> list[dict]:
    """List all snippets ordered by usage."""
    db = _get_db()
    rows = db.execute(
        "SELECT name, text, use_count, created_at FROM snippets ORDER BY use_count DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def snippet_delete(name: str) -> str:
    """Delete a snippet by name."""
    db = _get_db()
    result = db.execute("DELETE FROM snippets WHERE name = ?", (name,))
    db.commit()
    return "deleted" if result.rowcount else "not_found"


def snippet_use(name: str) -> "str | None":
    """Use a snippet: increment counter and return text."""
    db = _get_db()
    db.execute("UPDATE snippets SET use_count = use_count + 1 WHERE name = ?", (name,))
    db.commit()
    row = db.execute("SELECT text FROM snippets WHERE name = ?", (name,)).fetchone()
    return row["text"] if row else None


# ══════════════════════════════════════════════════
#  GLOBAL SEARCH
# ══════════════════════════════════════════════════

def global_search(query: str, limit: int = 30, *, include_ranking: bool = False) -> dict:
    """Search across conversations, notes, and memories.

    Uses FTS5 for notes/memories when available, LIKE for conversations.
    """
    db = _get_db()
    words = _extract_search_terms(query)
    if not words:
        words = query.lower().split()
    if not words:
        return {"conversations": [], "notes": [], "memories": []}

    # Search conversations (title + messages content) — always LIKE (no FTS on JSON)
    conv_conditions = " OR ".join(
        ["LOWER(title) LIKE ? OR LOWER(messages) LIKE ?" for _ in words]
    )
    conv_params: list[Any] = []
    for w in words:
        conv_params.extend([f"%{w}%", f"%{w}%"])
    convs = db.execute(
        f"SELECT id, title, message_count, updated_at FROM conversations "
        f"WHERE {conv_conditions} ORDER BY updated_at DESC LIMIT ?",
        conv_params + [limit],
    ).fetchall()

    # Search notes — try FTS5 first
    notes_list: list[dict] = []
    try:
        fts_query = _escape_fts5_query(words)
        if not fts_query:
            raise ValueError("No safe keywords")
        notes_rows = db.execute(
            """SELECT n.id, n.title, n.category, n.created_at
               FROM notes n JOIN notes_fts f ON n.id = f.rowid
               WHERE notes_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        notes_list = [dict(r) for r in notes_rows]
    except Exception:
        # FTS5 fallback to LIKE
        note_conditions = " OR ".join(
            ["LOWER(title) LIKE ? OR LOWER(content) LIKE ?" for _ in words]
        )
        note_params: list[Any] = []
        for w in words:
            note_params.extend([f"%{w}%", f"%{w}%"])
        notes_rows = db.execute(
            f"SELECT id, title, category, created_at FROM notes "
            f"WHERE {note_conditions} ORDER BY updated_at DESC LIMIT ?",
            note_params + [limit],
        ).fetchall()
        notes_list = [dict(r) for r in notes_rows]

    # Search memories — try FTS5 first
    mems_list: list[dict] = []
    try:
        fts_query = _escape_fts5_query(words)
        if not fts_query:
            raise ValueError("No safe keywords")
        mem_rows = db.execute(
            """SELECT m.id, m.content, m.category, m.memory_type, m.importance, m.source,
                      m.created_at, m.access_count, m.last_accessed_at
               FROM memories m JOIN memories_fts f ON m.id = f.rowid
               WHERE memories_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_query, limit),
        ).fetchall()
        mems_list = [dict(r) for r in mem_rows]
    except Exception:
        # FTS5 fallback to LIKE
        mem_conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
        mem_params = [f"%{w}%" for w in words]
        mem_rows = db.execute(
            f"SELECT id, content, category, memory_type, importance, source, "
            f"created_at, access_count, last_accessed_at FROM memories "
            f"WHERE {mem_conditions} ORDER BY importance DESC LIMIT ?",
            mem_params + [limit],
        ).fetchall()
        mems_list = [dict(r) for r in mem_rows]
    mems_list = _rank_memory_results(mems_list, query, words, include_ranking=include_ranking)
    mems_list = _finalize_memory_results(
        db,
        mems_list[:limit],
        include_ranking=include_ranking,
        expose_id=True,
    )

    return {
        "conversations": [dict(r) for r in convs],
        "notes": notes_list,
        "memories": mems_list,
    }


def conversation_export(conv_id: int, fmt: str = "markdown") -> "str | None":
    """Export a conversation as markdown or plain text."""
    db = _get_db()
    row = db.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    if not row:
        return None

    conv = dict(row)
    try:
        messages = json.loads(conv["messages"])
    except (json.JSONDecodeError, TypeError):
        messages = []
    title = conv["title"]
    created = conv["created_at"]
    updated = conv.get("updated_at", "")
    msg_count = len(messages)
    total_chars = sum(len(m.get("content", "")) for m in messages)

    if fmt == "markdown":
        lines = [
            f"# {title}",
            f"*Erstellt: {created}* | *Zuletzt aktualisiert: {updated}*",
            t("memory.exportStatsMarkdown", count=msg_count, chars=total_chars),
            "",
            "---",
            "",
        ]
        for msg in messages:
            role = "**Du**" if msg.get("role") == "user" else "**Lexa**"
            lines.append(f"{role}: {msg.get('content', '')}")
            lines.append("")
        return "\n".join(lines)
    else:
        lines = [
            f"{title}",
            f"Erstellt: {created}  |  Aktualisiert: {updated}",
            t("memory.exportStats", count=msg_count, chars=total_chars),
            "=" * 40,
            "",
        ]
        for msg in messages:
            role = "Du" if msg.get("role") == "user" else "Lexa"
            lines.append(f"[{role}] {msg.get('content', '')}")
            lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════════
#  ZUSAMMENFASSUNG (Summary)
# ══════════════════════════════════════════════════

def summarize_text(text: str) -> str:
    """Summarize text using the AI engine."""
    from backend.ai_engine import _chat_with_selected_provider, _get_selected_model_meta

    messages = [
        {"role": "system", "content": "Du bist ein Zusammenfassungs-Assistent. Fasse den folgenden Text in maximal 3-5 Sätzen auf Deutsch zusammen. Sei präzise und halte die wichtigsten Punkte fest."},
        {"role": "user", "content": text},
    ]
    selected_model = _get_selected_model_meta()
    reply = _chat_with_selected_provider(messages, selected_model)
    return reply or "Zusammenfassung nicht möglich — KI nicht erreichbar."


# ══════════════════════════════════════════════════
#  STATISTIKEN & CLEANUP
# ══════════════════════════════════════════════════

def memory_cleanup(days_old: int = 90, max_importance: int = 3) -> dict:
    """Manuell alte/unwichtige Erinnerungen aufräumen."""
    db = _get_db()
    result = db.execute(
        """DELETE FROM memories WHERE
           importance <= ? AND
           created_at < datetime('now', ? || ' days', 'localtime')""",
        (max_importance, f"-{days_old}"),
    )
    db.commit()
    return {"deleted": result.rowcount, "criteria": f"importance <= {max_importance}, älter als {days_old} Tage"}


def get_memory_stats() -> dict:
    """Get memory database statistics."""
    db = _get_db()
    notes = db.execute("SELECT COUNT(*) as c FROM notes").fetchone()["c"]
    memories = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
    memory_types = {
        row["memory_type"]: row["c"]
        for row in db.execute(
            "SELECT memory_type, COUNT(*) as c FROM memories GROUP BY memory_type"
        ).fetchall()
    }
    interactions = db.execute("SELECT COUNT(*) as c FROM interactions").fetchone()["c"]
    routines = db.execute("SELECT COUNT(*) as c FROM routines").fetchone()["c"]
    conversations = db.execute("SELECT COUNT(*) as c FROM conversations").fetchone()["c"]
    clipboard = db.execute("SELECT COUNT(*) as c FROM clipboard_entries").fetchone()["c"]
    return {
        "notes": notes,
        "memories": memories,
        "memory_types": memory_types,
        "interactions": interactions,
        "routines": routines,
        "conversations": conversations,
        "clipboard_entries": clipboard,
        "db_path": str(DB_PATH),
    }


# Alias for consistent naming
memory_stats = get_memory_stats


def _graph_text(value: Any, limit: int = 120) -> str:
    """Return compact display text for read-only graph payloads."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _graph_terms(*values: Any) -> list[str]:
    """Extract stable graph terms without exposing full content."""
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in _extract_search_terms(str(value or "")):
            normalized = term.lower().strip()
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
            if len(terms) >= 8:
                return terms
    return terms


def memory_graph(limit: int = 160) -> dict:
    """Build a read-only Obsidian-style graph from Lexa memory surfaces.

    The graph payload exposes compact labels/previews only. It never writes to
    the database and never returns full note, conversation, or memory bodies.
    """
    db = _get_db()
    limit = max(40, min(MEMORY_GRAPH_MAX_NODES, int(limit or 160)))
    fixed_node_budget = 1 + 5 + len(MEMORY_TYPES) + MEMORY_GRAPH_KEYWORD_NODES
    per_bucket = max(8, (limit - fixed_node_budget) // 4)
    secondary_bucket = max(6, per_bucket // 2)

    nodes: dict[str, dict] = {}
    links: list[dict] = []
    terms_by_node: dict[str, set[str]] = {}
    keyword_counts: dict[str, int] = {}

    def add_node(
        node_id: str,
        label: str,
        node_type: str,
        *,
        group: str | None = None,
        weight: float = 1.0,
        preview: str = "",
        meta: dict | None = None,
        terms: list[str] | None = None,
    ) -> None:
        nodes[node_id] = {
            "id": node_id,
            "label": _graph_text(label, 80) or node_type.title(),
            "type": node_type,
            "group": group or node_type,
            "weight": round(max(0.5, min(12.0, float(weight or 1.0))), 3),
            "preview": _graph_text(preview, 160),
            "meta": meta or {},
        }
        safe_terms = {t for t in (terms or []) if t and len(t) >= 3}
        terms_by_node[node_id] = safe_terms
        for term in safe_terms:
            keyword_counts[term] = keyword_counts.get(term, 0) + 1

    def add_link(source: str, target: str, kind: str, *, weight: float = 1.0) -> None:
        if source == target or source not in nodes or target not in nodes:
            return
        key = tuple(sorted((source, target))) + (kind,)
        for existing in links:
            existing_key = tuple(sorted((existing["source"], existing["target"]))) + (existing.get("kind", ""),)
            if existing_key == key:
                existing["weight"] = round(max(float(existing.get("weight", 1)), weight), 3)
                return
        if len(links) < MEMORY_GRAPH_MAX_LINKS:
            links.append({
                "source": source,
                "target": target,
                "kind": kind,
                "weight": round(max(0.2, min(6.0, float(weight or 1.0))), 3),
            })

    add_node(
        "hub:memory",
        "Lexa Gedächtnis",
        "hub",
        group="hub",
        weight=10,
        preview="Lokaler Wissensgraph aus Notizen, Erinnerungen, Chats, Routinen und Snippets.",
    )
    for group_id, label in [
        ("group:notes", "Notizen"),
        ("group:memories", "Erinnerungen"),
        ("group:conversations", "Chats"),
        ("group:routines", "Routinen"),
        ("group:snippets", "Snippets"),
    ]:
        add_node(group_id, label, "group", group=group_id.split(":", 1)[1], weight=5)
        add_link("hub:memory", group_id, "contains", weight=2.5)

    notes = db.execute(
        """SELECT id, title, category, created_at, updated_at, SUBSTR(content, 1, 320) AS preview
           FROM notes
           ORDER BY updated_at DESC
           LIMIT ?""",
        (per_bucket,),
    ).fetchall()
    for row in notes:
        node_id = f"note:{row['id']}"
        terms = _graph_terms(row["title"], row["category"], row["preview"])
        add_node(
            node_id,
            row["title"],
            "note",
            group="notes",
            weight=2.4 + min(4, len(terms) * 0.45),
            preview=row["preview"],
            meta={"category": row["category"], "updated_at": row["updated_at"]},
            terms=terms,
        )
        add_link("group:notes", node_id, "contains")

    memories = db.execute(
        """SELECT id, content, category, memory_type, importance, source, created_at,
                  access_count, last_accessed_at
           FROM memories
           ORDER BY importance DESC, access_count DESC, created_at DESC
           LIMIT ?""",
        (per_bucket,),
    ).fetchall()
    for memory_type in MEMORY_TYPES:
        type_id = f"type:{memory_type}"
        add_node(type_id, memory_type, "type", group="memories", weight=3.2)
        add_link("group:memories", type_id, "type", weight=1.2)
    for row in memories:
        node_id = f"memory:{row['id']}"
        content = row["content"]
        terms = _graph_terms(content, row["category"], row["memory_type"])
        importance = int(row["importance"] or 5)
        add_node(
            node_id,
            content,
            "memory",
            group=row["memory_type"] or "memories",
            weight=2.2 + importance * 0.35 + min(3, int(row["access_count"] or 0) * 0.1),
            preview=content,
            meta={
                "category": row["category"],
                "memory_type": row["memory_type"],
                "importance": importance,
                "source": row["source"],
                "created_at": row["created_at"],
            },
            terms=terms,
        )
        add_link("group:memories", node_id, "contains")
        if row["memory_type"]:
            add_link(f"type:{row['memory_type']}", node_id, "typed", weight=1.6)

    conversations = conversation_list(limit=per_bucket)
    for row in conversations:
        node_id = f"conversation:{row['id']}"
        title = row.get("title") or "Chat"
        preview = row.get("last_message") or ""
        count = int(row.get("message_count") or 0)
        terms = _graph_terms(title, preview)
        add_node(
            node_id,
            title,
            "conversation",
            group="conversations",
            weight=2.0 + min(5.5, math.log(count + 1, 2) if count else 0.6),
            preview=preview,
            meta={"message_count": count, "updated_at": row.get("updated_at")},
            terms=terms,
        )
        add_link("group:conversations", node_id, "contains")

    routines = db.execute(
        """SELECT id, name, description, schedule, enabled, last_run
           FROM routines
           ORDER BY enabled DESC, name
           LIMIT ?""",
        (secondary_bucket,),
    ).fetchall()
    for row in routines:
        node_id = f"routine:{row['id']}"
        terms = _graph_terms(row["name"], row["description"], row["schedule"])
        add_node(
            node_id,
            row["name"],
            "routine",
            group="routines",
            weight=3.2 if row["enabled"] else 2.2,
            preview=row["description"] or row["schedule"],
            meta={"schedule": row["schedule"], "enabled": bool(row["enabled"])},
            terms=terms,
        )
        add_link("group:routines", node_id, "contains")

    snippets = db.execute(
        """SELECT name, SUBSTR(text, 1, 260) AS preview, use_count, created_at
           FROM snippets
           ORDER BY use_count DESC, name
           LIMIT ?""",
        (secondary_bucket,),
    ).fetchall()
    for row in snippets:
        node_id = f"snippet:{row['name']}"
        terms = _graph_terms(row["name"], row["preview"])
        add_node(
            node_id,
            row["name"],
            "snippet",
            group="snippets",
            weight=2.2 + min(4, int(row["use_count"] or 0) * 0.2),
            preview=row["preview"],
            meta={"use_count": int(row["use_count"] or 0), "created_at": row["created_at"]},
            terms=terms,
        )
        add_link("group:snippets", node_id, "contains")

    keyword_terms = [
        term for term, count in sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))
        if count >= 2
    ][:MEMORY_GRAPH_KEYWORD_NODES]
    for term in keyword_terms:
        keyword_id = f"keyword:{term}"
        add_node(
            keyword_id,
            term,
            "keyword",
            group="keywords",
            weight=1.8 + min(5, keyword_counts[term] * 0.4),
            preview=f"{keyword_counts[term]} lokale Treffer",
        )
        add_link("hub:memory", keyword_id, "keyword", weight=0.6)
        linked = 0
        for node_id, terms in terms_by_node.items():
            if term in terms and nodes.get(node_id, {}).get("type") not in {"hub", "group", "type", "keyword"}:
                add_link(keyword_id, node_id, "mentions", weight=1.0 + min(2, keyword_counts[term] * 0.08))
                linked += 1
                if linked >= 14:
                    break

    content_node_ids = [
        node_id for node_id, node in nodes.items()
        if node.get("type") in {"note", "memory", "conversation", "routine", "snippet"}
    ]
    pair_links = 0
    for index, left in enumerate(content_node_ids):
        left_terms = terms_by_node.get(left) or set()
        if not left_terms:
            continue
        for right in content_node_ids[index + 1:]:
            overlap = left_terms.intersection(terms_by_node.get(right) or set())
            if len(overlap) >= 2:
                add_link(left, right, "related", weight=min(2.8, 0.8 + len(overlap) * 0.35))
                pair_links += 1
                if pair_links >= 80:
                    break
        if pair_links >= 80:
            break

    return {
        "status": "ok",
        "nodes": list(nodes.values()),
        "links": links,
        "counts": {
            "nodes": len(nodes),
            "links": len(links),
            "notes": len(notes),
            "memories": len(memories),
            "conversations": len(conversations),
            "routines": len(routines),
            "snippets": len(snippets),
            "keywords": len(keyword_terms),
        },
        "source": "local_sqlite_readonly",
    }


# ══════════════════════════════════════════════════
#  CLIPBOARD HISTORY (persistent)
# ══════════════════════════════════════════════════

MAX_CLIPBOARD_ENTRIES: int = 50


def clipboard_add(text: str) -> str:
    """Add text to clipboard history (avoids duplicates, moves to top)."""
    if not text or not text.strip():
        return "empty"
    db = _get_db()
    # Remove duplicates
    db.execute("DELETE FROM clipboard_entries WHERE text = ?", (text,))
    # Insert at top (newest ID = most recent)
    db.execute("INSERT INTO clipboard_entries (text) VALUES (?)", (text,))
    # Enforce max entries
    db.execute(
        """DELETE FROM clipboard_entries WHERE id NOT IN
           (SELECT id FROM clipboard_entries ORDER BY id DESC LIMIT ?)""",
        (MAX_CLIPBOARD_ENTRIES,),
    )
    db.commit()
    count = db.execute("SELECT COUNT(*) as c FROM clipboard_entries").fetchone()["c"]
    return f"added:{count}"


def clipboard_list() -> list[dict]:
    """Get clipboard history (newest first)."""
    db = _get_db()
    rows = db.execute(
        "SELECT text, created_at FROM clipboard_entries ORDER BY id DESC LIMIT ?",
        (MAX_CLIPBOARD_ENTRIES,),
    ).fetchall()
    return [{"text": r["text"], "timestamp": r["created_at"]} for r in rows]


def clipboard_clear() -> str:
    """Clear all clipboard history."""
    db = _get_db()
    db.execute("DELETE FROM clipboard_entries")
    db.commit()
    return "cleared"


# ══════════════════════════════════════════════════
#  SESSION STATE (persist active chat history across restarts)
# ══════════════════════════════════════════════════

def session_save(key: str, value: Any) -> None:
    """Save a session state value (JSON-serialized)."""
    db = _get_db()
    serialized = json.dumps(value, ensure_ascii=False)
    db.execute(
        """INSERT INTO session_state (key, value)
           VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET
           value=excluded.value, updated_at=datetime('now','localtime')""",
        (key, serialized),
    )
    db.commit()


def session_load(key: str, default: Any = None) -> Any:
    """Load a session state value."""
    db = _get_db()
    row = db.execute(
        "SELECT value FROM session_state WHERE key = ?", (key,)
    ).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return default
    return default


# ══════════════════════════════════════════════════
#  TIMERS (persistent)
# ══════════════════════════════════════════════════

def timer_create(fire_at: float, message: str = "Timer abgelaufen!") -> int:
    """Save a timer to the DB. Returns the timer ID."""
    db = _get_db()
    cursor = db.execute(
        "INSERT INTO timers (message, fire_at) VALUES (?, ?)",
        (message, fire_at),
    )
    db.commit()
    return cursor.lastrowid


def timer_list_pending(now: "float | None" = None) -> list[dict]:
    """List timers that fired but are not yet acknowledged."""
    import time as _time
    if now is None:
        now = _time.time()
    db = _get_db()
    rows = db.execute(
        "SELECT id, message, fire_at FROM timers WHERE fire_at <= ? AND acknowledged = 0",
        (now,),
    ).fetchall()
    return [dict(r) for r in rows]


def timer_list_future(now: "float | None" = None) -> list[dict]:
    """List timers that haven't fired yet (fire_at > now)."""
    import time as _time
    if now is None:
        now = _time.time()
    db = _get_db()
    rows = db.execute(
        "SELECT id, message, fire_at FROM timers WHERE fire_at > ? AND acknowledged = 0",
        (now,),
    ).fetchall()
    return [dict(r) for r in rows]


def timer_acknowledge(timer_id: "int | None" = None) -> int:
    """Acknowledge timers. If timer_id is None, acknowledge all pending. Returns count."""
    import time as _time
    now = _time.time()
    db = _get_db()
    if timer_id is not None:
        result = db.execute(
            "UPDATE timers SET acknowledged = 1 WHERE id = ?", (timer_id,)
        )
    else:
        result = db.execute(
            "UPDATE timers SET acknowledged = 1 WHERE fire_at <= ? AND acknowledged = 0",
            (now,),
        )
    db.commit()
    # Cleanup old acknowledged timers (older than 1 hour)
    db.execute(
        "DELETE FROM timers WHERE acknowledged = 1 AND fire_at < ?",
        (now - 3600,),
    )
    db.commit()
    return result.rowcount


# ══════════════════════════════════════════════════
#  BACKUP / RESTORE
# ══════════════════════════════════════════════════

# Regex to validate column names (alphanumeric + underscore only)
_VALID_COL_RE = re.compile(r'^[a-z_][a-z0-9_]*$', re.IGNORECASE)


def _validate_table_name(table: str) -> bool:
    """Check if table name is in the allowed whitelist."""
    return table in _VALID_TABLES


def _validate_column_names(table: str, columns: list[str]) -> list[str]:
    """Filter column names to only those valid for the given table.

    Returns the list of safe column names, dropping any unrecognized ones.
    """
    valid = _VALID_COLUMNS.get(table, set())
    safe_cols = []
    for col in columns:
        if col in valid and _VALID_COL_RE.match(col):
            safe_cols.append(col)
        else:
            logger.warning(f"Skipping invalid column '{col}' for table '{table}'")
    return safe_cols


def backup_database(backup_path: str = "") -> dict:
    """Create a JSON backup of all data."""
    db = _get_db()
    data = {
        "version": "1.0.0",
        "created_at": datetime.now().isoformat(),
        "notes": [dict(r) for r in db.execute("SELECT * FROM notes").fetchall()],
        "memories": [dict(r) for r in db.execute("SELECT * FROM memories").fetchall()],
        "user_profile": [dict(r) for r in db.execute("SELECT * FROM user_profile").fetchall()],
        "routines": [dict(r) for r in db.execute("SELECT * FROM routines").fetchall()],
        "snippets": [dict(r) for r in db.execute("SELECT * FROM snippets").fetchall()],
        "conversations": [dict(r) for r in db.execute("SELECT * FROM conversations").fetchall()],
        "todos": [],
        "habits": [],
        "habit_logs": [],
    }
    # Try productivity tables (might not exist yet)
    try:
        from backend import productivity
        prod_db = productivity._get_db()
        data["todos"] = [dict(r) for r in prod_db.execute("SELECT * FROM todos").fetchall()]
        data["habits"] = [dict(r) for r in prod_db.execute("SELECT * FROM habits").fetchall()]
        data["habit_logs"] = [dict(r) for r in prod_db.execute("SELECT * FROM habit_logs").fetchall()]
    except Exception:
        pass

    if backup_path:
        Path(backup_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data


def restore_database(data: dict) -> dict:
    """Restore data from a JSON backup. Returns stats.

    Uses whitelisted table/column names to prevent SQL injection via
    crafted backup files.

    IMPORTANT: All DELETE + INSERT operations run inside a single transaction.
    If anything fails, the entire restore is rolled back — no data loss.
    """
    db = _get_db()
    stats: dict[str, int] = {}
    try:
        # BEGIN IMMEDIATE acquires a write lock upfront — prevents other writers
        # from interleaving during the restore window
        db.execute("BEGIN IMMEDIATE")

        for table in ["notes", "memories", "user_profile", "routines", "snippets", "conversations"]:
            if not _validate_table_name(table):
                continue
            rows = data.get(table, [])
            if not rows:
                continue
            # Clear existing data — table name is from our whitelist, safe to use
            db.execute(f"DELETE FROM {table}")
            # Insert backup data with validated column names
            inserted = 0
            for row in rows:
                if table == "memories":
                    row = dict(row)
                    row["memory_type"] = (
                        normalize_memory_type(row.get("memory_type"))
                        or classify_memory_type(
                            row.get("content", ""),
                            row.get("category", "fact"),
                            row.get("source", "user"),
                        )
                    )
                raw_cols = list(row.keys())
                safe_cols = _validate_column_names(table, raw_cols)
                if not safe_cols:
                    continue
                placeholders = ", ".join(["?"] * len(safe_cols))
                col_str = ", ".join(safe_cols)
                values = [row[c] for c in safe_cols]
                try:
                    db.execute(f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders})", values)
                    inserted += 1
                except Exception:
                    pass
            stats[table] = inserted

        db.execute("COMMIT")

        # Rebuild FTS index after restore (outside transaction — non-critical)
        try:
            _rebuild_fts(db)
        except Exception:
            logger.warning("FTS rebuild after restore failed", exc_info=True)

        # Restore productivity data (separate DB connection, separate transaction)
        try:
            from backend import productivity
            prod_db = productivity._get_db()
            prod_db.execute("BEGIN IMMEDIATE")
            for table in ["todos", "habits", "habit_logs"]:
                rows = data.get(table, [])
                if not rows:
                    continue
                # Productivity tables not in our whitelist — validate manually
                if not re.match(r'^[a-z_]+$', table):
                    continue
                prod_db.execute(f"DELETE FROM {table}")
                inserted = 0
                for row in rows:
                    raw_cols = list(row.keys())
                    # Only allow safe column names
                    safe_cols = [c for c in raw_cols if _VALID_COL_RE.match(c)]
                    if not safe_cols:
                        continue
                    placeholders = ", ".join(["?"] * len(safe_cols))
                    col_str = ", ".join(safe_cols)
                    values = [row[c] for c in safe_cols]
                    try:
                        prod_db.execute(f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({placeholders})", values)
                        inserted += 1
                    except Exception:
                        pass
                stats[table] = inserted
            prod_db.execute("COMMIT")
        except Exception:
            try:
                prod_db.execute("ROLLBACK")
            except Exception:
                pass
            logger.warning("Productivity restore failed — rolled back", exc_info=True)

        return {"status": "ok", "restored": stats}
    except Exception as e:
        # CRITICAL: Roll back the main DB transaction on ANY failure
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"Database restore failed — rolled back: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}


# ══════════════════════════════════════════════════
#  CONVERSATION SUMMARIES
# ══════════════════════════════════════════════════

def save_conversation_summary(conv_id: int, summary: str, msg_range: str) -> None:
    """Save a summary for a conversation message range."""
    with _db_session() as db:
        db.execute(
            "INSERT INTO conversation_summaries (conversation_id, summary, message_range) VALUES (?, ?, ?)",
            (conv_id, summary, msg_range),
        )
        db.commit()
        logger.debug(f"Saved conversation summary for conv {conv_id}, range {msg_range}")


def get_conversation_summaries(conv_id: int) -> list[dict]:
    """Get all summaries for a conversation, ordered by creation."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, conversation_id, summary, message_range, created_at "
        "FROM conversation_summaries WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_summary(conv_id: int) -> Optional[str]:
    """Get the most recent summary for a conversation."""
    db = _get_db()
    row = db.execute(
        "SELECT summary FROM conversation_summaries "
        "WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
        (conv_id,),
    ).fetchone()
    return row["summary"] if row else None
