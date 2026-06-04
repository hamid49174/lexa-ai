"""Lexa AI — Productivity Module (Production-Grade)
To-Do System, Pomodoro Timer, Gewohnheits-Tracker, Zeiterfassung, Fokus-Modus
"""

import os
import sqlite3
import logging
import re
import threading
import time
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional
from backend.config import LEXA_DATA_DIR
from backend.i18n import t

logger = logging.getLogger("lexa.productivity")

_tables_ready = False
_tables_lock = threading.Lock()
_pomodoro_lock = threading.Lock()
_time_tracker_lock = threading.Lock()
_thread_local = threading.local()

DB_PATH = LEXA_DATA_DIR / "lexa_memory.db"

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
VALID_STATUSES = {"open", "in_progress", "done", "cancelled"}
VALID_FREQUENCIES = {"daily", "weekly"}

# Windows-compatible hosts path
HOSTS_PATH = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "drivers", "etc", "hosts"
)
FOCUS_MARKER = "# LEXA-FOCUS-MODE"

# Domain validation pattern: valid FQDN, no leading/trailing dots, no consecutive dots
_DOMAIN_RE = re.compile(r'^(?!-)[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$')

# Pomodoro status cache
_pomodoro_status_cache: dict = {"data": None, "ts": 0.0}
_POMODORO_CACHE_TTL = 1.0  # seconds


# ══════════════════════════════════════════════════
#  VALIDATION HELPERS
# ══════════════════════════════════════════════════

def _validate_priority(priority: str, default: str = "normal") -> str:
    """Validate and return a valid priority string."""
    return priority if priority in VALID_PRIORITIES else default


def _validate_status(status: str) -> Optional[str]:
    """Validate status, return None if invalid."""
    return status if status in VALID_STATUSES else None


def _validate_duration(duration: int, min_val: int = 1, max_val: int = 120) -> int:
    """Clamp duration to valid range."""
    return max(min_val, min(max_val, int(duration)))


def _validate_due_date(due_date: str) -> Optional[str]:
    """Validate due_date as YYYY-MM-DD format. Returns cleaned date or None if invalid."""
    if not due_date or not due_date.strip():
        return None
    due_date = due_date.strip()
    try:
        datetime.strptime(due_date, "%Y-%m-%d")
        return due_date
    except ValueError:
        return None


def _validate_domain(domain: str) -> Optional[str]:
    """Validate FQDN. Returns cleaned domain or None if invalid."""
    domain = domain.strip().lower()
    if not domain or len(domain) > 253:
        return None
    # No leading/trailing dots
    if domain.startswith('.') or domain.endswith('.'):
        return None
    # No consecutive dots
    if '..' in domain:
        return None
    if not _DOMAIN_RE.match(domain):
        return None
    return domain


# ══════════════════════════════════════════════════
#  DATABASE CONNECTION (thread-local, kept alive)
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
    db.execute("PRAGMA cache_size=-64000")
    db.execute("PRAGMA temp_store=MEMORY")
    _init_productivity_tables(db)
    _thread_local.db = db
    return db


def _init_productivity_tables(db: sqlite3.Connection) -> None:
    global _tables_ready
    # Double-check locking pattern: fast path without lock, then acquire lock
    if _tables_ready:
        return
    with _tables_lock:
        if _tables_ready:
            return
        _init_productivity_tables_inner(db)
        _tables_ready = True


def _init_productivity_tables_inner(db: sqlite3.Connection) -> None:
    """Actual table creation — called under lock from _init_productivity_tables."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'normal' CHECK(priority IN ('low','normal','high','urgent')),
            status TEXT DEFAULT 'open' CHECK(status IN ('open','in_progress','done','cancelled')),
            category TEXT DEFAULT 'allgemein',
            due_date TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            frequency TEXT DEFAULT 'daily' CHECK(frequency IN ('daily','weekly')),
            target INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE,
            UNIQUE(habit_id, log_date)
        );

        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT DEFAULT '',
            duration_min INTEGER DEFAULT 25,
            started_at TEXT DEFAULT (datetime('now', 'localtime')),
            completed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS time_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            window_title TEXT DEFAULT '',
            duration_sec INTEGER DEFAULT 0,
            tracked_date TEXT DEFAULT (date('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS focus_blocked_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            blocked_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
        CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority);
        CREATE INDEX IF NOT EXISTS idx_todos_category ON todos(category);
        CREATE INDEX IF NOT EXISTS idx_habits_name ON habits(name);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs(log_date);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_habit_date ON habit_logs(habit_id, log_date);
        CREATE INDEX IF NOT EXISTS idx_pomodoro_date ON pomodoro_sessions(started_at);
        CREATE INDEX IF NOT EXISTS idx_time_tracking_date ON time_tracking(tracked_date);
        CREATE INDEX IF NOT EXISTS idx_focus_domain ON focus_blocked_domains(domain);
    """)

    # Add last_streak column if missing (migration for pre-compute streak)
    try:
        db.execute("SELECT last_streak FROM habits LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE habits ADD COLUMN last_streak INTEGER DEFAULT 0")

    db.commit()


# ══════════════════════════════════════════════════
#  TO-DO SYSTEM
# ══════════════════════════════════════════════════

def todo_create(title: str = "", description: str = "", priority: str = "normal",
                category: str = "allgemein", due_date: str = "") -> str:
    if not title:
        return "Titel fehlt."
    title = title[:200]
    description = description[:1000] if description else ""
    priority = _validate_priority(priority)
    # Validate due_date format if provided
    validated_due = _validate_due_date(due_date) if due_date else None

    db = _get_db()
    try:
        db.execute(
            "INSERT INTO todos (title, description, priority, category, due_date) VALUES (?, ?, ?, ?, ?)",
            (title, description, priority, category, validated_due),
        )
        db.commit()
        return f"To-Do '{title}' erstellt."
    except sqlite3.IntegrityError as e:
        return {"error": t("error.createFailed", error=str(e))}


def todo_list(status: str = "", category: str = "", priority: str = "") -> list[dict]:
    db = _get_db()
    query = "SELECT * FROM todos WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if category:
        query += " AND category = ?"
        params.append(category)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    query += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 END, created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def todo_update(id: int = 0, status: str = "", title: str = "", priority: str = "") -> str:
    if status and status not in VALID_STATUSES:
        return {"error": t("validation.invalidStatus", allowed=', '.join(VALID_STATUSES))}
    if priority and priority not in VALID_PRIORITIES:
        return {"error": t("validation.invalidPriority", allowed=', '.join(VALID_PRIORITIES))}
    if not id:
        return {"error": "ID fehlt."}
    db = _get_db()
    updates: list[str] = []
    params: list = []
    if status:
        updates.append("status = ?")
        params.append(status)
        if status == "done":
            updates.append("completed_at = datetime('now','localtime')")
    if title:
        updates.append("title = ?")
        params.append(title)
    if priority:
        updates.append("priority = ?")
        params.append(priority)
    if not updates:
        return t("error.noChanges")
    params.append(id)
    db.execute(f"UPDATE todos SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    return f"To-Do #{id} aktualisiert."


def todo_delete(id: int = 0) -> str:
    if not id:
        return {"error": "ID fehlt."}
    db = _get_db()
    result = db.execute("DELETE FROM todos WHERE id = ?", (id,))
    db.commit()
    return f"To-Do #{id} gelöscht." if result.rowcount else {"error": f"To-Do #{id} nicht gefunden."}


def todo_complete(id: int = 0) -> str:
    return todo_update(id=id, status="done")


# ══════════════════════════════════════════════════
#  POMODORO TIMER
# ══════════════════════════════════════════════════

_pomodoro_stop_event = threading.Event()

_active_pomodoro: dict = {
    "running": False,
    "task": "",
    "end_time": None,
    "duration_sec": 0,
    "thread": None,
    "completed_at": None,
    "acknowledged": True,
}


def pomodoro_start(task: str = "", duration: int = 25) -> str:
    with _pomodoro_lock:
        if _active_pomodoro["running"]:
            remaining = max(0, int((_active_pomodoro["end_time"] - time.time()) / 60))
            return f"Pomodoro läuft bereits ({remaining} Min verbleibend, Task: {_active_pomodoro['task']})"

        duration = _validate_duration(duration, 1, 120)
        _active_pomodoro["running"] = True
        _active_pomodoro["task"] = task
        _active_pomodoro["duration_sec"] = duration * 60
        _active_pomodoro["end_time"] = time.time() + duration * 60
        _active_pomodoro["completed_at"] = None
        _active_pomodoro["acknowledged"] = True
        # Clear stop event INSIDE lock so pomodoro_stop() can't race between
        # setting running=True above and clearing the event
        _pomodoro_stop_event.clear()
        # Invalidate status cache (merged into same lock acquisition)
        _pomodoro_status_cache["data"] = None

    # Log session
    db = _get_db()
    db.execute(
        "INSERT INTO pomodoro_sessions (task, duration_min) VALUES (?, ?)",
        (task, duration),
    )
    db.commit()

    def _timer():
        # Use Event.wait() instead of time.sleep() for clean cancellation
        stopped = _pomodoro_stop_event.wait(timeout=duration * 60)
        if stopped:
            # Timer was cancelled via pomodoro_stop()
            return
        with _pomodoro_lock:
            if _active_pomodoro["running"]:
                _active_pomodoro["running"] = False
                _active_pomodoro["completed_at"] = time.time()
                _active_pomodoro["acknowledged"] = False
                _pomodoro_status_cache["data"] = None
        # Mark completed in DB
        try:
            db2 = _get_db()
            db2.execute(
                "UPDATE pomodoro_sessions SET completed = 1 WHERE id = (SELECT MAX(id) FROM pomodoro_sessions)"
            )
            db2.commit()
        except Exception as e:
            logger.error(f"Pomodoro DB-Update fehlgeschlagen: {e}", exc_info=True)

    t = threading.Thread(target=_timer, daemon=True)
    t.start()
    _active_pomodoro["thread"] = t
    return f"Pomodoro gestartet: {duration} Min — Task: '{task or 'Kein Task'}'"


def pomodoro_stop() -> str:
    with _pomodoro_lock:
        if not _active_pomodoro["running"]:
            return "Kein aktiver Pomodoro."
        _active_pomodoro["running"] = False
        _active_pomodoro["end_time"] = None
        _pomodoro_status_cache["data"] = None
    # Signal the timer thread to terminate immediately
    _pomodoro_stop_event.set()
    return "Pomodoro gestoppt."


def pomodoro_status() -> dict:
    # Check cache first (1s TTL) — read under lock to prevent torn reads
    now = time.time()
    with _pomodoro_lock:
        cached = _pomodoro_status_cache.get("data")
        cache_ts = _pomodoro_status_cache.get("ts", 0.0)
    if cached is not None and (now - cache_ts) < _POMODORO_CACHE_TTL:
        # Update remaining_sec live even from cache if running
        if cached.get("running") and cached.get("_end_time"):
            remaining = max(0, int(cached["_end_time"] - now))
            cached_copy = dict(cached)
            cached_copy["remaining_sec"] = remaining
            cached_copy["remaining_min"] = remaining // 60
            return cached_copy
        return cached

    with _pomodoro_lock:
        running = _active_pomodoro["running"]
        end_time = _active_pomodoro["end_time"]
        task = _active_pomodoro["task"]
        duration_sec = _active_pomodoro.get("duration_sec", 0)
        completed_at = _active_pomodoro["completed_at"]
        acknowledged = _active_pomodoro["acknowledged"]

    if running and end_time:
        remaining = max(0, int((end_time - now)))
        result = {
            "running": True,
            "task": task,
            "remaining_sec": remaining,
            "remaining_min": remaining // 60,
            "duration_sec": duration_sec,
            "completed_just_now": False,
            "_end_time": end_time,  # internal, for cache update
        }
        with _pomodoro_lock:
            _pomodoro_status_cache["data"] = result
            _pomodoro_status_cache["ts"] = now
        return result

    # Check if pomodoro just completed (within last 60s) and not yet acknowledged
    completed_just_now = (
        completed_at is not None
        and not acknowledged
        and (now - completed_at) < 60
    )

    # Stats
    db = _get_db()
    today = date.today().isoformat()
    today_count = db.execute(
        "SELECT COUNT(*) as c FROM pomodoro_sessions WHERE completed = 1 AND date(started_at) = ?",
        (today,),
    ).fetchone()["c"]
    total = db.execute(
        "SELECT COUNT(*) as c FROM pomodoro_sessions WHERE completed = 1"
    ).fetchone()["c"]
    result = {
        "running": False,
        "today_completed": today_count,
        "total_completed": total,
        "completed_just_now": completed_just_now,
        "completed_task": task if completed_just_now else "",
    }
    with _pomodoro_lock:
        _pomodoro_status_cache["data"] = result
        _pomodoro_status_cache["ts"] = now
    return result


def pomodoro_acknowledge() -> str:
    """Acknowledge pomodoro completion so completed_just_now resets."""
    with _pomodoro_lock:
        _active_pomodoro["acknowledged"] = True
        _pomodoro_status_cache["data"] = None
    return "Pomodoro-Benachrichtigung bestätigt."


# ══════════════════════════════════════════════════
#  GEWOHNHEITS-TRACKER (HABITS)
# ══════════════════════════════════════════════════

def _calc_streak_sql(db: sqlite3.Connection, habit_id: int) -> int:
    """Calculate consecutive days streak using SQL date math — much faster than Python loop."""
    today_iso = date.today().isoformat()
    # Get all log dates for this habit, descending from today
    rows = db.execute(
        """SELECT log_date FROM habit_logs
           WHERE habit_id = ? AND log_date <= ? AND count > 0
           ORDER BY log_date DESC LIMIT 366""",
        (habit_id, today_iso),
    ).fetchall()
    if not rows:
        return 0

    streak = 0
    check_date = date.today()
    log_dates = {r["log_date"] for r in rows}

    for _ in range(366):
        if check_date.isoformat() in log_dates:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
    return streak


def habit_create(name: str = "", description: str = "", frequency: str = "daily", target: int = 1) -> str:
    if not name:
        return {"error": "Name fehlt."}
    if frequency not in VALID_FREQUENCIES:
        frequency = "daily"
    target = max(1, min(100, int(target)))
    db = _get_db()
    try:
        db.execute(
            """INSERT INTO habits (name, description, frequency, target)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
               description=excluded.description, frequency=excluded.frequency, target=excluded.target""",
            (name, description, frequency, target),
        )
        db.commit()
        return f"Gewohnheit '{name}' erstellt."
    except sqlite3.IntegrityError as e:
        return {"error": t("error.generic", error=str(e))}


def habit_log(name: str = "", count: int = 1) -> str:
    if not name:
        return {"error": "Name fehlt."}
    db = _get_db()
    habit = db.execute("SELECT id FROM habits WHERE name = ?", (name,)).fetchone()
    if not habit:
        return {"error": f"Gewohnheit '{name}' nicht gefunden."}
    today = date.today().isoformat()
    db.execute(
        """INSERT INTO habit_logs (habit_id, log_date, count)
           VALUES (?, ?, ?)
           ON CONFLICT(habit_id, log_date) DO UPDATE SET count = count + ?""",
        (habit["id"], today, count, count),
    )
    db.commit()

    # Pre-compute and store streak
    streak = _calc_streak_sql(db, habit["id"])
    db.execute("UPDATE habits SET last_streak = ? WHERE id = ?", (streak, habit["id"]))
    db.commit()

    return f"'{name}' für heute geloggt ({count}x)."


def habit_list() -> list[dict]:
    db = _get_db()
    habits = db.execute("SELECT * FROM habits ORDER BY name").fetchall()
    if not habits:
        return []

    today = date.today()
    today_iso = today.isoformat()
    week_start = (today - timedelta(days=6)).isoformat()

    habit_ids = [h["id"] for h in habits]
    placeholders = ",".join("?" * len(habit_ids))

    # Batch query: all logs in last 7 days for all habits (fixes N+1)
    week_logs = db.execute(
        f"""SELECT habit_id, log_date, count FROM habit_logs
            WHERE habit_id IN ({placeholders}) AND log_date >= ? AND log_date <= ?""",
        (*habit_ids, week_start, today_iso),
    ).fetchall()

    # Build lookup: {habit_id: {date_str: count}}
    log_map: dict[int, dict[str, int]] = {}
    for row in week_logs:
        hid = row["habit_id"]
        if hid not in log_map:
            log_map[hid] = {}
        log_map[hid][row["log_date"]] = row["count"]

    result = []
    for h in habits:
        hd = dict(h)
        hid = h["id"]
        habit_logs = log_map.get(hid, {})

        # Today's progress
        hd["today_count"] = habit_logs.get(today_iso, 0)
        hd["today_done"] = hd["today_count"] >= h["target"]

        # Use pre-computed streak from DB, fallback to calculation
        hd["streak"] = h["last_streak"] if h["last_streak"] else _calc_streak_sql(db, hid)

        # Last 7 days for mini-calendar (True/False per day, oldest first)
        week = []
        for i in range(6, -1, -1):
            day = (today - timedelta(days=i)).isoformat()
            day_count = habit_logs.get(day, 0)
            week.append(bool(day_count >= h["target"]))
        hd["week"] = week
        result.append(hd)
    return result


def _calc_streak(db: sqlite3.Connection, habit_id: int) -> int:
    """Legacy wrapper — delegates to SQL-based implementation."""
    return _calc_streak_sql(db, habit_id)


def habit_delete(name: str = "") -> str:
    if not name:
        return {"error": "Name fehlt."}
    db = _get_db()
    result = db.execute("DELETE FROM habits WHERE name = ?", (name,))
    db.commit()
    return f"Gewohnheit '{name}' gelöscht." if result.rowcount else {"error": f"'{name}' nicht gefunden."}


def habit_stats() -> dict:
    db = _get_db()
    total = db.execute("SELECT COUNT(*) as c FROM habits").fetchone()["c"]
    today = date.today().isoformat()
    done_today = db.execute(
        """SELECT COUNT(DISTINCT h.id) as c FROM habits h
           JOIN habit_logs hl ON h.id = hl.habit_id
           WHERE hl.log_date = ? AND hl.count >= h.target""",
        (today,),
    ).fetchone()["c"]
    return {"total_habits": total, "completed_today": done_today}


# ══════════════════════════════════════════════════
#  ZEITERFASSUNG (TIME TRACKING)
# ══════════════════════════════════════════════════

_time_tracker: dict = {"running": False, "thread": None, "start_time": None, "current_app": ""}
_time_tracker_stop_event = threading.Event()


def _get_active_window() -> tuple[str, str]:
    """Get currently active window app name and title."""
    try:
        ps = '''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Text;
        using System.Diagnostics;
        public class ActiveWin {
            [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
            [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
            [DllImport("user32.dll")] static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
            public static string[] Get() {
                IntPtr h = GetForegroundWindow();
                uint pid;
                GetWindowThreadProcessId(h, out pid);
                var sb = new StringBuilder(256);
                GetWindowText(h, sb, 256);
                try {
                    var p = Process.GetProcessById((int)pid);
                    return new string[] { p.ProcessName, sb.ToString() };
                } catch { return new string[] { "unknown", sb.ToString() }; }
            }
        }
"@
        $r = [ActiveWin]::Get()
        "$($r[0])|$($r[1])"
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=5,
        )
        parts = result.stdout.strip().split("|", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return "unknown", ""
    except Exception:
        return "unknown", ""


def time_tracking_start() -> str:
    with _time_tracker_lock:
        if _time_tracker["running"]:
            return "Zeiterfassung läuft bereits."
        _time_tracker["running"] = True
        _time_tracker["start_time"] = datetime.now().isoformat()
        _time_tracker["current_app"] = ""

    # Clear stop event before starting thread so previous set() doesn't leak
    _time_tracker_stop_event.clear()

    def _track():
        while True:
            with _time_tracker_lock:
                if not _time_tracker["running"]:
                    break
            try:
                app_name, title = _get_active_window()
                if app_name and app_name != "unknown":
                    with _time_tracker_lock:
                        _time_tracker["current_app"] = app_name
                    db = _get_db()
                    today = date.today().isoformat()
                    existing = db.execute(
                        "SELECT id, duration_sec FROM time_tracking WHERE app_name = ? AND tracked_date = ?",
                        (app_name, today),
                    ).fetchone()
                    if existing:
                        db.execute(
                            "UPDATE time_tracking SET duration_sec = duration_sec + 30, window_title = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                            (title[:200], existing["id"]),
                        )
                    else:
                        db.execute(
                            "INSERT INTO time_tracking (app_name, window_title, duration_sec, tracked_date) VALUES (?, ?, 30, ?)",
                            (app_name, title[:200], today),
                        )
                    db.commit()
            except Exception as e:
                logger.debug(f"Time tracking error: {e}", exc_info=True)
            # Use Event.wait() instead of time.sleep() for immediate wakeup on stop
            if _time_tracker_stop_event.wait(timeout=30):
                break

    t = threading.Thread(target=_track, daemon=True)
    t.start()
    with _time_tracker_lock:
        _time_tracker["thread"] = t
    return "Zeiterfassung gestartet (30s Intervall)."


def time_tracking_stop() -> str:
    with _time_tracker_lock:
        if not _time_tracker["running"]:
            return "Zeiterfassung ist nicht aktiv."
        _time_tracker["running"] = False
        _time_tracker["start_time"] = None
        _time_tracker["current_app"] = ""
    # Wake the tracking thread immediately instead of waiting up to 30s
    _time_tracker_stop_event.set()
    return "Zeiterfassung gestoppt."


def time_tracking_report(days: int = 1) -> list[dict]:
    db = _get_db()
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    rows = db.execute(
        """SELECT app_name, SUM(duration_sec) as total_sec, tracked_date
           FROM time_tracking
           WHERE tracked_date >= ?
           GROUP BY app_name, tracked_date
           ORDER BY total_sec DESC""",
        (cutoff,),
    ).fetchall()
    result = []
    for r in rows:
        total = r["total_sec"]
        hours = total // 3600
        mins = (total % 3600) // 60
        result.append({
            "app": r["app_name"],
            "date": r["tracked_date"],
            "duration_sec": total,
            "duration_display": f"{hours}h {mins}m" if hours else f"{mins}m",
        })
    return result


def time_tracking_status() -> dict:
    with _time_tracker_lock:
        return {
            "running": _time_tracker["running"],
            "start_time": _time_tracker.get("start_time"),
            "current_app": _time_tracker.get("current_app", ""),
        }


# ══════════════════════════════════════════════════
#  FOKUS-MODUS (DB-backed + hosts file)
# ══════════════════════════════════════════════════

def _detect_focus_mode_from_db() -> dict:
    """Detect focus mode state from DB (primary) and hosts file (fallback)."""
    state: dict = {"active": False, "blocked_sites": [], "backup": None}
    try:
        db = _get_db()
        rows = db.execute("SELECT domain FROM focus_blocked_domains ORDER BY domain").fetchall()
        if rows:
            state["active"] = True
            state["blocked_sites"] = [r["domain"] for r in rows]
            return state
    except Exception:
        pass

    # Fallback: check hosts file for legacy entries
    try:
        content = Path(HOSTS_PATH).read_text(encoding="utf-8")
        if FOCUS_MARKER in content:
            in_block = False
            sites: list[str] = []
            for line in content.split("\n"):
                if FOCUS_MARKER in line and "END" not in line:
                    in_block = True
                    continue
                if f"{FOCUS_MARKER}-END" in line:
                    in_block = False
                    continue
                if in_block and line.strip().startswith("127.0.0.1"):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        sites.append(parts[1])
            if sites:
                state["active"] = True
                state["blocked_sites"] = sites
    except Exception:
        pass
    return state


_focus_mode: dict = {"active": False, "blocked_sites": [], "backup": None}

# Deferred init — will be called on first access or module load


def _init_focus_state() -> None:
    global _focus_mode
    try:
        _focus_mode = _detect_focus_mode_from_db()
    except Exception:
        pass


# Try to init, but don't fail module load if DB isn't ready
try:
    _init_focus_state()
except Exception:
    pass

DEFAULT_BLOCK = [
    "youtube.com", "www.youtube.com",
    "reddit.com", "www.reddit.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com",
]


def focus_mode_on(sites: str = "") -> str:
    """Activate focus mode — block distracting sites via hosts file + DB tracking."""
    if _focus_mode["active"]:
        return "Fokus-Modus ist bereits aktiv."

    block_list = DEFAULT_BLOCK
    if sites:
        block_list = [s.strip() for s in sites.split(",") if s.strip()]

    # Validate each domain properly
    validated: list[str] = []
    for s in block_list:
        domain = _validate_domain(s)
        if domain:
            validated.append(domain)
    block_list = validated

    if not block_list:
        return {"error": t("validation.noDomains")}

    try:
        hosts = Path(HOSTS_PATH)
        original = hosts.read_text(encoding="utf-8")
        _focus_mode["backup"] = original

        # Add blocks — ensure trailing newline before marker
        separator = "" if original.endswith("\n") else "\n"
        lines = [f"{separator}{FOCUS_MARKER}"]
        for site in block_list:
            lines.append(f"127.0.0.1 {site}")
        lines.append(f"{FOCUS_MARKER}-END\n")

        # Write to temp file first, then replace atomically to prevent corruption
        import tempfile
        new_content = original + "\n".join(lines)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(hosts.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(new_content)
            Path(tmp_path).replace(hosts)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        # Flush DNS
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)

        # Track in DB
        db = _get_db()
        db.execute("DELETE FROM focus_blocked_domains")
        for site in block_list:
            db.execute("INSERT INTO focus_blocked_domains (domain) VALUES (?)", (site,))
        db.commit()

        _focus_mode["active"] = True
        _focus_mode["blocked_sites"] = block_list
        return f"Fokus-Modus aktiv — {len(block_list)} Seiten blockiert."
    except PermissionError:
        return {"error": t("error.adminRequired")}
    except Exception as e:
        return {"error": t("error.generic", error=str(e))}


def focus_mode_off() -> str:
    """Deactivate focus mode — restore hosts file."""
    # Also check hosts file directly in case state was lost on restart
    if not _focus_mode["active"]:
        try:
            content = Path(HOSTS_PATH).read_text(encoding="utf-8")
            if FOCUS_MARKER not in content:
                return "Fokus-Modus ist nicht aktiv."
        except Exception:
            return "Fokus-Modus ist nicht aktiv."

    try:
        hosts = Path(HOSTS_PATH)
        content = hosts.read_text(encoding="utf-8")

        # Remove lexa focus lines
        cleaned: list[str] = []
        skip = False
        for line in content.split("\n"):
            if FOCUS_MARKER in line and "END" not in line:
                skip = True
                continue
            if f"{FOCUS_MARKER}-END" in line:
                skip = False
                continue
            if not skip:
                cleaned.append(line)

        # Write to temp file first, then replace atomically to prevent corruption
        import tempfile
        new_content = "\n".join(cleaned)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(hosts.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(new_content)
            Path(tmp_path).replace(hosts)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)

        # Clear DB tracking
        db = _get_db()
        db.execute("DELETE FROM focus_blocked_domains")
        db.commit()

        _focus_mode["active"] = False
        _focus_mode["blocked_sites"] = []
        return "Fokus-Modus deaktiviert — alle Seiten wieder erreichbar."
    except PermissionError:
        return {"error": t("error.adminRequiredShort")}
    except Exception as e:
        return {"error": t("error.generic", error=str(e))}


def focus_mode_status() -> dict:
    return {
        "active": _focus_mode["active"],
        "blocked_sites": _focus_mode["blocked_sites"],
    }


# ══════════════════════════════════════════════════
#  PRODUCTIVITY STATS (for dashboard)
# ══════════════════════════════════════════════════

def weekly_stats(days: int = 7) -> list[dict]:
    """Gibt tägl. Statistiken der letzten N Tage zurück (todos_done, pomodoros, habits_done)."""
    days = max(1, min(days, 30))
    db = _get_db()
    today = date.today()
    cutoff = (today - timedelta(days=days - 1)).isoformat()

    # Batch query: todos done per day
    todos_by_date: dict[str, int] = {}
    for row in db.execute(
        "SELECT date(completed_at) as d, COUNT(*) as c FROM todos WHERE status='done' AND date(completed_at) >= ? GROUP BY d",
        (cutoff,),
    ).fetchall():
        if row["d"]:
            todos_by_date[row["d"]] = row["c"]

    # Batch query: pomodoros per day
    pomo_by_date: dict[str, int] = {}
    for row in db.execute(
        "SELECT date(started_at) as d, COUNT(*) as c FROM pomodoro_sessions WHERE completed=1 AND date(started_at) >= ? GROUP BY d",
        (cutoff,),
    ).fetchall():
        if row["d"]:
            pomo_by_date[row["d"]] = row["c"]

    # Batch query: habits done per day
    habits_by_date: dict[str, int] = {}
    for row in db.execute(
        """SELECT hl.log_date as d, COUNT(DISTINCT h.id) as c FROM habits h
           JOIN habit_logs hl ON h.id = hl.habit_id
           WHERE hl.log_date >= ? AND hl.count >= h.target
           GROUP BY hl.log_date""",
        (cutoff,),
    ).fetchall():
        if row["d"]:
            habits_by_date[row["d"]] = row["c"]

    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        label = (today - timedelta(days=i)).strftime("%a") if i > 0 else "Heute"
        result.append({
            "date": d,
            "label": label,
            "todos_done": todos_by_date.get(d, 0),
            "pomodoros": pomo_by_date.get(d, 0),
            "habits_done": habits_by_date.get(d, 0),
        })
    return result


def productivity_stats() -> dict:
    db = _get_db()
    today = date.today().isoformat()
    open_todos = db.execute("SELECT COUNT(*) as c FROM todos WHERE status IN ('open','in_progress')").fetchone()["c"]
    done_today = db.execute(
        "SELECT COUNT(*) as c FROM todos WHERE status = 'done' AND date(completed_at) = ?",
        (today,),
    ).fetchone()["c"]
    pomodoros_today = db.execute(
        "SELECT COUNT(*) as c FROM pomodoro_sessions WHERE completed = 1 AND date(started_at) = ?",
        (today,),
    ).fetchone()["c"]
    habits_total = db.execute("SELECT COUNT(*) as c FROM habits").fetchone()["c"]
    habits_done = db.execute(
        """SELECT COUNT(DISTINCT h.id) as c FROM habits h
           JOIN habit_logs hl ON h.id = hl.habit_id
           WHERE hl.log_date = ? AND hl.count >= h.target""",
        (today,),
    ).fetchone()["c"]
    return {
        "open_todos": open_todos,
        "done_today": done_today,
        "pomodoros_today": pomodoros_today,
        "habits_total": habits_total,
        "habits_done_today": habits_done,
        "focus_mode": _focus_mode["active"],
        "time_tracking": _time_tracker["running"],
    }
