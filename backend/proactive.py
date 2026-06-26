"""Lexa Proactive Engine — Generiert kontextbezogene Vorschlaege basierend auf User-Patterns.

Regelbasiert fuer Performance (kein AI-Call). Prueft:
- Tageszeit + uebliche Aktivitaeten
- Offene Todos, Pomodoro-Status, Habits
- App-Kontext, Inaktivitaet, Feierabend
- Kalender-Erinnerungen (10-15 Min vor Termin)
- Wetter-Warnungen (Regen, Kaelte)
- E-Mail-Benachrichtigungen (neue ungelesene Mails)
- Akku- und Festplatten-Warnungen
- Morgen-Briefing (7-9 Uhr) + Abend-Zusammenfassung (18-20 Uhr)
- Cooldown-System gegen Spam (gleicher Typ max alle 30 Min)

Thread-safe, asyncio-kompatibel.
"""

import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger("lexa.proactive")


# ══════════════════════════════════════════════════
#  DEFAULT SETTINGS — each check individually toggleable
# ══════════════════════════════════════════════════

DEFAULT_PROACTIVE_SETTINGS: dict[str, bool] = {
    "morning_briefing": True,
    "calendar_reminder": True,
    "weather_warning": True,
    "email_notification": True,
    "battery_warning": True,
    "disk_warning": True,
    "evening_summary": True,
    # Existing checks
    "time_based": True,
    "productivity": True,
    "patterns": True,
    "idle": True,
    "app_context": True,
}


# ══════════════════════════════════════════════════
#  SUGGESTION DATACLASS
# ══════════════════════════════════════════════════

@dataclass
class Suggestion:
    """Ein proaktiver Vorschlag fuer den User."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: str = ""          # "reminder", "shortcut", "health", "productivity", "context",
    # "briefing", "calendar_reminder", "weather_warning",
    # "email_notification", "battery_warning", "disk_warning",
    # "evening_summary"
    title: str = ""
    message: str = ""
    action: Optional[dict] = None  # {"type": "tool", "tool": "start_pomodoro"} oder None
    priority: float = 0.5   # 0-1
    expires_at: Optional[str] = None  # ISO timestamp, wann der Vorschlag irrelevant wird
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict:
        """Serialisierung fuer JSON-API."""
        d = asdict(self)
        if d["action"] is None:
            d.pop("action", None)
        if d["expires_at"] is None:
            d.pop("expires_at", None)
        return d


# ══════════════════════════════════════════════════
#  PROACTIVE ENGINE (Singleton)
# ══════════════════════════════════════════════════

class ProactiveEngine:
    """Singleton-Engine fuer proaktive Vorschlaege. Thread-safe."""

    _instance: Optional["ProactiveEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ProactiveEngine":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._lock = threading.Lock()
        self._generation_lock = threading.Lock()  # Serialisiert _generate_suggestions
        self._suggestions: list[Suggestion] = []
        self._dismissed: set[str] = set()  # Dismissed suggestion IDs
        self._cooldowns: dict[str, float] = {}  # type -> last_shown_timestamp
        self._cooldown_seconds: float = 1800.0  # 30 Minuten
        self._last_activity: float = time.time()
        self._last_check: float = 0.0
        self._check_interval: float = 60.0  # Alle 60 Sekunden
        self._background_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Settings dict — individually toggleable checks
        self._settings: dict[str, bool] = dict(DEFAULT_PROACTIVE_SETTINGS)

        # ── State tracking for new checks ──
        self._last_briefing_date: Optional[str] = None        # ISO date of last morning briefing
        self._last_evening_date: Optional[str] = None          # ISO date of last evening summary
        self._reminded_events: set[str] = set()                # Calendar event IDs already reminded
        self._last_weather_check: float = 0.0                  # timestamp of last weather check
        self._last_email_check: float = 0.0                    # timestamp of last email check
        self._last_unread_count: int = 0                       # unread email count at last check
        self._email_baseline_set: bool = False                 # True once the first email check ran
        self._last_disk_check: float = 0.0                     # timestamp of last disk check

        self._initialized = True
        logger.info("ProactiveEngine initialisiert (erweitert)")

    # ──────────────────────────────────────────────
    #  SETTINGS ACCESS
    # ──────────────────────────────────────────────

    def get_settings(self) -> dict[str, bool]:
        """Return a copy of the current proactive settings."""
        return dict(self._settings)

    def update_settings(self, updates: dict[str, bool]) -> dict[str, bool]:
        """Update individual settings. Returns the full settings dict."""
        for key, val in updates.items():
            if key in self._settings and isinstance(val, bool):
                self._settings[key] = val
        return dict(self._settings)

    def start_background(self) -> None:
        """Startet den Background-Loop fuer periodische Suggestion-Generierung."""
        if self._background_thread and self._background_thread.is_alive():
            return
        self._stop_event.clear()
        self._background_thread = threading.Thread(
            target=self._background_loop, daemon=True, name="proactive-engine"
        )
        self._background_thread.start()
        logger.info("ProactiveEngine Background-Loop gestartet")

    def stop_background(self) -> None:
        """Stoppt den Background-Loop."""
        self._stop_event.set()
        if self._background_thread:
            self._background_thread.join(timeout=5)
        logger.info("ProactiveEngine Background-Loop gestoppt")

    def _background_loop(self) -> None:
        """Periodischer Loop: Alle 60s neue Vorschlaege generieren."""
        while not self._stop_event.is_set():
            try:
                self._generate_suggestions()
            except Exception as e:
                logger.error(f"ProactiveEngine Fehler: {e}", exc_info=True)
            # Warte 60s oder bis Stop-Signal
            self._stop_event.wait(timeout=self._check_interval)

    def record_activity(self) -> None:
        """Markiert User-Aktivitaet (fuer Idle-Detection)."""
        self._last_activity = time.time()

    def get_suggestions(self, context: Optional[dict] = None) -> list[dict]:
        """Aktuelle Vorschlaege abrufen. Optional mit Kontext fuer On-Demand-Generierung."""
        # On-Demand: Auch sofort generieren wenn genug Zeit vergangen.
        # respect_interval=True verhindert doppelte teure Laeufe parallel zum
        # Background-Loop (Lock + erneute Gate-Pruefung innerhalb des Locks).
        try:
            self._generate_suggestions(context, respect_interval=True)
        except Exception as e:
            logger.error(f"On-Demand Suggestion-Fehler: {e}", exc_info=True)

        with self._lock:
            # Abgelaufene Vorschlaege entfernen
            now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            active = []
            for s in self._suggestions:
                if s.id in self._dismissed:
                    continue
                if s.expires_at and s.expires_at < now_iso:
                    continue
                active.append(s)
            self._suggestions = active
            return [s.to_dict() for s in sorted(active, key=lambda x: x.priority, reverse=True)]

    def dismiss_suggestion(self, suggestion_id: str) -> bool:
        """Vorschlag als dismissed markieren."""
        with self._lock:
            self._dismissed.add(suggestion_id)
            self._suggestions = [s for s in self._suggestions if s.id != suggestion_id]
            return True

    def accept_suggestion(self, suggestion_id: str) -> Optional[dict]:
        """Vorschlag akzeptieren — gibt die Action zurueck und entfernt ihn."""
        with self._lock:
            for s in self._suggestions:
                if s.id == suggestion_id:
                    action = s.action
                    self._suggestions.remove(s)
                    self._dismissed.add(suggestion_id)
                    return action
        return None

    # ──────────────────────────────────────────────
    #  SUGGESTION GENERATION (regelbasiert)
    # ──────────────────────────────────────────────

    def _generate_suggestions(
        self, context: Optional[dict] = None, respect_interval: bool = False
    ) -> None:
        """Generiert neue Vorschlaege basierend auf Regeln. KEIN AI-Call.

        Serialisiert ueber _generation_lock, damit On-Demand-Calls und der
        Background-Loop die teuren Checks (Kalender/Wetter/IMAP) nicht doppelt
        ausfuehren. Bei respect_interval=True wird das Zeit-Gate innerhalb des
        Locks geprueft, sodass nur ein Lauf pro Intervall stattfindet.
        """
        with self._generation_lock:
            if respect_interval and (time.time() - self._last_check) < self._check_interval:
                return
            self._generate_suggestions_locked(context)

    def _generate_suggestions_locked(self, context: Optional[dict] = None) -> None:
        """Eigentliche Generierung. Nur unter gehaltenem _generation_lock aufrufen."""
        self._last_check = time.time()
        new_suggestions: list[Suggestion] = []

        s = self._settings

        # Existing checks
        if s.get("time_based", True):
            new_suggestions.extend(self._check_time_based())
        if s.get("productivity", True):
            new_suggestions.extend(self._check_productivity())
        if s.get("patterns", True):
            new_suggestions.extend(self._check_patterns())
        if s.get("idle", True):
            new_suggestions.extend(self._check_idle())

        if context and s.get("app_context", True):
            new_suggestions.extend(self._check_app_context(context))

        # ── New checks ──
        if s.get("morning_briefing", True):
            new_suggestions.extend(self._check_morning_briefing())
        if s.get("calendar_reminder", True):
            new_suggestions.extend(self._check_calendar_reminders())
        if s.get("weather_warning", True):
            new_suggestions.extend(self._check_weather_warnings())
        if s.get("email_notification", True):
            new_suggestions.extend(self._check_email_notifications())
        if s.get("battery_warning", True):
            new_suggestions.extend(self._check_battery_warning())
        if s.get("disk_warning", True):
            new_suggestions.extend(self._check_disk_warning())
        if s.get("evening_summary", True):
            new_suggestions.extend(self._check_evening_summary())

        # Cooldown-Filter: gleicher Typ maximal alle 30 Min.
        # Ausnahme: event-spezifische Typen (z.B. calendar_reminder) liefern
        # mehrere inhaltlich verschiedene Vorschlaege mit gleichem Titel fuer
        # verschiedene Termine. Hier wuerde der Typ-Cooldown jeden weiteren
        # Termin-Hinweis unterdruecken; _reminded_events verhindert bereits die
        # Wiederholung desselben Events. Daher Cooldown ueberspringen und den
        # Dedup-Key um die message erweitern.
        cooldown_exempt = {"calendar_reminder"}
        now = time.time()
        filtered: list[Suggestion] = []
        with self._lock:
            for s in new_suggestions:
                exempt = s.type in cooldown_exempt
                last_shown = self._cooldowns.get(s.type, 0)
                if exempt or now - last_shown >= self._cooldown_seconds:
                    # Nicht bereits als dismissed oder vorhanden
                    dedup_key = s.type + s.title + (s.message if exempt else "")
                    existing_keys = {
                        es.type + es.title + (es.message if es.type in cooldown_exempt else "")
                        for es in self._suggestions
                    }
                    if dedup_key not in existing_keys and s.id not in self._dismissed:
                        filtered.append(s)
                        if not exempt:
                            self._cooldowns[s.type] = now

            self._suggestions.extend(filtered)

            # Max 20 aktive Vorschlaege
            if len(self._suggestions) > 20:
                self._suggestions = sorted(
                    self._suggestions, key=lambda x: x.priority, reverse=True
                )[:20]

        if filtered:
            logger.debug(f"ProactiveEngine: {len(filtered)} neue Vorschlaege generiert")

    # ──────────────────────────────────────────────
    #  EXISTING CHECKS (unchanged)
    # ──────────────────────────────────────────────

    def _check_time_based(self) -> list[Suggestion]:
        """Zeitbasierte Vorschlaege: Arbeitsstart, Feierabend."""
        suggestions = []
        now = datetime.now()
        hour = now.hour

        # Work-Start: 7-9 Uhr morgens
        if 7 <= hour <= 9:
            # Pruefe offene Todos fuer Morgen-Greeting
            try:
                from backend.productivity import todo_list
                open_todos = todo_list(status="open")
                urgent = [t for t in open_todos if t.get("priority") in ("urgent", "high")]
                count = len(open_todos)

                if count > 0:
                    msg = f"Guten Morgen! Du hast {count} offene Todos."
                    if urgent:
                        msg += f" Davon {len(urgent)} mit hoher Prioritaet."
                    suggestions.append(Suggestion(
                        type="productivity",
                        title="Guten Morgen!",
                        message=msg,
                        priority=0.7,
                        expires_at=(now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                    ))
            except Exception:
                pass

        # End-of-Day: 17-19 Uhr
        if 17 <= hour <= 19:
            try:
                from backend.productivity import productivity_stats
                stats = productivity_stats()
                done = stats.get("done_today", 0)
                pomos = stats.get("pomodoros_today", 0)

                suggestions.append(Suggestion(
                    type="productivity",
                    title="Feierabend-Zusammenfassung",
                    message=f"Heute: {done} Todos erledigt, {pomos} Pomodoros. Soll ich den Tag zusammenfassen?",
                    action={"type": "summary", "scope": "today"},
                    priority=0.6,
                    expires_at=(now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                ))
            except Exception:
                pass

        return suggestions

    def _check_productivity(self) -> list[Suggestion]:
        """Prueft Todos, Pomodoro, Habits fuer Vorschlaege."""
        suggestions = []
        now = datetime.now()
        hour = now.hour

        # 1. Pomodoro-Pause-Erinnerung
        try:
            from backend.productivity import pomodoro_status
            pomo = pomodoro_status()
            if pomo.get("running"):
                remaining = pomo.get("remaining_sec", 0)
                duration = pomo.get("duration_sec", 1500)
                elapsed = duration - remaining
                # Wenn > 25 Min Arbeitszeit und Pomodoro noch laeuft
                if elapsed > 1500 and remaining > 0:
                    suggestions.append(Suggestion(
                        type="health",
                        title="Pomodoro-Pause",
                        message="Du arbeitest seit ueber 25 Minuten. Zeit fuer eine kurze Pause?",
                        action={"type": "tool", "tool": "pomodoro_stop"},
                        priority=0.8,
                        expires_at=(now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"),
                    ))
            elif pomo.get("completed_just_now"):
                suggestions.append(Suggestion(
                    type="health",
                    title="Pomodoro abgeschlossen!",
                    message=f"'{pomo.get('completed_task', '')}' erledigt! 5 Minuten Pause?",
                    priority=0.9,
                    expires_at=(now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S"),
                ))
        except Exception:
            pass

        # 2. Habit-Erinnerung (abends, 18-22 Uhr)
        if 18 <= hour <= 22:
            try:
                from backend.productivity import habit_stats
                stats = habit_stats()
                total = stats.get("total_habits", 0)
                done = stats.get("completed_today", 0)
                remaining = total - done
                if remaining > 0:
                    suggestions.append(Suggestion(
                        type="reminder",
                        title="Offene Gewohnheiten",
                        message=f"Du hast noch {remaining} Gewohnheit{'en' if remaining > 1 else ''} fuer heute offen.",
                        priority=0.65,
                        expires_at=(now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%S"),
                    ))
            except Exception:
                pass

        # 3. Ueberfaellige Todos
        try:
            from backend.productivity import todo_list
            open_todos = todo_list(status="open")
            today_iso = date.today().isoformat()
            overdue = [
                t for t in open_todos
                if t.get("due_date") and t["due_date"] < today_iso
            ]
            if overdue:
                titles = ", ".join(t.get("title", "?")[:30] for t in overdue[:3])
                more = f" (+{len(overdue) - 3} weitere)" if len(overdue) > 3 else ""
                suggestions.append(Suggestion(
                    type="reminder",
                    title="Ueberfaellige Todos",
                    message=f"{len(overdue)} ueberfaellige Todos: {titles}{more}",
                    priority=0.85,
                    expires_at=(now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S"),
                ))
        except Exception:
            pass

        return suggestions

    def _check_patterns(self) -> list[Suggestion]:
        """User-Pattern basierte Vorschlaege (haeufige Commands etc.)."""
        suggestions = []
        now = datetime.now()
        hour = now.hour

        try:
            from backend.smart_memory import get_common_commands

            # Haeufige Commands zur typischen Uhrzeit vorschlagen
            commands = get_common_commands(5)
            for cmd in commands:
                avg_hour = cmd.get("avg_hour")
                count = cmd.get("count", 0)
                if avg_hour is not None and count >= 10:
                    # Wenn aktuelle Stunde nahe an der durchschnittlichen Nutzungszeit
                    if abs(hour - avg_hour) <= 1:
                        cmd_name = cmd["command"]
                        suggestions.append(Suggestion(
                            type="shortcut",
                            title=f"Haeufiger Befehl: {cmd_name}",
                            message=f"Du fuehrst '{cmd_name}' oft um diese Zeit aus ({count}x insgesamt).",
                            action={"type": "tool", "tool": cmd_name},
                            priority=0.4,
                            expires_at=(now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),
                        ))
        except Exception:
            pass

        return suggestions

    def _check_idle(self) -> list[Suggestion]:
        """Idle-Detection: Vorschlag nach langer Inaktivitaet (>30 Min)."""
        suggestions = []
        idle_seconds = time.time() - self._last_activity

        if idle_seconds > 1800:  # 30 Minuten
            now = datetime.now()
            suggestions.append(Suggestion(
                type="context",
                title="Noch da?",
                message=f"Du warst {int(idle_seconds / 60)} Minuten inaktiv. Soll ich eine Zusammenfassung machen?",
                action={"type": "summary", "scope": "session"},
                priority=0.3,
                expires_at=(now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
            ))

        return suggestions

    def _check_app_context(self, context: dict) -> list[Suggestion]:
        """App-Kontext basierte Vorschlaege."""
        suggestions = []
        current_app = context.get("current_app", "").lower()
        now = datetime.now()

        if not current_app:
            return suggestions

        # Browser offen -> Web-bezogene Vorschlaege
        browser_apps = {"chrome", "firefox", "edge", "brave", "opera", "msedge"}
        if any(b in current_app for b in browser_apps):
            suggestions.append(Suggestion(
                type="context",
                title="Browser erkannt",
                message="Soll ich die aktuelle Seite zusammenfassen oder einen Screenshot machen?",
                action={"type": "tool", "tool": "web_scrape"},
                priority=0.3,
                expires_at=(now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S"),
            ))

        # IDE/Editor offen -> Dev-Vorschlaege
        dev_apps = {"code", "vscode", "pycharm", "intellij", "sublime", "notepad++"}
        if any(d in current_app for d in dev_apps):
            suggestions.append(Suggestion(
                type="context",
                title="Editor erkannt",
                message="Git-Status pruefen oder Pomodoro starten fuer fokussiertes Arbeiten?",
                action={"type": "tool", "tool": "git_status"},
                priority=0.35,
                expires_at=(now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
            ))

        # Terminal offen
        terminal_apps = {"windowsterminal", "cmd", "powershell", "wt"}
        if any(t in current_app for t in terminal_apps):
            suggestions.append(Suggestion(
                type="context",
                title="Terminal erkannt",
                message="Brauchst du Hilfe mit einem Befehl? Ich kann Commands erklaeren.",
                priority=0.2,
                expires_at=(now + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S"),
            ))

        return suggestions

    # ──────────────────────────────────────────────
    #  NEW CHECK 1: MORNING BRIEFING (7:00-9:00)
    # ──────────────────────────────────────────────

    def _check_morning_briefing(self) -> list[Suggestion]:
        """Morgen-Briefing: Kalender + Wetter + E-Mails + Todos. Einmal pro Tag."""
        now = datetime.now()
        hour = now.hour

        # Only between 7:00 and 9:00
        if not (7 <= hour <= 9):
            return []

        # Only once per day
        today_str = date.today().isoformat()
        if self._last_briefing_date == today_str:
            return []

        parts: list[str] = []

        # 1. Calendar events for today
        try:
            from companion.calendar_integration import calendar_today
            cal_result = calendar_today()
            if cal_result.get("success") and cal_result.get("count", 0) > 0:
                count = cal_result["count"]
                events = cal_result.get("events", [])
                event_names = ", ".join(e.get("title", "?")[:25] for e in events[:3])
                more = f" (+{count - 3} weitere)" if count > 3 else ""
                parts.append(f"Kalender: {count} Termine heute — {event_names}{more}")
        except Exception as e:
            logger.debug(f"Morning briefing calendar check failed: {e}")

        # 2. Weather
        try:
            from companion.weather import weather_current
            weather = weather_current()
            if not weather.get("error"):
                temp = weather.get("temp", "?")
                desc = weather.get("description", "")
                city = weather.get("city", "")
                parts.append(f"Wetter ({city}): {temp}C, {desc}")
        except Exception as e:
            logger.debug(f"Morning briefing weather check failed: {e}")

        # 3. Unread emails
        try:
            from companion.communication import email_read
            emails = email_read(count=50, unread_only=True)
            if isinstance(emails, list) and len(emails) > 0:
                parts.append(f"E-Mails: {len(emails)} ungelesen")
        except Exception as e:
            logger.debug(f"Morning briefing email check failed: {e}")

        # 4. Open todos
        try:
            from backend.productivity import todo_list
            open_todos = todo_list(status="open")
            if open_todos:
                urgent = [t for t in open_todos if t.get("priority") in ("urgent", "high")]
                msg = f"Todos: {len(open_todos)} offen"
                if urgent:
                    msg += f" ({len(urgent)} dringend)"
                parts.append(msg)
        except Exception as e:
            logger.debug(f"Morning briefing todo check failed: {e}")

        # Only generate if we have at least one piece of info
        if not parts:
            return []

        self._last_briefing_date = today_str

        briefing_text = "Guten Morgen! Dein Tages-Briefing:\n" + "\n".join(f"  - {p}" for p in parts)

        return [Suggestion(
            type="briefing",
            title="Morgen-Briefing",
            message=briefing_text,
            action={"type": "summary", "scope": "briefing"},
            priority=0.8,
            expires_at=(now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
        )]

    # ──────────────────────────────────────────────
    #  NEW CHECK 2: CALENDAR REMINDERS (every minute)
    # ──────────────────────────────────────────────

    def _check_calendar_reminders(self) -> list[Suggestion]:
        """Kalender-Erinnerung: 10-15 Minuten vor jedem Termin."""
        suggestions = []
        now = datetime.now()

        try:
            from companion.calendar_integration import calendar_today
            cal_result = calendar_today()
            if not cal_result.get("success"):
                return []

            for event in cal_result.get("events", []):
                event_id = event.get("id", "")
                if not event_id or event_id in self._reminded_events:
                    continue

                start_str = event.get("start", "")
                if not start_str or "T" not in start_str:
                    # All-day event, skip
                    continue

                try:
                    # RFC3339 vollstaendig parsen (inkl. Offset/"Z"). Den Offset NICHT
                    # abschneiden — sonst wird die Event-Wandzeit faelschlich als lokale
                    # Zeit interpretiert und der Reminder feuert um den Offset verschoben.
                    event_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue

                # Im selben Bezug vergleichen: tz-aware Event gegen tz-aware now,
                # naives Event gegen das naive lokale now.
                ref_now = datetime.now(event_start.tzinfo) if event_start.tzinfo else now
                minutes_until = (event_start - ref_now).total_seconds() / 60.0

                # Trigger if event starts in 10-15 minutes
                if 10 <= minutes_until <= 15:
                    self._reminded_events.add(event_id)
                    title = event.get("title", "Termin")
                    location = event.get("location", "")
                    start_time = event_start.strftime("%H:%M")

                    msg = f"'{title}' beginnt um {start_time}"
                    if location:
                        msg += f" ({location})"

                    suggestions.append(Suggestion(
                        type="calendar_reminder",
                        title="Termin in Kuerze",
                        message=msg,
                        priority=0.9,
                        expires_at=(now + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S"),
                    ))

        except Exception as e:
            logger.debug(f"Calendar reminder check failed: {e}")

        return suggestions

    # ──────────────────────────────────────────────
    #  NEW CHECK 3: WEATHER WARNINGS (every 2 hours)
    # ──────────────────────────────────────────────

    def _check_weather_warnings(self) -> list[Suggestion]:
        """Wetter-Warnungen: Regen oder Kaelte."""
        now_ts = time.time()

        # Only check every 2 hours (7200 seconds)
        if now_ts - self._last_weather_check < 7200:
            return []

        self._last_weather_check = now_ts
        suggestions = []
        now = datetime.now()

        # Check current weather for temperature
        try:
            from companion.weather import weather_current
            current = weather_current()
            if not current.get("error"):
                temp = current.get("temp")
                if temp is not None and temp < 5:
                    suggestions.append(Suggestion(
                        type="weather_warning",
                        title="Kaelte-Warnung",
                        message=f"Aktuell nur {temp}C — warm anziehen!",
                        priority=0.6,
                        expires_at=(now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                    ))
        except Exception as e:
            logger.debug(f"Weather current check failed: {e}")

        # Check forecast for rain in next 3 hours
        try:
            from companion.weather import weather_forecast
            forecast = weather_forecast(days=1)
            if not forecast.get("error"):
                days = forecast.get("days", [])
                if days:
                    rain_prob = days[0].get("rain_probability", 0)
                    if rain_prob >= 50:
                        suggestions.append(Suggestion(
                            type="weather_warning",
                            title="Regen-Warnung",
                            message=f"Regenwahrscheinlichkeit heute: {rain_prob}% — Regenschirm mitnehmen!",
                            priority=0.6,
                            expires_at=(now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                        ))
        except Exception as e:
            logger.debug(f"Weather forecast check failed: {e}")

        return suggestions

    # ──────────────────────────────────────────────
    #  NEW CHECK 4: EMAIL NOTIFICATIONS (every 5 min)
    # ──────────────────────────────────────────────

    def _check_email_notifications(self) -> list[Suggestion]:
        """E-Mail-Benachrichtigung: Neue ungelesene Mails seit letztem Check."""
        now_ts = time.time()

        # Only check every 5 minutes (300 seconds)
        if now_ts - self._last_email_check < 300:
            return []

        self._last_email_check = now_ts
        now = datetime.now()

        try:
            from companion.communication import email_read
            emails = email_read(count=50, unread_only=True)
            if not isinstance(emails, list):
                return []

            current_count = len(emails)
            prev = self._last_unread_count
            self._last_unread_count = current_count

            # First check ever: just record baseline, no notification.
            # Eigenes Flag statt `prev == 0`, sonst werden nach jedem Nullstand
            # (alle Mails gelesen) neu eintreffende Mails faelschlich als Baseline
            # eingestuft und nicht gemeldet.
            if not self._email_baseline_set:
                self._email_baseline_set = True
                return []

            # Only notify when count increased (new unread mails arrived)
            if current_count > prev:
                new_mails = current_count - prev
                msg = f"{new_mails} neue Mail{'s' if new_mails > 1 else ''} ({current_count} ungelesen insgesamt)"
                return [Suggestion(
                    type="email_notification",
                    title="Neue E-Mails",
                    message=msg,
                    action={"type": "tool", "tool": "email_read"},
                    priority=0.5,
                    expires_at=(now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
                )]

        except Exception as e:
            logger.debug(f"Email notification check failed: {e}")

        return []

    # ──────────────────────────────────────────────
    #  NEW CHECK 5: BATTERY WARNING
    # ──────────────────────────────────────────────

    def _check_battery_warning(self) -> list[Suggestion]:
        """Akku-Warnung: Unter 20% und nicht am Laden."""
        now = datetime.now()

        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery is None:
                # Desktop-PC, kein Akku
                return []

            percent = battery.percent
            plugged = battery.power_plugged

            if percent < 20 and not plugged:
                return [Suggestion(
                    type="battery_warning",
                    title="Akku niedrig",
                    message=f"Akku bei {percent}% — bitte laden!",
                    priority=0.8,
                    expires_at=(now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S"),
                )]
        except Exception as e:
            logger.debug(f"Battery warning check failed: {e}")

        return []

    # ──────────────────────────────────────────────
    #  NEW CHECK 6: DISK SPACE WARNING (every hour)
    # ──────────────────────────────────────────────

    def _check_disk_warning(self) -> list[Suggestion]:
        """Festplatten-Warnung: Ueber 90% belegt."""
        now_ts = time.time()

        # Only check every hour (3600 seconds)
        if now_ts - self._last_disk_check < 3600:
            return []

        self._last_disk_check = now_ts
        now = datetime.now()

        try:
            # Windows-only App: explizit das Systemlaufwerk pruefen, da "/"
            # je nach Arbeitsverzeichnis/Drive nicht zuverlaessig ist.
            system_drive = os.environ.get("SystemDrive", "C:") + os.sep
            usage = shutil.disk_usage(system_drive)
            used_pct = (usage.used / usage.total) * 100

            if used_pct > 90:
                free_gb = usage.free / (1024 ** 3)
                return [Suggestion(
                    type="disk_warning",
                    title="Festplatte fast voll",
                    message=f"Festplatte zu {used_pct:.0f}% belegt — nur noch {free_gb:.1f} GB frei!",
                    priority=0.7,
                    expires_at=(now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S"),
                )]
        except Exception as e:
            logger.debug(f"Disk warning check failed: {e}")

        return []

    # ──────────────────────────────────────────────
    #  NEW CHECK 7: EVENING SUMMARY (18:00-20:00)
    # ──────────────────────────────────────────────

    def _check_evening_summary(self) -> list[Suggestion]:
        """Abend-Zusammenfassung: Todos, Pomodoros, morgen Kalender. Einmal pro Tag."""
        now = datetime.now()
        hour = now.hour

        # Only between 18:00 and 20:00
        if not (18 <= hour <= 20):
            return []

        # Only once per day
        today_str = date.today().isoformat()
        if self._last_evening_date == today_str:
            return []

        parts: list[str] = []

        # 1. Productivity stats for today
        try:
            from backend.productivity import productivity_stats
            stats = productivity_stats()
            done = stats.get("done_today", 0)
            pomos = stats.get("pomodoros_today", 0)
            parts.append(f"Erledigt: {done} Todos, {pomos} Pomodoros")
        except Exception as e:
            logger.debug(f"Evening summary stats failed: {e}")

        # 2. Tomorrow's calendar
        try:
            # We need tomorrow's events — calendar_today() only does today.
            # Use calendar_week() and filter for tomorrow instead.
            from companion.calendar_integration import calendar_week
            week_result = calendar_week()
            if week_result.get("success"):
                tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
                tomorrow_events = [
                    e for e in week_result.get("events", [])
                    if e.get("start", "").startswith(tomorrow_str)
                ]
                if tomorrow_events:
                    names = ", ".join(e.get("title", "?")[:25] for e in tomorrow_events[:3])
                    parts.append(f"Morgen: {len(tomorrow_events)} Termine — {names}")
                else:
                    parts.append("Morgen: Keine Termine")
        except Exception as e:
            logger.debug(f"Evening summary calendar failed: {e}")

        if not parts:
            return []

        self._last_evening_date = today_str

        summary_text = "Dein Tages-Rueckblick:\n" + "\n".join(f"  - {p}" for p in parts)

        return [Suggestion(
            type="evening_summary",
            title="Abend-Zusammenfassung",
            message=summary_text,
            action={"type": "summary", "scope": "evening"},
            priority=0.4,
            expires_at=(now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
        )]


# ══════════════════════════════════════════════════
#  MODULE-LEVEL SINGLETON ACCESS
# ══════════════════════════════════════════════════

def get_engine() -> ProactiveEngine:
    """Gibt die Singleton ProactiveEngine-Instanz zurueck."""
    return ProactiveEngine()


def get_suggestions(context: Optional[dict] = None) -> list[dict]:
    """Shortcut: Aktuelle Vorschlaege abrufen."""
    return get_engine().get_suggestions(context)


def dismiss_suggestion(suggestion_id: str) -> bool:
    """Shortcut: Vorschlag dismissen."""
    return get_engine().dismiss_suggestion(suggestion_id)


def accept_suggestion(suggestion_id: str) -> Optional[dict]:
    """Shortcut: Vorschlag akzeptieren."""
    return get_engine().accept_suggestion(suggestion_id)


def record_activity() -> None:
    """Shortcut: User-Aktivitaet markieren."""
    get_engine().record_activity()


def start_background() -> None:
    """Shortcut: Background-Loop starten."""
    get_engine().start_background()


def stop_background() -> None:
    """Shortcut: Background-Loop stoppen."""
    get_engine().stop_background()


def get_proactive_settings() -> dict[str, bool]:
    """Shortcut: Proactive settings abrufen."""
    return get_engine().get_settings()


def update_proactive_settings(updates: dict[str, bool]) -> dict[str, bool]:
    """Shortcut: Proactive settings aktualisieren."""
    return get_engine().update_settings(updates)
