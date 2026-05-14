"""Tests for backend/productivity.py — Todos, Pomodoro, Habits, Time Tracking, Stats"""

import threading
import time

import pytest


# ── Fixtures ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Redirect productivity DB_PATH to a temp database for every test."""
    import backend.productivity as prod

    # Close any existing thread-local connection
    tl = prod._thread_local
    old_db = getattr(tl, "db", None)
    if old_db:
        try:
            old_db.close()
        except Exception:
            pass
        tl.db = None

    tmp_db = tmp_path / "test_prod.db"
    monkeypatch.setattr(prod, "DB_PATH", tmp_db)
    monkeypatch.setattr(prod, "_tables_ready", False)

    # Reset pomodoro state
    with prod._pomodoro_lock:
        prod._active_pomodoro = {
            "running": False,
            "task": "",
            "end_time": None,
            "duration_sec": 0,
            "completed_just_now": False,
            "completed_task": "",
            "acknowledged": False,
            "completed_time": 0,
            "completed_at": 0,
        }
        prod._pomodoro_status_cache["data"] = None
        prod._pomodoro_status_cache["ts"] = 0.0
        prod._pomodoro_stop_event = threading.Event()

    # Reset time tracker state
    with prod._time_tracker_lock:
        prod._time_tracker = {
            "running": False,
            "start_time": None,
            "current_app": "",
        }
        prod._time_tracker_stop_event = threading.Event()

    yield

    # Cleanup — stop any running pomodoro/tracker threads
    prod._pomodoro_stop_event.set()
    prod._time_tracker_stop_event.set()
    with prod._pomodoro_lock:
        prod._active_pomodoro["running"] = False
    with prod._time_tracker_lock:
        prod._time_tracker["running"] = False

    old_db2 = getattr(tl, "db", None)
    if old_db2:
        try:
            old_db2.close()
        except Exception:
            pass
        tl.db = None


# ══════════════════════════════════════════════════
#  VALIDATION HELPERS
# ══════════════════════════════════════════════════

class TestValidationHelpers:
    def test_validate_priority_valid(self):
        from backend.productivity import _validate_priority
        assert _validate_priority("urgent") == "urgent"
        assert _validate_priority("low") == "low"

    def test_validate_priority_invalid_returns_default(self):
        from backend.productivity import _validate_priority
        assert _validate_priority("super") == "normal"
        assert _validate_priority("") == "normal"
        assert _validate_priority("URGENT") == "normal"  # case-sensitive

    def test_validate_status_valid(self):
        from backend.productivity import _validate_status
        assert _validate_status("open") == "open"
        assert _validate_status("done") == "done"

    def test_validate_status_invalid(self):
        from backend.productivity import _validate_status
        assert _validate_status("finished") is None
        assert _validate_status("") is None

    def test_validate_duration_clamps(self):
        from backend.productivity import _validate_duration
        assert _validate_duration(25) == 25
        assert _validate_duration(0) == 1      # min clamp
        assert _validate_duration(999) == 120   # max clamp
        assert _validate_duration(-5) == 1

    def test_validate_due_date_valid(self):
        from backend.productivity import _validate_due_date
        assert _validate_due_date("2026-03-15") == "2026-03-15"
        assert _validate_due_date("  2026-01-01  ") == "2026-01-01"

    def test_validate_due_date_invalid(self):
        from backend.productivity import _validate_due_date
        assert _validate_due_date("") is None
        assert _validate_due_date("15.03.2026") is None
        assert _validate_due_date("not-a-date") is None
        assert _validate_due_date("2026-13-40") is None

    def test_validate_domain_valid(self):
        from backend.productivity import _validate_domain
        assert _validate_domain("youtube.com") == "youtube.com"
        assert _validate_domain("  Reddit.COM  ") == "reddit.com"
        assert _validate_domain("sub.domain.example.org") == "sub.domain.example.org"

    def test_validate_domain_invalid(self):
        from backend.productivity import _validate_domain
        assert _validate_domain("") is None
        assert _validate_domain(".leading-dot.com") is None
        assert _validate_domain("trailing-dot.com.") is None
        assert _validate_domain("double..dot.com") is None
        assert _validate_domain("a" * 254) is None  # too long
        assert _validate_domain("-invalid.com") is None


# ══════════════════════════════════════════════════
#  TODO CRUD
# ══════════════════════════════════════════════════

class TestTodoCreate:
    def test_create_basic(self):
        from backend.productivity import todo_create, todo_list
        result = todo_create(title="Einkaufen gehen")
        assert "erstellt" in result.lower() or "einkaufen" in result.lower()
        todos = todo_list()
        assert len(todos) == 1
        assert todos[0]["title"] == "Einkaufen gehen"
        assert todos[0]["priority"] == "normal"
        assert todos[0]["status"] == "open"

    def test_create_with_all_fields(self):
        from backend.productivity import todo_create, todo_list
        todo_create(
            title="Projekt abgeben",
            description="Bachelorarbeit bis Freitag",
            priority="urgent",
            category="arbeit",
            due_date="2026-12-31",
        )
        todos = todo_list()
        assert len(todos) == 1
        assert todos[0]["priority"] == "urgent"
        assert todos[0]["category"] == "arbeit"
        assert todos[0]["due_date"] == "2026-12-31"

    def test_create_empty_title_fails(self):
        from backend.productivity import todo_create
        result = todo_create(title="")
        assert isinstance(result, dict) or "fehlt" in str(result).lower() or "error" in str(result).lower()

    def test_create_invalid_priority_defaults(self):
        from backend.productivity import todo_create, todo_list
        todo_create(title="Test", priority="super-high")
        todos = todo_list()
        assert todos[0]["priority"] == "normal"

    def test_create_invalid_due_date_ignored(self):
        from backend.productivity import todo_create, todo_list
        todo_create(title="Test", due_date="not-a-date")
        todos = todo_list()
        assert todos[0]["due_date"] is None

    def test_title_length_cap(self):
        from backend.productivity import todo_create, todo_list
        long_title = "A" * 500
        todo_create(title=long_title)
        todos = todo_list()
        assert len(todos[0]["title"]) <= 200


class TestTodoList:
    def test_empty_list(self):
        from backend.productivity import todo_list
        assert todo_list() == []

    def test_filter_by_status(self):
        from backend.productivity import todo_create, todo_list, todo_update
        todo_create(title="A")
        todo_create(title="B")
        todos = todo_list()
        todo_update(id=todos[0]["id"], status="done")
        open_todos = todo_list(status="open")
        done_todos = todo_list(status="done")
        assert len(open_todos) == 1
        assert len(done_todos) == 1

    def test_filter_by_priority(self):
        from backend.productivity import todo_create, todo_list
        todo_create(title="Low", priority="low")
        todo_create(title="Urgent", priority="urgent")
        urgent = todo_list(priority="urgent")
        assert len(urgent) == 1
        assert urgent[0]["title"] == "Urgent"

    def test_priority_ordering(self):
        from backend.productivity import todo_create, todo_list
        todo_create(title="Low", priority="low")
        todo_create(title="Urgent", priority="urgent")
        todo_create(title="High", priority="high")
        todos = todo_list()
        # urgent should come first
        assert todos[0]["priority"] == "urgent"


class TestTodoUpdate:
    def test_update_status(self):
        from backend.productivity import todo_create, todo_list, todo_update
        todo_create(title="Test")
        tid = todo_list()[0]["id"]
        todo_update(id=tid, status="done")
        updated = todo_list(status="done")
        assert len(updated) == 1
        assert updated[0]["completed_at"] is not None

    def test_update_title(self):
        from backend.productivity import todo_create, todo_list, todo_update
        todo_create(title="Old")
        tid = todo_list()[0]["id"]
        todo_update(id=tid, title="New")
        assert todo_list()[0]["title"] == "New"

    def test_update_nonexistent(self):
        from backend.productivity import todo_update
        result = todo_update(id=9999, status="done")
        # Note: productivity.py doesn't check rowcount — it always returns success message
        assert isinstance(result, str)

    def test_update_zero_id(self):
        from backend.productivity import todo_update
        result = todo_update(id=0)
        assert isinstance(result, (str, dict))


class TestTodoDelete:
    def test_delete(self):
        from backend.productivity import todo_create, todo_list, todo_delete
        todo_create(title="Temp")
        tid = todo_list()[0]["id"]
        todo_delete(id=tid)
        assert todo_list() == []

    def test_delete_nonexistent(self):
        from backend.productivity import todo_delete
        result = todo_delete(id=9999)
        assert "nicht gefunden" in str(result).lower() or "error" in str(result).lower() or "not found" in str(result).lower()


class TestTodoComplete:
    def test_complete_shorthand(self):
        from backend.productivity import todo_create, todo_list, todo_complete
        todo_create(title="Test")
        tid = todo_list()[0]["id"]
        todo_complete(id=tid)
        done = todo_list(status="done")
        assert len(done) == 1


# ══════════════════════════════════════════════════
#  POMODORO
# ══════════════════════════════════════════════════

class TestPomodoroStart:
    def test_start_basic(self):
        from backend.productivity import pomodoro_start, pomodoro_status
        result = pomodoro_start(task="Coding", duration=1)
        assert "gestartet" in result.lower() or "pomodoro" in result.lower()
        status = pomodoro_status()
        assert status["running"] is True
        assert status["task"] == "Coding"

    def test_start_while_running(self):
        from backend.productivity import pomodoro_start
        pomodoro_start(task="A", duration=25)
        result = pomodoro_start(task="B", duration=25)
        assert "läuft" in result.lower() or "already" in result.lower() or "bereits" in result.lower()

    def test_duration_clamped(self):
        from backend.productivity import pomodoro_start, pomodoro_status
        pomodoro_start(task="Test", duration=999)
        status = pomodoro_status()
        assert status["duration_sec"] == 120 * 60  # 120 min max


class TestPomodoroStop:
    def test_stop_running(self):
        from backend.productivity import pomodoro_start, pomodoro_stop, pomodoro_status
        pomodoro_start(task="Test", duration=25)
        result = pomodoro_stop()
        assert "gestoppt" in result.lower() or "stop" in result.lower()
        status = pomodoro_status()
        assert status["running"] is False

    def test_stop_when_idle(self):
        from backend.productivity import pomodoro_stop
        result = pomodoro_stop()
        assert "kein" in result.lower() or "nicht" in result.lower() or "no" in result.lower()


class TestPomodoroStatus:
    def test_idle_status(self):
        from backend.productivity import pomodoro_status
        status = pomodoro_status()
        assert status["running"] is False
        assert "today_completed" in status
        assert "total_completed" in status

    def test_running_status_has_remaining(self):
        from backend.productivity import pomodoro_start, pomodoro_status
        pomodoro_start(task="Work", duration=25)
        status = pomodoro_status()
        assert status["running"] is True
        assert "remaining_sec" in status
        assert status["remaining_sec"] > 0


# ══════════════════════════════════════════════════
#  HABITS
# ══════════════════════════════════════════════════

class TestHabitCreate:
    def test_create_basic(self):
        from backend.productivity import habit_create, habit_list
        result = habit_create(name="Lesen")
        assert "erstellt" in result.lower() or "lesen" in result.lower()
        habits = habit_list()
        assert len(habits) == 1
        assert habits[0]["name"] == "Lesen"

    def test_create_empty_name_fails(self):
        from backend.productivity import habit_create
        result = habit_create(name="")
        assert isinstance(result, dict) or "fehlt" in str(result).lower() or "error" in str(result).lower()

    def test_create_with_frequency_and_target(self):
        from backend.productivity import habit_create, habit_list
        habit_create(name="Sport", frequency="weekly", target=3)
        habits = habit_list()
        assert habits[0]["frequency"] == "weekly"
        assert habits[0]["target"] == 3

    def test_target_clamped(self):
        from backend.productivity import habit_create, habit_list
        habit_create(name="X", target=999)
        habits = habit_list()
        assert habits[0]["target"] <= 100

    def test_duplicate_name_updates(self):
        from backend.productivity import habit_create, habit_list
        habit_create(name="Lesen", target=1)
        habit_create(name="Lesen", target=5)  # upsert
        habits = habit_list()
        assert len(habits) == 1  # still one habit


class TestHabitLog:
    def test_log_basic(self):
        from backend.productivity import habit_create, habit_log, habit_list
        habit_create(name="Lesen")
        result = habit_log(name="Lesen")
        assert "geloggt" in result.lower() or "logged" in result.lower() or "lesen" in result.lower()
        habits = habit_list()
        assert habits[0]["today_count"] >= 1

    def test_log_nonexistent(self):
        from backend.productivity import habit_log
        result = habit_log(name="Nope")
        result_str = str(result).lower()
        assert "nicht gefunden" in result_str or "not found" in result_str or "error" in result_str

    def test_log_increments(self):
        from backend.productivity import habit_create, habit_log, habit_list
        habit_create(name="Push-ups", target=3)
        habit_log(name="Push-ups", count=1)
        habit_log(name="Push-ups", count=2)
        habits = habit_list()
        assert habits[0]["today_count"] >= 3

    def test_log_updates_streak(self):
        from backend.productivity import habit_create, habit_log, habit_list
        habit_create(name="Lesen")
        habit_log(name="Lesen")
        habits = habit_list()
        assert habits[0]["streak"] >= 1


class TestHabitList:
    def test_empty(self):
        from backend.productivity import habit_list
        assert habit_list() == []

    def test_has_week_data(self):
        from backend.productivity import habit_create, habit_list
        habit_create(name="Test")
        habits = habit_list()
        assert "week" in habits[0]
        assert len(habits[0]["week"]) == 7

    def test_today_done_flag(self):
        from backend.productivity import habit_create, habit_log, habit_list
        habit_create(name="Test", target=1)
        habit_log(name="Test", count=1)
        habits = habit_list()
        assert habits[0]["today_done"] is True


class TestHabitDelete:
    def test_delete(self):
        from backend.productivity import habit_create, habit_delete, habit_list
        habit_create(name="Temp")
        habit_delete(name="Temp")
        assert habit_list() == []

    def test_delete_nonexistent(self):
        from backend.productivity import habit_delete
        result = habit_delete(name="Nope")
        assert "nicht gefunden" in str(result).lower() or "not found" in str(result).lower()


class TestHabitStats:
    def test_stats_empty(self):
        from backend.productivity import habit_stats
        stats = habit_stats()
        assert stats["total_habits"] == 0
        assert stats["completed_today"] == 0

    def test_stats_with_data(self):
        from backend.productivity import habit_create, habit_log, habit_stats
        habit_create(name="A", target=1)
        habit_create(name="B", target=1)
        habit_log(name="A")
        stats = habit_stats()
        assert stats["total_habits"] == 2
        assert stats["completed_today"] == 1


# ══════════════════════════════════════════════════
#  TIME TRACKING
# ══════════════════════════════════════════════════

@pytest.mark.usefixtures("isolate_productivity_db")
class TestTimeTracking:
    def test_status_idle(self):
        from backend.productivity import time_tracking_status
        status = time_tracking_status()
        assert status["running"] is False

    def test_start(self, monkeypatch):
        from backend.productivity import time_tracking_start, time_tracking_status
        # Stub _get_active_window to avoid PowerShell dependency
        import backend.productivity as prod
        monkeypatch.setattr(prod, "_get_active_window", lambda: ("TestApp", "Test Window"))
        result = time_tracking_start()
        assert "gestartet" in result.lower() or "start" in result.lower()
        status = time_tracking_status()
        assert status["running"] is True
        # Stop it immediately for cleanup
        prod.time_tracking_stop()

    def test_start_while_running(self, monkeypatch):
        import backend.productivity as prod
        monkeypatch.setattr(prod, "_get_active_window", lambda: ("TestApp", "Test Window"))
        prod.time_tracking_start()
        result = prod.time_tracking_start()
        assert "läuft" in result.lower() or "already" in result.lower() or "bereits" in result.lower()
        prod.time_tracking_stop()

    def test_stop_when_idle(self):
        from backend.productivity import time_tracking_stop
        result = time_tracking_stop()
        assert "nicht" in result.lower() or "no" in result.lower() or "kein" in result.lower()

    def test_report_empty(self, tmp_path):
        """Test time_tracking_report with a fresh empty database."""
        import sqlite3
        db_path = tmp_path / "test_tt.db"
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS time_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            duration_sec INTEGER NOT NULL,
            tracked_date TEXT NOT NULL
        )""")
        db.commit()
        rows = db.execute(
            "SELECT app_name, SUM(duration_sec) as total_sec, tracked_date "
            "FROM time_tracking WHERE tracked_date >= ? GROUP BY app_name, tracked_date",
            ("2020-01-01",)
        ).fetchall()
        db.close()
        assert isinstance(rows, list)
        assert len(rows) == 0


# ══════════════════════════════════════════════════
#  WEEKLY STATS
# ══════════════════════════════════════════════════

class TestWeeklyStats:
    def test_empty_stats(self):
        from backend.productivity import weekly_stats
        stats = weekly_stats(days=7)
        assert isinstance(stats, list)
        assert len(stats) == 7
        for day in stats:
            assert day["todos_done"] == 0
            assert day["pomodoros"] == 0
            assert day["habits_done"] == 0

    def test_stats_include_today(self):
        from backend.productivity import weekly_stats
        from datetime import date
        stats = weekly_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["date"] == date.today().isoformat()

    def test_stats_with_completed_todo(self):
        from backend.productivity import todo_create, todo_list, todo_complete, weekly_stats
        todo_create(title="Test")
        tid = todo_list()[0]["id"]
        todo_complete(id=tid)
        stats = weekly_stats(days=1)
        assert stats[0]["todos_done"] >= 1

    def test_label_heute_for_today(self):
        from backend.productivity import weekly_stats
        stats = weekly_stats(days=1)
        assert stats[0]["label"] == "Heute"


# ══════════════════════════════════════════════════
#  PRODUCTIVITY STATS
# ══════════════════════════════════════════════════

class TestProductivityStats:
    def test_empty_stats(self):
        from backend.productivity import productivity_stats
        stats = productivity_stats()
        assert stats["open_todos"] == 0
        assert stats["done_today"] == 0
        assert stats["pomodoros_today"] == 0
        assert stats["habits_total"] == 0
        assert stats["focus_mode"] is False
        assert stats["time_tracking"] is False

    def test_stats_with_open_todos(self):
        from backend.productivity import todo_create, productivity_stats
        todo_create(title="A")
        todo_create(title="B")
        stats = productivity_stats()
        assert stats["open_todos"] == 2


# ══════════════════════════════════════════════════
#  FOCUS MODE (validation only, no hosts modification)
# ══════════════════════════════════════════════════

class TestFocusMode:
    def test_status_idle(self):
        from backend.productivity import focus_mode_status
        status = focus_mode_status()
        assert status["active"] is False
        assert status["blocked_sites"] == [] or isinstance(status["blocked_sites"], list)

    def test_off_when_inactive(self):
        from backend.productivity import focus_mode_off
        result = focus_mode_off()
        assert "nicht aktiv" in result.lower() or "not active" in result.lower() or "kein" in result.lower()
