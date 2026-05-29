"""Buffered access-count tracking for memory search results."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time


class MemoryAccessTracker:
    """Batch memory access updates to avoid write-lock churn during reads."""

    def __init__(
        self,
        *,
        flush_seconds: int,
        max_ids: int,
        logger: logging.Logger,
    ) -> None:
        self.flush_seconds = max(1, int(flush_seconds))
        self.max_ids = max(1, int(max_ids))
        self.logger = logger
        self._lock = threading.Lock()
        self._counts: dict[int, int] = {}
        self._last_flush = 0.0

    def track(self, db: sqlite3.Connection, memory_ids: list[int]) -> None:
        """Track returned-memory access through a bounded write buffer."""
        ids = sorted({int(memory_id) for memory_id in memory_ids if memory_id})
        if not ids:
            return
        now = time.monotonic()
        with self._lock:
            for memory_id in ids:
                self._counts[memory_id] = self._counts.get(memory_id, 0) + 1
            should_flush = (
                self._last_flush <= 0.0
                or now - self._last_flush >= self.flush_seconds
                or len(self._counts) >= self.max_ids
            )
        if should_flush:
            self.flush(db)

    def flush(self, db: sqlite3.Connection) -> int:
        """Flush buffered memory access counters to SQLite in one small batch."""
        with self._lock:
            pending = dict(self._counts)
            self._counts.clear()
            self._last_flush = time.monotonic()

        if not pending:
            return 0

        try:
            for memory_id, increment in pending.items():
                db.execute(
                    """UPDATE memories
                       SET access_count = COALESCE(access_count, 0) + ?,
                           last_accessed_at = datetime('now', 'localtime')
                       WHERE id = ?""",
                    (max(1, int(increment)), int(memory_id)),
                )
            db.commit()
            return len(pending)
        except Exception:
            self.logger.warning("Buffered memory access tracking flush failed", exc_info=True)
            with self._lock:
                for memory_id, increment in pending.items():
                    self._counts[memory_id] = self._counts.get(memory_id, 0) + increment
            return 0

    def reset(self) -> None:
        """Clear pending counters and reset the flush clock."""
        with self._lock:
            self._counts.clear()
            self._last_flush = 0.0
