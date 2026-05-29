"""Thread-local SQLite connection helpers for backend.memory."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Callable


def open_memory_connection(db_path: str | Path, logger: logging.Logger) -> sqlite3.Connection:
    """Open a tuned SQLite connection for the memory database."""
    db = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    db.row_factory = sqlite3.Row
    wal_result = db.execute("PRAGMA journal_mode=WAL").fetchone()
    if wal_result and wal_result[0].lower() != "wal":
        logger.warning(
            "WAL mode not enabled - journal_mode is '%s'. "
            "Performance may be degraded. This can happen on network drives.",
            wal_result[0],
        )
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("PRAGMA mmap_size=268435456")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def get_thread_memory_connection(
    thread_local: SimpleNamespace,
    *,
    db_path: str | Path,
    logger: logging.Logger,
    initialize_schema: Callable[[sqlite3.Connection], None],
) -> sqlite3.Connection:
    """Return a live thread-local connection, creating and initializing it if needed."""
    db = getattr(thread_local, "db", None)
    if db is not None:
        try:
            db.execute("SELECT 1")
            return db
        except Exception:
            try:
                db.close()
            except Exception:
                pass
            thread_local.db = None

    db = open_memory_connection(db_path, logger)
    initialize_schema(db)
    thread_local.db = db
    return db


def close_thread_memory_connection(
    thread_local: SimpleNamespace,
    *,
    before_close: Callable[[sqlite3.Connection], None] | None = None,
) -> None:
    """Close the current thread-local connection if present."""
    db = getattr(thread_local, "db", None)
    if db is not None:
        try:
            if before_close is not None:
                before_close(db)
            db.close()
        except Exception:
            pass
        thread_local.db = None
