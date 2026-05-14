"""Lexa AI — Smart Reminders (Upgrade 3)
Persistent, recurring reminders with natural language time parsing.
Stored in SQLite (lexa_memory.db), survives app restarts.
"""

import logging
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import os

logger = logging.getLogger("lexa.reminders")

_tables_ready = False
_tables_lock = threading.Lock()
_thread_local = threading.local()

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
DB_PATH = Path(_DATA_DIR) / "lexa_memory.db"

# Fired reminders waiting for frontend pickup (mirrors _timer_results pattern)
_fired_reminders: list[dict] = []
_fired_lock = threading.Lock()


# ══════════════════════════════════════════════════
#  DATABASE CONNECTION (thread-local, same pattern as productivity.py)
# ══════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    """Get database connection with auto-init. Reuses connection per thread."""
    db = getattr(_thread_local, "db", None)
    if db is not None:
        try:
            db.execute("SELECT 1")
            return db
        except Exception:
            try:
                db.close()
            except Exception:
                pass
            _thread_local.db = None

    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    _ensure_tables(db)
    _thread_local.db = db
    return db


def _ensure_tables(db: sqlite3.Connection) -> None:
    global _tables_ready
    if _tables_ready:
        return
    with _tables_lock:
        if _tables_ready:
            return
        db.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                fire_at TEXT NOT NULL,
                repeat TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                fired_count INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_reminders_fire_at ON reminders(fire_at);
            CREATE INDEX IF NOT EXISTS idx_reminders_active ON reminders(active);
        """)
        _tables_ready = True


# ══════════════════════════════════════════════════
#  TIME PARSING
# ══════════════════════════════════════════════════

def _parse_time(time_str: str) -> Optional[datetime]:
    """Parse natural language time string to datetime.

    Supports German and English via dateparser, with manual fallback patterns.
    """
    if not time_str or not time_str.strip():
        return None

    time_str = time_str.strip()
    now = datetime.now()

    # Try manual patterns FIRST (more reliable for German "X Uhr" patterns)
    manual = _try_manual_patterns(time_str, now)
    if manual:
        return manual

    # Fall back to dateparser (handles complex natural language)
    try:
        import dateparser
        result = dateparser.parse(
            time_str,
            settings={
                "PREFER_DATES_FROM": "future",
                "TIMEZONE": "Europe/Berlin",
                "RETURN_AS_TIMEZONE_AWARE": False,
                "RELATIVE_BASE": now,
            },
            languages=["de", "en"],
        )
        if result and result > now:
            return result
    except Exception as e:
        logger.debug(f"dateparser failed for '{time_str}': {e}")

    return None


def _try_manual_patterns(time_str: str, now: datetime) -> Optional[datetime]:
    """Try manual regex patterns for common German/English time expressions."""

    # "in X min/minuten"
    m = re.match(r"^in\s+(\d{1,4})\s*(?:min(?:uten?)?|m)$", time_str, re.IGNORECASE)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # "in X stunden/h"
    m = re.match(r"^in\s+(\d{1,3})\s*(?:stunden?|h(?:ours?)?)$", time_str, re.IGNORECASE)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # "in X tagen"
    m = re.match(r"^in\s+(\d{1,3})\s*(?:tagen?|days?)$", time_str, re.IGNORECASE)
    if m:
        return now + timedelta(days=int(m.group(1)))

    # "morgen um HH:MM"
    m = re.match(r"^morgen\s+(?:um\s+)?(\d{1,2}):(\d{2})$", time_str, re.IGNORECASE)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=h, minute=mi, second=0, microsecond=0)

    # "morgen um H Uhr" or "morgen um H"
    m = re.match(r"^morgen\s+(?:um\s+)?(\d{1,2})\s*(?:uhr)?$", time_str, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=h, minute=0, second=0, microsecond=0)

    # "um HH:MM" (today or tomorrow if past)
    m = re.match(r"^(?:um\s+)?(\d{1,2}):(\d{2})$", time_str, re.IGNORECASE)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    # "um H Uhr" or "um H" (bare hour)
    m = re.match(r"^um\s+(\d{1,2})\s*(?:uhr)?$", time_str, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    return None


def _calculate_next(fire_at_str: str, repeat: str) -> Optional[str]:
    """Calculate the next fire_at for recurring reminders.

    Returns ISO string or None if repeat type is invalid.
    """
    try:
        fire_at = datetime.fromisoformat(fire_at_str)
    except (ValueError, TypeError):
        return None

    now = datetime.now()

    if repeat == "daily":
        next_fire = fire_at + timedelta(days=1)
        # Skip past times
        while next_fire <= now:
            next_fire += timedelta(days=1)
        return next_fire.isoformat()

    elif repeat == "weekly":
        next_fire = fire_at + timedelta(weeks=1)
        while next_fire <= now:
            next_fire += timedelta(weeks=1)
        return next_fire.isoformat()

    elif repeat == "monthly":
        # Add approximately 1 month
        month = fire_at.month + 1
        year = fire_at.year
        if month > 12:
            month = 1
            year += 1
        day = min(fire_at.day, 28)  # Safe day for all months
        next_fire = fire_at.replace(year=year, month=month, day=day)
        while next_fire <= now:
            month = next_fire.month + 1
            year = next_fire.year
            if month > 12:
                month = 1
                year += 1
            next_fire = next_fire.replace(year=year, month=month, day=day)
        return next_fire.isoformat()

    elif repeat == "weekdays":
        # Next weekday (Mon-Fri)
        next_fire = fire_at + timedelta(days=1)
        while next_fire.weekday() >= 5 or next_fire <= now:  # 5=Sat, 6=Sun
            next_fire += timedelta(days=1)
        return next_fire.isoformat()

    return None


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

VALID_REPEAT = {"daily", "weekly", "monthly", "weekdays"}


def reminder_create(message: str, time: str, repeat: str = None) -> dict:
    """Create a new reminder with natural language time parsing.

    Args:
        message: What to remind about
        time: When — e.g. "morgen um 9", "in 2 Stunden", "jeden Montag 8 Uhr"
        repeat: Optional recurrence — daily, weekly, monthly, weekdays
    """
    if not message or not message.strip():
        return {"error": "Keine Nachricht angegeben."}
    message = str(message).strip()[:500]

    if not time or not time.strip():
        return {"error": "Keine Zeit angegeben."}

    # Validate repeat
    if repeat and repeat not in VALID_REPEAT:
        return {"error": f"Ungültiger Wiederholungstyp. Erlaubt: {', '.join(VALID_REPEAT)}"}

    # Parse time
    fire_at = _parse_time(time)
    if fire_at is None:
        return {"error": f"Konnte die Zeit nicht verstehen: '{time}'. Versuche z.B. 'morgen um 9', 'in 2 Stunden', '14:30'."}

    fire_at_str = fire_at.isoformat()

    db = _get_db()
    try:
        cursor = db.execute(
            "INSERT INTO reminders (message, fire_at, repeat, active) VALUES (?, ?, ?, 1)",
            (message, fire_at_str, repeat),
        )
        db.commit()
        reminder_id = cursor.lastrowid
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        return {"error": f"Datenbankfehler: {e}"}

    # Format for display
    fire_display = fire_at.strftime("%d.%m.%Y %H:%M")
    repeat_display = ""
    if repeat:
        repeat_names = {
            "daily": "täglich",
            "weekly": "wöchentlich",
            "monthly": "monatlich",
            "weekdays": "werktags (Mo-Fr)",
        }
        repeat_display = f" ({repeat_names.get(repeat, repeat)})"

    logger.info(f"Reminder #{reminder_id} created: '{message}' at {fire_at_str} repeat={repeat}")
    return {
        "id": reminder_id,
        "message": message,
        "fire_at": fire_at_str,
        "fire_at_display": fire_display,
        "repeat": repeat,
        "status": f"Erinnerung erstellt: '{message}' am {fire_display}{repeat_display}",
    }


def reminder_list(include_fired: bool = False) -> list[dict]:
    """List all active reminders sorted by fire_at."""
    db = _get_db()
    if include_fired:
        rows = db.execute(
            "SELECT * FROM reminders ORDER BY fire_at ASC"
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM reminders WHERE active = 1 ORDER BY fire_at ASC"
        ).fetchall()

    reminders = []
    for r in rows:
        d = dict(r)
        try:
            fire_at = datetime.fromisoformat(d["fire_at"])
            d["fire_at_display"] = fire_at.strftime("%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            d["fire_at_display"] = d["fire_at"]
        reminders.append(d)

    return reminders


def reminder_delete(id: int) -> dict:
    """Soft-delete a reminder (set active=False)."""
    if not id:
        return {"error": "Keine ID angegeben."}

    db = _get_db()
    cursor = db.execute(
        "UPDATE reminders SET active = 0 WHERE id = ? AND active = 1",
        (int(id),),
    )
    db.commit()

    if cursor.rowcount == 0:
        return {"error": f"Erinnerung #{id} nicht gefunden oder bereits gelöscht."}

    logger.info(f"Reminder #{id} deleted (soft)")
    return {"status": f"Erinnerung #{id} gelöscht.", "id": int(id)}


def reminder_snooze(reminder_id: int, minutes: int = 10) -> dict:
    """Postpone a reminder by N minutes."""
    if not reminder_id:
        return {"error": "Keine ID angegeben."}
    minutes = max(1, min(1440, int(minutes)))

    new_fire_at = datetime.now() + timedelta(minutes=minutes)
    fire_at_str = new_fire_at.isoformat()

    db = _get_db()
    cursor = db.execute(
        "UPDATE reminders SET fire_at = ?, active = 1 WHERE id = ?",
        (fire_at_str, int(reminder_id)),
    )
    db.commit()

    if cursor.rowcount == 0:
        return {"error": f"Erinnerung #{reminder_id} nicht gefunden."}

    logger.info(f"Reminder #{reminder_id} snoozed for {minutes}min to {fire_at_str}")
    return {
        "status": f"Erinnerung um {minutes} Minuten verschoben.",
        "id": int(reminder_id),
        "new_fire_at": fire_at_str,
    }


def reminder_check() -> list[dict]:
    """Check for reminders that should fire now.

    Called by the scheduler every 30-60 seconds.
    Returns list of fired reminders.
    """
    now = datetime.now()
    now_str = now.isoformat()

    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM reminders WHERE fire_at <= ? AND active = 1",
            (now_str,),
        ).fetchall()
    except Exception as e:
        logger.error(f"reminder_check DB error: {e}")
        return []

    fired = []
    for r in rows:
        reminder = dict(r)
        reminder_id = reminder["id"]
        message = reminder["message"]
        repeat = reminder.get("repeat")

        # Mark as fired
        db.execute(
            "UPDATE reminders SET active = 0, fired_count = fired_count + 1 WHERE id = ?",
            (reminder_id,),
        )

        # If recurring, create next occurrence
        if repeat and repeat in VALID_REPEAT:
            next_fire = _calculate_next(reminder["fire_at"], repeat)
            if next_fire:
                db.execute(
                    "INSERT INTO reminders (message, fire_at, repeat, active, fired_count) VALUES (?, ?, ?, 1, 0)",
                    (message, next_fire, repeat),
                )
                logger.info(f"Recurring reminder '{message}': next at {next_fire}")

        fired.append({"id": reminder_id, "message": message, "repeat": repeat})
        logger.info(f"Reminder #{reminder_id} fired: '{message}'")

    if fired:
        db.commit()
        # Add to fired queue for frontend pickup
        with _fired_lock:
            for f in fired:
                _fired_reminders.append({
                    "message": f["message"],
                    "id": f["id"],
                    "fired_at": now.isoformat(),
                    "acknowledged": False,
                })

    return fired


def get_pending_fired() -> list[dict]:
    """Get fired reminders not yet acknowledged (for frontend polling)."""
    with _fired_lock:
        pending = [r for r in _fired_reminders if not r["acknowledged"]]
    return pending


def acknowledge_fired() -> int:
    """Acknowledge all fired reminders. Returns count acknowledged."""
    count = 0
    with _fired_lock:
        for r in _fired_reminders:
            if not r["acknowledged"]:
                r["acknowledged"] = True
                count += 1
        # Clean up old entries
        _fired_reminders[:] = [
            r for r in _fired_reminders if not r["acknowledged"]
        ]
    return count
