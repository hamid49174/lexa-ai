"""
Lexa App-Integrationen — Native Integration mit populaeren Anwendungen.
Browser-Tabs, Spotify, Dateisystem, Clipboard-Intelligenz.

Nur stdlib + ctypes + psutil — keine externen Dependencies (kein pywin32, kein watchdog).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger("lexa.integrations")

# ── Konstanten ────────────────────────────────────────────
_CLIPBOARD_HISTORY_MAX = 20
_RECENT_FILES_SCAN_DIRS = [
    os.path.expanduser("~\\Desktop"),
    os.path.expanduser("~\\Documents"),
    os.path.expanduser("~\\Downloads"),
]
_WATCHER_POLL_INTERVAL = 5  # Sekunden fuer Verzeichnis-Polling
_MAX_RECENT_FILES = 50


# ══════════════════════════════════════════════════════════
#  BROWSER INTEGRATION
# ══════════════════════════════════════════════════════════

def get_browser_tabs(limit: int = 20) -> list[dict[str, str]]:
    """
    Liest die zuletzt besuchten Browser-Tabs aus der Chrome History-DB.
    Chrome speichert History in einer SQLite-DB.

    Args:
        limit: Max Anzahl Eintraege (default 20, max 100).

    Returns:
        [{"url": "...", "title": "...", "last_visit": "..."}]
    """
    limit = max(1, min(100, limit))

    chrome_history = Path(
        os.environ.get("LOCALAPPDATA", ""),
        "Google", "Chrome", "User Data", "Default", "History"
    )

    if not chrome_history.exists():
        logger.debug("Chrome History-DB nicht gefunden: %s", chrome_history)
        return []

    # Chrome sperrt die DB — wir kopieren sie temporaer
    tmp_path = Path(os.environ.get("TEMP", ".")) / "lexa_chrome_history_tmp.db"
    try:
        shutil.copy2(str(chrome_history), str(tmp_path))
    except (PermissionError, OSError) as e:
        logger.debug(f"Chrome History kopieren fehlgeschlagen: {e}")
        return []

    tabs: list[dict[str, str]] = []
    try:
        conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True, timeout=3)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT url, title, last_visit_time FROM urls "
            "ORDER BY last_visit_time DESC LIMIT ?",
            (limit,),
        )
        for row in cursor.fetchall():
            # Chrome speichert Timestamps als Microseconds seit 1601-01-01
            chrome_epoch = row["last_visit_time"]
            if chrome_epoch:
                # Konvertierung: Chrome-Epoch zu Unix-Epoch
                unix_ts = (chrome_epoch / 1_000_000) - 11_644_473_600
                try:
                    visit_time = datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M")
                except (OSError, ValueError, OverflowError):
                    visit_time = ""
            else:
                visit_time = ""

            tabs.append({
                "url": row["url"] or "",
                "title": row["title"] or "",
                "last_visit": visit_time,
            })
        conn.close()
    except (sqlite3.Error, Exception) as e:
        logger.debug(f"Chrome History lesen fehlgeschlagen: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass

    return tabs


def get_current_url() -> str:
    """
    Versucht die aktuelle URL aus dem Browser-Fenstertitel zu parsen.
    Viele Browser zeigen die URL oder den Seitentitel an.

    Returns:
        URL-String oder leerer String.
    """
    try:
        from backend.context_monitor import context_monitor
        window = context_monitor.get_active_window()
        title = window.get("title", "")
        process = window.get("process", "").lower()

        # Nur bei Browser-Prozessen versuchen
        browser_processes = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
        if process not in browser_processes:
            return ""

        # URL aus Titel extrahieren (manche Browser zeigen URL-Fragmente)
        url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        match = url_pattern.search(title)
        if match:
            return match.group(0)

        return ""
    except Exception as e:
        logger.debug(f"get_current_url Fehler: {e}")
        return ""


# ══════════════════════════════════════════════════════════
#  SPOTIFY INTEGRATION (lokal, ueber Window-Titel + Media Keys)
# ══════════════════════════════════════════════════════════

def get_spotify_status() -> dict[str, str]:
    """
    Erkennt den aktuellen Spotify-Song aus dem Fenstertitel.
    Spotify zeigt: "Artist - Song - Spotify" oder "Spotify Free/Premium" (wenn pausiert).

    Returns:
        {"playing": true, "artist": "...", "song": "...", "raw_title": "..."}
    """
    import psutil as _ps

    try:
        for proc in _ps.process_iter(["name", "pid"]):
            if proc.info["name"] and proc.info["name"].lower() == "spotify.exe":
                pid = proc.info["pid"]
                break
        else:
            return {"playing": False, "artist": "", "song": "", "raw_title": "", "error": "Spotify nicht gestartet"}

        # Fenstertitel von Spotify holen
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        titles: list[str] = []

        def _enum_callback(hwnd, _):
            _pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid))
            if _pid.value == pid and user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value:
                        titles.append(buf.value)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)

        # Spotify-Titel parsen
        for title in titles:
            if " - " in title and title.lower() not in ("spotify", "spotify free", "spotify premium"):
                parts = title.split(" - ")
                if len(parts) >= 2:
                    artist = parts[0].strip()
                    song = " - ".join(parts[1:]).strip()
                    # "Spotify" am Ende entfernen wenn vorhanden
                    if song.lower().endswith(" - spotify"):
                        song = song[:-len(" - Spotify")].strip()
                    elif song.lower() == "spotify":
                        song = ""
                    return {
                        "playing": True,
                        "artist": artist,
                        "song": song,
                        "raw_title": title,
                    }

        return {"playing": False, "artist": "", "song": "", "raw_title": titles[0] if titles else ""}

    except Exception as e:
        logger.debug(f"get_spotify_status Fehler: {e}")
        return {"playing": False, "artist": "", "song": "", "raw_title": "", "error": str(e)}


def spotify_control(action: str) -> dict[str, Any]:
    """
    Steuert Spotify via Media-Keys (SendKeys ueber PowerShell).
    Funktioniert systemweit ohne Spotify-API.

    Args:
        action: "play", "pause", "next", "previous"

    Returns:
        {"success": true, "action": "..."}
    """
    # Media Key VK Codes
    _VK_MEDIA_PLAY_PAUSE = 0xB3
    _VK_MEDIA_NEXT = 0xB0
    _VK_MEDIA_PREV = 0xB1

    key_map = {
        "play": _VK_MEDIA_PLAY_PAUSE,
        "pause": _VK_MEDIA_PLAY_PAUSE,
        "next": _VK_MEDIA_NEXT,
        "previous": _VK_MEDIA_PREV,
        "prev": _VK_MEDIA_PREV,
    }

    if action not in key_map:
        return {"success": False, "error": f"Unbekannte Aktion: {action}. Erlaubt: play, pause, next, previous"}

    try:
        import ctypes
        vk = key_map[action]
        # keybd_event(vk, scan, flags, extra)
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)       # Key down
        ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)   # Key up (KEYEVENTF_KEYUP)
        return {"success": True, "action": action}
    except Exception as e:
        logger.warning(f"spotify_control Fehler: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════
#  FILE SYSTEM AWARENESS
# ══════════════════════════════════════════════════════════

def get_recent_files(hours: int = 24, directory: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Gibt kuerzlich geaenderte Dateien zurueck.

    Args:
        hours: Stunden zurueckschauen (1-168, default 24).
        directory: Spezifisches Verzeichnis (optional, sonst Standard-Verzeichnisse).

    Returns:
        [{"path": "...", "name": "...", "size_kb": 123, "modified": "...", "extension": ".py"}]
    """
    hours = max(1, min(168, hours))
    cutoff = time.time() - (hours * 3600)
    results: list[dict[str, Any]] = []

    scan_dirs = [directory] if directory else _RECENT_FILES_SCAN_DIRS

    for scan_dir in scan_dirs:
        scan_path = Path(scan_dir)
        if not scan_path.exists() or not scan_path.is_dir():
            continue

        try:
            # os.scandir ist schneller als Path.iterdir fuer grosse Verzeichnisse
            with os.scandir(str(scan_path)) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file():
                            continue
                        stat = entry.stat()
                        if stat.st_mtime >= cutoff:
                            results.append({
                                "path": entry.path,
                                "name": entry.name,
                                "size_kb": round(stat.st_size / 1024, 1),
                                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                "extension": Path(entry.name).suffix.lower(),
                            })
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError) as e:
            logger.debug(f"Verzeichnis-Scan fehlgeschlagen fuer {scan_dir}: {e}")

    # Nach Aenderungszeit sortieren (neueste zuerst)
    results.sort(key=lambda x: x["modified"], reverse=True)
    return results[:_MAX_RECENT_FILES]


def get_project_context() -> dict[str, Any]:
    """
    Erkennt das aktive Projekt basierend auf dem VS Code Fenstertitel.
    VS Code zeigt: "filename - folder - Visual Studio Code"

    Returns:
        {"project_name": "...", "project_path": "...", "active_file": "...", "detected_from": "..."}
    """
    try:
        from backend.context_monitor import context_monitor
        window = context_monitor.get_active_window()
        title = window.get("title", "")
        process = window.get("process", "").lower()

        result: dict[str, Any] = {
            "project_name": "",
            "project_path": "",
            "active_file": "",
            "detected_from": "",
        }

        # VS Code Detection
        if process in ("code.exe", "code - insiders.exe"):
            result["detected_from"] = "vscode"
            parts = title.split(" - ")
            if len(parts) >= 3:
                # "file.py - project_folder - Visual Studio Code"
                result["active_file"] = parts[0].strip()
                result["project_name"] = parts[1].strip()
            elif len(parts) == 2:
                result["project_name"] = parts[0].strip()

        # PyCharm Detection
        elif "pycharm" in process:
            result["detected_from"] = "pycharm"
            # "project_name – filename – PyCharm"
            parts = title.split(" \u2013 ")  # em-dash
            if not parts or len(parts) < 2:
                parts = title.split(" - ")
            if len(parts) >= 2:
                result["project_name"] = parts[0].strip()
                if len(parts) >= 3:
                    result["active_file"] = parts[1].strip()

        # IntelliJ/WebStorm
        elif any(ide in process for ide in ("idea64.exe", "webstorm64.exe")):
            result["detected_from"] = "jetbrains"
            parts = title.split(" \u2013 ")
            if not parts or len(parts) < 2:
                parts = title.split(" - ")
            if parts:
                result["project_name"] = parts[0].strip()

        return result

    except Exception as e:
        logger.debug(f"get_project_context Fehler: {e}")
        return {"project_name": "", "project_path": "", "active_file": "", "detected_from": ""}


class DirectoryWatcher:
    """
    Ueberwacht ein Verzeichnis auf Aenderungen via Polling (kein watchdog noetig).
    Nutzt os.scandir fuer effizientes Scanning.
    """

    def __init__(self, path: str, callback: Callable[[str, str, str], None],
                 interval: float = _WATCHER_POLL_INTERVAL):
        """
        Args:
            path: Verzeichnis zum Ueberwachen.
            callback: Wird aufgerufen mit (event_type, file_path, file_name).
                      event_type: "created", "modified", "deleted"
            interval: Poll-Intervall in Sekunden.
        """
        self.path = Path(path)
        self.callback = callback
        self.interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._snapshot: dict[str, float] = {}  # name -> mtime

    def start(self) -> None:
        """Startet den Watcher als Background-Thread."""
        if self._running:
            return
        if not self.path.exists():
            logger.warning(f"DirectoryWatcher: Verzeichnis existiert nicht: {self.path}")
            return

        self._snapshot = self._take_snapshot()
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name=f"dir-watcher-{self.path.name}",
        )
        self._thread.start()
        logger.info(f"DirectoryWatcher gestartet: {self.path}")

    def stop(self) -> None:
        """Stoppt den Watcher."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)

    def _take_snapshot(self) -> dict[str, float]:
        """Erstellt einen Snapshot des Verzeichnisses."""
        snap: dict[str, float] = {}
        try:
            with os.scandir(str(self.path)) as entries:
                for entry in entries:
                    try:
                        if entry.is_file():
                            snap[entry.name] = entry.stat().st_mtime
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass
        return snap

    def _watch_loop(self) -> None:
        """Polling-Loop fuer Verzeichnis-Ueberwachung."""
        while self._running:
            try:
                new_snapshot = self._take_snapshot()
                prev = self._snapshot

                # Neue Dateien
                for name, mtime in new_snapshot.items():
                    if name not in prev:
                        self._safe_callback("created", str(self.path / name), name)
                    elif mtime != prev[name]:
                        self._safe_callback("modified", str(self.path / name), name)

                # Geloeschte Dateien
                for name in prev:
                    if name not in new_snapshot:
                        self._safe_callback("deleted", str(self.path / name), name)

                self._snapshot = new_snapshot
            except Exception as e:
                logger.debug(f"DirectoryWatcher Fehler: {e}")

            time.sleep(self.interval)

    def _safe_callback(self, event_type: str, file_path: str, file_name: str) -> None:
        """Ruft den Callback sicher auf."""
        try:
            self.callback(event_type, file_path, file_name)
        except Exception as e:
            logger.warning(f"DirectoryWatcher Callback Fehler: {e}", exc_info=True)


# ══════════════════════════════════════════════════════════
#  CLIPBOARD INTELLIGENCE
# ══════════════════════════════════════════════════════════

class ClipboardIntelligence:
    """
    Analysiert Clipboard-Inhalte und fuehrt einen In-Memory Ring-Buffer
    fuer Clipboard-History.
    """

    def __init__(self, max_entries: int = _CLIPBOARD_HISTORY_MAX):
        self._history: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._last_text: str = ""

    def add_entry(self, text: str) -> None:
        """Fuegt einen neuen Clipboard-Eintrag hinzu (wenn unterschiedlich zum letzten)."""
        if not text or not text.strip():
            return
        text = text.strip()

        with self._lock:
            if text == self._last_text:
                return
            self._last_text = text

            analysis = self.analyze_text(text)
            self._history.appendleft({
                "text": text[:500],  # Max 500 Zeichen pro Eintrag
                "type": analysis["type"],
                "timestamp": datetime.now().isoformat(),
                "length": len(text),
            })

    def get_history(self) -> list[dict[str, Any]]:
        """Gibt die Clipboard-History zurueck (neueste zuerst)."""
        with self._lock:
            return list(self._history)

    @staticmethod
    def analyze_text(text: str) -> dict[str, Any]:
        """
        Analysiert einen Text und erkennt den Typ.

        Returns:
            {"type": "code|url|email|path|json|number|text", "details": {...}}
        """
        text = text.strip()

        if not text:
            return {"type": "empty", "details": {}}

        # URL-Erkennung
        if re.match(r'^https?://', text, re.IGNORECASE):
            try:
                parsed = urlparse(text)
                return {
                    "type": "url",
                    "details": {"domain": parsed.netloc, "scheme": parsed.scheme},
                }
            except Exception:
                pass

        # E-Mail-Erkennung
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', text):
            return {"type": "email", "details": {"address": text}}

        # Dateipfad-Erkennung (Windows)
        if re.match(r'^[A-Za-z]:\\', text) or text.startswith("\\\\"):
            return {"type": "path", "details": {"path": text}}

        # JSON-Erkennung
        if (text.startswith("{") and text.endswith("}")) or \
           (text.startswith("[") and text.endswith("]")):
            try:
                import json
                json.loads(text)
                return {"type": "json", "details": {"length": len(text)}}
            except (json.JSONDecodeError, ValueError):
                pass

        # Code-Erkennung (Heuristik)
        code_indicators = [
            "def ", "class ", "import ", "function ", "const ", "let ", "var ",
            "if (", "for (", "while (", "return ", "=>", "->", "async ", "await ",
            "#include", "public static", "private ", "SELECT ", "INSERT ",
        ]
        if any(indicator in text for indicator in code_indicators):
            return {"type": "code", "details": {"lines": text.count("\n") + 1}}

        # Zahlen-Erkennung
        if re.match(r'^-?\d+([.,]\d+)?$', text.replace(" ", "")):
            return {"type": "number", "details": {"value": text}}

        return {"type": "text", "details": {"length": len(text), "words": len(text.split())}}

    def analyze_clipboard(self) -> dict[str, Any]:
        """
        Analysiert den aktuellen Clipboard-Inhalt.

        Returns:
            {"text": "...", "type": "...", "details": {...}}
        """
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            text = result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            text = ""

        if not text:
            return {"text": "", "type": "empty", "details": {}}

        analysis = self.analyze_text(text)
        return {
            "text": text[:500],
            **analysis,
        }


# ── Singleton-Instanzen ──────────────────────────────────
clipboard_intel = ClipboardIntelligence()
