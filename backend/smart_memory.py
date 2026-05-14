"""Lexa Smart Memory — Lernt User-Patterns, Praeferenzen und Gewohnheiten.
Baut ein persistentes User-Profil auf das ueber Sessions hinweg waechst.

Features:
- UserProfile: Persistentes Profil in SQLite (Preferences, Work Hours, Apps, Commands)
- Pattern Learning: Lernt aus Interaktionen, Commands, App-Nutzung
- Keyword-basierte Praeferenz-Erkennung (kein AI-Call)
- Thread-safe, asyncio-kompatibel
"""

import json
import logging
import os
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("lexa.smart_memory")

_tables_ready: bool = False
_tables_lock = threading.Lock()
_thread_local = threading.local()

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
DB_PATH = Path(_DATA_DIR) / "lexa_memory.db"


# ══════════════════════════════════════════════════
#  DATABASE CONNECTION (thread-local, same pattern as productivity.py)
# ══════════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    """Thread-lokale DB-Verbindung mit Auto-Init. Wiederverwendung pro Thread."""
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

    db = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")
    db.execute("PRAGMA temp_store=MEMORY")
    _init_smart_tables(db)
    _thread_local.db = db
    return db


def _init_smart_tables(db: sqlite3.Connection) -> None:
    """Tabellen fuer Smart Memory erstellen (Double-Check Locking)."""
    global _tables_ready
    if _tables_ready:
        return
    with _tables_lock:
        if _tables_ready:
            return
        _init_smart_tables_inner(db)
        _tables_ready = True


def _init_smart_tables_inner(db: sqlite3.Connection) -> None:
    """Tatsaechliche Tabellenerstellung — wird unter Lock aufgerufen."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            confidence REAL DEFAULT 0.5 CHECK(confidence >= 0.0 AND confidence <= 1.0)
        );

        CREATE TABLE IF NOT EXISTS interaction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now', 'localtime')),
            user_message TEXT,
            tools_used TEXT,
            app_context TEXT,
            hour_of_day INTEGER,
            day_of_week INTEGER
        );

        CREATE TABLE IF NOT EXISTS app_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT NOT NULL,
            timestamp TEXT DEFAULT (datetime('now', 'localtime')),
            hour_of_day INTEGER,
            day_of_week INTEGER
        );

        CREATE TABLE IF NOT EXISTS command_frequency (
            command TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1,
            last_used TEXT DEFAULT (datetime('now', 'localtime')),
            avg_hour REAL
        );

        CREATE INDEX IF NOT EXISTS idx_interaction_log_ts ON interaction_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_interaction_log_hour ON interaction_log(hour_of_day);
        CREATE INDEX IF NOT EXISTS idx_interaction_log_dow ON interaction_log(day_of_week);
        CREATE INDEX IF NOT EXISTS idx_app_usage_name ON app_usage(app_name);
        CREATE INDEX IF NOT EXISTS idx_app_usage_ts ON app_usage(timestamp);
        CREATE INDEX IF NOT EXISTS idx_app_usage_hour ON app_usage(hour_of_day);
        CREATE INDEX IF NOT EXISTS idx_command_freq_count ON command_frequency(count DESC);
    """)
    db.commit()


# ══════════════════════════════════════════════════
#  USER PROFILE — Persistentes Profil-System
# ══════════════════════════════════════════════════

def profile_get(key: str) -> Optional[dict]:
    """Einzelnen Profil-Eintrag lesen. Gibt {key, value, updated_at, confidence} oder None zurueck."""
    if not key or not key.strip():
        return None
    db = _get_db()
    row = db.execute(
        "SELECT key, value, updated_at, confidence FROM user_profile WHERE key = ?",
        (key.strip(),)
    ).fetchone()
    if not row:
        return None
    try:
        val = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        val = row["value"]
    return {
        "key": row["key"],
        "value": val,
        "updated_at": row["updated_at"],
        "confidence": row["confidence"],
    }


def profile_get_all() -> dict[str, Any]:
    """Komplettes Profil als Dict {key: {value, updated_at, confidence}} zurueckgeben."""
    db = _get_db()
    rows = db.execute(
        "SELECT key, value, updated_at, confidence FROM user_profile ORDER BY key"
    ).fetchall()
    result = {}
    for row in rows:
        try:
            val = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            val = row["value"]
        result[row["key"]] = {
            "value": val,
            "updated_at": row["updated_at"],
            "confidence": row["confidence"],
        }
    return result


def profile_set(key: str, value: Any, confidence: float = 0.5) -> str:
    """Profil-Eintrag setzen oder aktualisieren."""
    if not key or not key.strip():
        return "Key darf nicht leer sein."
    key = key.strip()[:200]
    confidence = max(0.0, min(1.0, float(confidence)))
    val_json = json.dumps(value, ensure_ascii=False, default=str)
    if len(val_json) > 50000:
        return "Wert zu gross (max 50KB)."

    db = _get_db()
    db.execute(
        """INSERT INTO user_profile (key, value, updated_at, confidence)
           VALUES (?, ?, datetime('now', 'localtime'), ?)
           ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               updated_at = excluded.updated_at,
               confidence = MAX(user_profile.confidence, excluded.confidence)""",
        (key, val_json, confidence),
    )
    db.commit()
    return f"Profil '{key}' gespeichert."


def profile_delete(key: str) -> str:
    """Profil-Eintrag loeschen."""
    if not key or not key.strip():
        return "Key darf nicht leer sein."
    db = _get_db()
    result = db.execute("DELETE FROM user_profile WHERE key = ?", (key.strip(),))
    db.commit()
    if result.rowcount:
        return f"Profil '{key}' geloescht."
    return f"Profil '{key}' nicht gefunden."


# ══════════════════════════════════════════════════
#  PATTERN LEARNING — Lernt aus Interaktionen
# ══════════════════════════════════════════════════

# Keyword-Mapping fuer Praeferenz-Erkennung (kein AI-Call)
_PREFERENCE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    # (keyword_in_message, preference_key): value_to_set
    "editor": [
        ("vs code", "VS Code"), ("vscode", "VS Code"), ("visual studio code", "VS Code"),
        ("sublime", "Sublime Text"), ("notepad++", "Notepad++"), ("vim", "Vim"),
        ("neovim", "Neovim"), ("intellij", "IntelliJ"), ("pycharm", "PyCharm"),
        ("atom", "Atom"), ("cursor", "Cursor"),
    ],
    "browser": [
        ("chrome", "Chrome"), ("firefox", "Firefox"), ("edge", "Edge"),
        ("brave", "Brave"), ("opera", "Opera"), ("safari", "Safari"),
    ],
    "language": [
        ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"),
        ("java", "Java"), ("c#", "C#"), ("csharp", "C#"), ("c++", "C++"),
        ("rust", "Rust"), ("go", "Go"), ("golang", "Go"), ("ruby", "Ruby"),
        ("php", "PHP"), ("swift", "Swift"), ("kotlin", "Kotlin"),
    ],
    "os": [
        ("windows", "Windows"), ("linux", "Linux"), ("ubuntu", "Ubuntu"),
        ("macos", "macOS"), ("mac os", "macOS"),
    ],
}

# Topic-Keywords fuer Interessen-Erkennung
_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Python": ["python", "pip", "pytest", "django", "flask", "fastapi"],
    "JavaScript": ["javascript", "node", "npm", "react", "vue", "angular"],
    "Machine Learning": ["machine learning", "ml", "neural", "tensorflow", "pytorch", "model training"],
    "Web Development": ["html", "css", "frontend", "backend", "api", "rest"],
    "DevOps": ["docker", "kubernetes", "ci/cd", "pipeline", "deploy"],
    "Gaming": ["game", "gaming", "steam", "spiel", "spielen"],
    "Data Science": ["data science", "pandas", "numpy", "jupyter", "daten"],
    "Cybersecurity": ["security", "hacking", "penetration", "firewall", "verschluesselung"],
    "Automation": ["automatisierung", "automation", "script", "batch", "cron"],
    "Design": ["design", "figma", "photoshop", "ui", "ux"],
}

# Interaction Style Detection
_STYLE_INDICATORS: dict[str, dict[str, list[str]]] = {
    "verbosity": {
        "concise": ["kurz", "knapp", "schnell", "tldr", "zusammenfassung"],
        "detailed": ["detail", "erklaer", "ausfuehrlich", "genau", "schritt fuer schritt"],
    },
    "language": {
        "de": ["auf deutsch", "deutsch", "german"],
        "en": ["auf englisch", "english", "in english"],
    },
}


def learn_from_interaction(
    user_message: str,
    ai_response: str = "",
    tools_used: Optional[list[str]] = None,
    app_context: str = "",
) -> None:
    """Lernt aus einer User-Interaktion. Loggt und extrahiert Praeferenzen."""
    if not user_message:
        return

    now = datetime.now()
    hour = now.hour
    dow = now.weekday()  # 0=Montag

    # 1. Interaktion loggen
    db = _get_db()
    tools_json = json.dumps(tools_used or [], ensure_ascii=False)
    db.execute(
        """INSERT INTO interaction_log (user_message, tools_used, app_context, hour_of_day, day_of_week)
           VALUES (?, ?, ?, ?, ?)""",
        (user_message[:2000], tools_json, app_context[:200], hour, dow),
    )
    db.commit()

    # 2. Praeferenzen extrahieren (Keyword-basiert, kein AI-Call)
    _extract_preferences(user_message)

    # 3. Arbeitszeiten aktualisieren
    _update_work_schedule_from_interaction(hour, dow)

    # 4. Interaktionsstil erkennen
    _detect_interaction_style(user_message)

    logger.debug(f"Smart Memory: Interaktion gelernt (Hour={hour}, DOW={dow})")


def learn_from_command(command: str, context: str = "") -> None:
    """Merkt sich haeufig verwendete Commands mit Durchschnitts-Uhrzeit."""
    if not command or not command.strip():
        return
    command = command.strip()[:500]
    hour = datetime.now().hour

    db = _get_db()
    existing = db.execute(
        "SELECT count, avg_hour FROM command_frequency WHERE command = ?",
        (command,)
    ).fetchone()

    if existing:
        old_count = existing["count"]
        old_avg = existing["avg_hour"] or hour
        new_count = old_count + 1
        # Laufender Durchschnitt
        new_avg = ((old_avg * old_count) + hour) / new_count
        db.execute(
            "UPDATE command_frequency SET count = ?, last_used = datetime('now', 'localtime'), avg_hour = ? WHERE command = ?",
            (new_count, round(new_avg, 2), command),
        )
    else:
        db.execute(
            "INSERT INTO command_frequency (command, count, avg_hour) VALUES (?, 1, ?)",
            (command, float(hour)),
        )
    db.commit()


def learn_app_usage(app_name: str) -> None:
    """Trackt App-Nutzung mit Zeitstempel."""
    if not app_name or not app_name.strip():
        return
    app_name = app_name.strip()[:200]
    now = datetime.now()

    db = _get_db()
    db.execute(
        "INSERT INTO app_usage (app_name, hour_of_day, day_of_week) VALUES (?, ?, ?)",
        (app_name, now.hour, now.weekday()),
    )
    db.commit()

    # Auch im Profil als common_apps aktualisieren (Top 20)
    _update_common_apps()


def _extract_preferences(message: str) -> None:
    """Extrahiert Praeferenzen aus Nachricht via Keyword-Matching (kein AI-Call)."""
    msg_lower = message.lower()

    # Praeferenz-Patterns pruefen
    for pref_key, patterns in _PREFERENCE_PATTERNS.items():
        for keyword, value in patterns:
            if keyword in msg_lower:
                # Nur setzen wenn Kontext auf Praeferenz hindeutet
                pref_indicators = [
                    "nutze", "verwende", "benutze", "bevorzuge", "lieblings",
                    "favorite", "prefer", "use", "open", "oeffne", "starte",
                    "arbeite mit", "programmiere in", "code in",
                ]
                if any(ind in msg_lower for ind in pref_indicators) or pref_key == "language":
                    current = profile_get(f"preferences.{pref_key}")
                    # Erhoehe Confidence wenn gleicher Wert wiederholt
                    if current and current["value"] == value:
                        new_conf = min(1.0, current["confidence"] + 0.1)
                        profile_set(f"preferences.{pref_key}", value, confidence=new_conf)
                    else:
                        profile_set(f"preferences.{pref_key}", value, confidence=0.4)
                    break

    # Topic-Interessen erkennen
    detected_topics = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            detected_topics.append(topic)

    if detected_topics:
        existing = profile_get("topics_of_interest")
        current_topics: list[str] = existing["value"] if existing and isinstance(existing["value"], list) else []
        updated = False
        for topic in detected_topics:
            if topic not in current_topics:
                current_topics.append(topic)
                updated = True
        if updated:
            # Max 30 Topics
            profile_set("topics_of_interest", current_topics[:30], confidence=0.5)


def _detect_interaction_style(message: str) -> None:
    """Erkennt bevorzugten Interaktionsstil (Verbositaet, Sprache, Humor)."""
    msg_lower = message.lower()

    for style_key, options in _STYLE_INDICATORS.items():
        for style_value, keywords in options.items():
            if any(kw in msg_lower for kw in keywords):
                profile_set(f"interaction_style.{style_key}", style_value, confidence=0.5)
                break

    # Humor-Erkennung
    humor_indicators = ["haha", "lol", "witzig", "lustig", "spass", "joke", "funny", ":)", "xd"]
    if any(ind in msg_lower for ind in humor_indicators):
        existing = profile_get("interaction_style.humor")
        conf = 0.4
        if existing and existing["value"] is True:
            conf = min(1.0, existing["confidence"] + 0.05)
        profile_set("interaction_style.humor", True, confidence=conf)


def _update_work_schedule_from_interaction(hour: int, dow: int) -> None:
    """Aktualisiert Arbeitszeiten basierend auf Interaktions-Zeitpunkten."""
    db = _get_db()

    # Letzte 200 Interaktionen analysieren fuer Arbeitszeit-Erkennung
    rows = db.execute(
        "SELECT hour_of_day, day_of_week FROM interaction_log ORDER BY id DESC LIMIT 200"
    ).fetchall()

    if len(rows) < 10:
        return  # Zu wenig Daten

    hours = [r["hour_of_day"] for r in rows]
    hour_counts = Counter(hours)

    # Arbeitszeit: Stunden mit mindestens 5% der Interaktionen
    threshold = len(rows) * 0.05
    active_hours = sorted([h for h, c in hour_counts.items() if c >= threshold])

    if not active_hours:
        return

    work_start = f"{active_hours[0]:02d}:00"
    work_end = f"{active_hours[-1]:02d}:00"

    # Peak-Hours: Top 3 Stunden
    top_hours = hour_counts.most_common(3)
    peak_start = min(h for h, _ in top_hours)
    peak_end = max(h for h, _ in top_hours)
    peak = f"{peak_start:02d}:00-{peak_end + 1:02d}:00"

    work_hours = {
        "start": work_start,
        "end": work_end,
        "peak": peak,
        "active_hours": active_hours,
    }
    profile_set("work_hours", work_hours, confidence=min(0.9, len(rows) / 200))


def _update_common_apps() -> None:
    """Aktualisiert die Liste der meistgenutzten Apps im Profil."""
    db = _get_db()
    rows = db.execute(
        """SELECT app_name, COUNT(*) as freq
           FROM app_usage
           WHERE timestamp >= datetime('now', '-30 days', 'localtime')
           GROUP BY app_name
           ORDER BY freq DESC
           LIMIT 20"""
    ).fetchall()

    if not rows:
        return

    apps = [{"name": r["app_name"], "frequency": r["freq"]} for r in rows]
    profile_set("common_apps", apps, confidence=0.7)


def update_work_schedule() -> str:
    """Manueller Trigger fuer Arbeitszeit-Update basierend auf allen Interaktionen."""
    now = datetime.now()
    _update_work_schedule_from_interaction(now.hour, now.weekday())
    return "Arbeitszeiten aktualisiert."


# ══════════════════════════════════════════════════
#  QUERY FUNCTIONS — Profil-Daten abfragen
# ══════════════════════════════════════════════════

def get_common_commands(limit: int = 20) -> list[dict]:
    """Top N haeufigste Commands zurueckgeben."""
    limit = max(1, min(100, limit))
    db = _get_db()
    rows = db.execute(
        "SELECT command, count, last_used, avg_hour FROM command_frequency ORDER BY count DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_common_apps(limit: int = 20) -> list[dict]:
    """Top N haeufigste Apps (letzte 30 Tage)."""
    limit = max(1, min(100, limit))
    db = _get_db()
    rows = db.execute(
        """SELECT app_name, COUNT(*) as frequency,
                  ROUND(AVG(hour_of_day), 1) as avg_hour
           FROM app_usage
           WHERE timestamp >= datetime('now', '-30 days', 'localtime')
           GROUP BY app_name
           ORDER BY frequency DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_activity_by_hour() -> list[dict]:
    """Interaktions-Verteilung pro Stunde (0-23)."""
    db = _get_db()
    rows = db.execute(
        """SELECT hour_of_day, COUNT(*) as count
           FROM interaction_log
           GROUP BY hour_of_day
           ORDER BY hour_of_day"""
    ).fetchall()
    # Alle 24 Stunden, auch leere
    hour_map = {r["hour_of_day"]: r["count"] for r in rows}
    return [{"hour": h, "count": hour_map.get(h, 0)} for h in range(24)]


def get_activity_by_day() -> list[dict]:
    """Interaktions-Verteilung pro Wochentag (0=Mo bis 6=So)."""
    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    db = _get_db()
    rows = db.execute(
        """SELECT day_of_week, COUNT(*) as count
           FROM interaction_log
           GROUP BY day_of_week
           ORDER BY day_of_week"""
    ).fetchall()
    day_map = {r["day_of_week"]: r["count"] for r in rows}
    return [{"day": d, "name": day_names[d], "count": day_map.get(d, 0)} for d in range(7)]


def get_stats() -> dict:
    """Lern-Statistiken: Anzahl Interaktionen, gelernte Patterns etc."""
    db = _get_db()
    interaction_count = db.execute("SELECT COUNT(*) as c FROM interaction_log").fetchone()["c"]
    profile_count = db.execute("SELECT COUNT(*) as c FROM user_profile").fetchone()["c"]
    command_count = db.execute("SELECT COUNT(*) as c FROM command_frequency").fetchone()["c"]
    app_count = db.execute("SELECT COUNT(DISTINCT app_name) as c FROM app_usage").fetchone()["c"]

    # Zeitraum der Daten
    first_interaction = db.execute(
        "SELECT MIN(timestamp) as t FROM interaction_log"
    ).fetchone()["t"]
    last_interaction = db.execute(
        "SELECT MAX(timestamp) as t FROM interaction_log"
    ).fetchone()["t"]

    # Top Command
    top_cmd = db.execute(
        "SELECT command, count FROM command_frequency ORDER BY count DESC LIMIT 1"
    ).fetchone()

    return {
        "total_interactions": interaction_count,
        "profile_entries": profile_count,
        "unique_commands": command_count,
        "unique_apps": app_count,
        "tracking_since": first_interaction,
        "last_interaction": last_interaction,
        "top_command": dict(top_cmd) if top_cmd else None,
    }


def get_insights_data() -> dict:
    """Sammelt alle relevanten Daten fuer AI-generierte Insights."""
    return {
        "profile": profile_get_all(),
        "stats": get_stats(),
        "activity_by_hour": get_activity_by_hour(),
        "activity_by_day": get_activity_by_day(),
        "common_commands": get_common_commands(10),
        "common_apps": get_common_apps(10),
    }
