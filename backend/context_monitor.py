"""
Lexa Context Monitor — Ueberwacht den System-Zustand und aktive Anwendungen.
Liefert Kontext fuer proaktive Vorschlaege und Workflow-Trigger.

Nur stdlib + ctypes — keine externen Dependencies.
Thread-safe Singleton mit Event-System.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable, Optional

import psutil

logger = logging.getLogger("lexa.context_monitor")

# ── Windows API Definitionen ─────────────────────────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# ── Konstanten ────────────────────────────────────────────
_MONITOR_INTERVAL = 10          # Sekunden zwischen Kontext-Updates
_HIGH_CPU_THRESHOLD = 85.0      # Prozent
_HIGH_MEMORY_THRESHOLD = 90.0   # Prozent
_IDLE_THRESHOLD = 300           # 5 Minuten idle
_APP_HISTORY_MAX = 500          # Max Eintraege in App-History
_CLIPBOARD_MAX_LEN = 200        # Max Zeichen fuer Clipboard-Snippet


class ContextMonitor:
    """
    Singleton-Klasse die den System-Zustand ueberwacht.
    Emittiert Events bei Aenderungen (Fenster-Wechsel, hohe CPU, etc.).
    """

    _instance: Optional[ContextMonitor] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> ContextMonitor:
        with cls._instance_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Aktueller Kontext-Cache
        self._current_context: dict[str, Any] = {}
        self._last_active_window: dict[str, str] = {}
        self._last_clipboard: str = ""

        # Event-Handlers
        self._event_handlers: dict[str, list[Callable]] = {}

        # App-History (Ring-Buffer)
        self._app_history: deque[dict] = deque(maxlen=_APP_HISTORY_MAX)

        # Vorheriger App-Satz fuer open/close Detection
        self._prev_running_apps: set[str] = set()

        logger.info("ContextMonitor initialisiert")

    # ══════════════════════════════════════════════════
    #  WINDOWS API — Aktives Fenster
    # ══════════════════════════════════════════════════

    def get_active_window(self) -> dict[str, str]:
        """
        Gibt das aktuell aktive Fenster zurueck.
        Nutzt Windows API: GetForegroundWindow, GetWindowText, GetWindowThreadProcessId.

        Returns:
            {"title": "...", "process": "...", "exe": "..."}
        """
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"title": "", "process": "", "exe": ""}

            # Window-Titel holen
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return {"title": "", "process": "", "exe": ""}

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            # Prozess-ID holen
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            process_name = ""
            exe_path = ""
            try:
                proc = psutil.Process(pid.value)
                process_name = proc.name()
                exe_path = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

            return {
                "title": title,
                "process": process_name,
                "exe": exe_path,
            }
        except Exception as e:
            logger.debug(f"get_active_window Fehler: {e}")
            return {"title": "", "process": "", "exe": ""}

    # ══════════════════════════════════════════════════
    #  IDLE-ZEIT (Maus/Tastatur)
    # ══════════════════════════════════════════════════

    def get_idle_time(self) -> float:
        """
        Gibt die Sekunden seit der letzten Maus/Tastatur-Eingabe zurueck.
        Nutzt Windows API: GetLastInputInfo.
        """
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if not user32.GetLastInputInfo(ctypes.byref(lii)):
                return 0.0

            tick_count = kernel32.GetTickCount64()
            idle_ms = tick_count - lii.dwTime
            return max(0.0, idle_ms / 1000.0)
        except Exception as e:
            logger.debug(f"get_idle_time Fehler: {e}")
            return 0.0

    # ══════════════════════════════════════════════════
    #  CLIPBOARD
    # ══════════════════════════════════════════════════

    def get_clipboard(self) -> str:
        """
        Liest den aktuellen Clipboard-Text (nur Text, keine Bilder).
        Nutzt PowerShell Get-Clipboard als sicherste Methode ohne pywin32.

        Returns:
            Clipboard-Text (max 200 Zeichen) oder leerer String.
        """
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                text = result.stdout.strip()
                return text[:_CLIPBOARD_MAX_LEN] if text else ""
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.debug(f"get_clipboard Fehler: {e}")
            return ""

    # ══════════════════════════════════════════════════
    #  LAUFENDE APPS
    # ══════════════════════════════════════════════════

    def get_running_apps(self) -> list[str]:
        """
        Gibt eine Liste der laufenden Apps mit sichtbaren Fenstern zurueck.
        Filtert System-Prozesse heraus.
        """
        _SYSTEM_PROCS = {
            "svchost.exe", "csrss.exe", "wininit.exe", "services.exe",
            "lsass.exe", "smss.exe", "System", "Registry", "dwm.exe",
            "fontdrvhost.exe", "conhost.exe", "sihost.exe", "taskhostw.exe",
            "ctfmon.exe", "dllhost.exe", "SearchHost.exe", "TextInputHost.exe",
            "RuntimeBroker.exe", "ShellExperienceHost.exe", "StartMenuExperienceHost.exe",
            "SecurityHealthSystray.exe", "SgrmBroker.exe", "spoolsv.exe",
            "WmiPrvSE.exe", "SearchIndexer.exe", "WidgetService.exe",
        }
        apps: set[str] = set()
        try:
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    name = proc.info["name"]
                    if name and name not in _SYSTEM_PROCS:
                        # Pruefen ob der Prozess ein sichtbares Fenster hat
                        # (vereinfacht: alles mit .exe das kein System-Prozess ist)
                        if name.lower().endswith(".exe"):
                            apps.add(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug(f"get_running_apps Fehler: {e}")

        return sorted(apps)

    # ══════════════════════════════════════════════════
    #  SYSTEM-KONTEXT (Gesamt)
    # ══════════════════════════════════════════════════

    def get_system_context(self) -> dict[str, Any]:
        """
        Gibt den gesamten aktuellen System-Kontext zurueck.

        Returns:
            {
                "active_window": {"title": "...", "process": "...", "exe": "..."},
                "clipboard_text": "...",
                "cpu_percent": 45.2,
                "memory_percent": 68.1,
                "running_apps": ["Code.exe", "chrome.exe", ...],
                "idle_seconds": 120,
                "time": "14:30",
                "day": "Monday",
                "battery": {"percent": 85, "charging": true} | null
            }
        """
        now = datetime.now()

        # Batterie-Status
        battery = None
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                battery = {
                    "percent": round(bat.percent, 1),
                    "charging": bat.power_plugged,
                }
        except Exception:
            pass

        context = {
            "active_window": self.get_active_window(),
            "clipboard_text": self.get_clipboard(),
            "cpu_percent": round(psutil.cpu_percent(interval=0.5), 1),
            "memory_percent": round(psutil.virtual_memory().percent, 1),
            "running_apps": self.get_running_apps(),
            "idle_seconds": round(self.get_idle_time(), 1),
            "time": now.strftime("%H:%M"),
            "day": now.strftime("%A"),
            "battery": battery,
        }

        with self._lock:
            self._current_context = context

        return context

    # ══════════════════════════════════════════════════
    #  APP-HISTORY
    # ══════════════════════════════════════════════════

    def get_app_history(self, hours: int = 24) -> list[dict]:
        """
        Gibt die App-Nutzungshistorie der letzten N Stunden zurueck.
        Wird vom Monitor-Loop automatisch befuellt.

        Returns:
            [{"app": "Code.exe", "title": "...", "timestamp": "...", "duration_approx_sec": 10}]
        """
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            return [
                entry for entry in self._app_history
                if entry.get("timestamp_unix", 0) >= cutoff
            ]

    # ══════════════════════════════════════════════════
    #  EVENT-SYSTEM
    # ══════════════════════════════════════════════════

    def on(self, event_name: str, callback: Callable) -> None:
        """
        Registriert einen Handler fuer ein Event.

        Events:
            - active_window_changed: Fenster gewechselt
            - high_cpu: CPU > Threshold
            - high_memory: RAM > Threshold
            - idle_detected: User ist idle
            - app_opened: Neue App gestartet
            - app_closed: App geschlossen
            - clipboard_changed: Clipboard hat neuen Inhalt
        """
        with self._lock:
            if event_name not in self._event_handlers:
                self._event_handlers[event_name] = []
            self._event_handlers[event_name].append(callback)
            logger.debug(f"Event-Handler registriert: {event_name}")

    def emit(self, event_name: str, data: Any = None) -> None:
        """Loest ein Event aus und ruft alle registrierten Handler auf."""
        with self._lock:
            handlers = list(self._event_handlers.get(event_name, []))

        for handler in handlers:
            try:
                handler(event_name, data)
            except Exception as e:
                logger.warning(f"Event-Handler Fehler ({event_name}): {e}", exc_info=True)

    # ══════════════════════════════════════════════════
    #  MONITOR LOOP (Background Thread)
    # ══════════════════════════════════════════════════

    def start(self) -> None:
        """Startet den Monitor-Loop als Background-Thread."""
        with self._lock:
            if self._running:
                logger.debug("Monitor laeuft bereits")
                return
            self._running = True

        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="context-monitor",
        )
        self._thread.start()
        logger.info("Context-Monitor gestartet (Intervall: %ds)", _MONITOR_INTERVAL)

    def stop(self) -> None:
        """Stoppt den Monitor-Loop."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=_MONITOR_INTERVAL + 2)
        logger.info("Context-Monitor gestoppt")

    def _monitor_loop(self) -> None:
        """
        Background-Loop der alle 10 Sekunden den Kontext aktualisiert
        und Events emittiert bei Aenderungen.
        """
        while True:
            with self._lock:
                if not self._running:
                    break

            try:
                self._monitor_tick()
            except Exception as e:
                logger.warning(f"Monitor-Tick Fehler: {e}", exc_info=True)

            # Schlafen in kleinen Schritten fuer schnelleres Stop
            for _ in range(_MONITOR_INTERVAL * 2):
                with self._lock:
                    if not self._running:
                        return
                time.sleep(0.5)

    def _monitor_tick(self) -> None:
        """Ein einzelner Monitor-Durchlauf mit Event-Detection."""
        # Aktives Fenster pruefen
        current_window = self.get_active_window()
        with self._lock:
            prev_window = self._last_active_window.copy()
            self._last_active_window = current_window.copy()

        if (prev_window.get("title")
                and current_window.get("title") != prev_window.get("title")):
            self.emit("active_window_changed", {
                "previous": prev_window,
                "current": current_window,
            })

            # App-History eintragen
            now = time.time()
            with self._lock:
                self._app_history.append({
                    "app": current_window.get("process", ""),
                    "title": current_window.get("title", ""),
                    "timestamp": datetime.now().isoformat(),
                    "timestamp_unix": now,
                    "duration_approx_sec": _MONITOR_INTERVAL,
                })

        # CPU pruefen
        try:
            cpu = psutil.cpu_percent(interval=0.3)
            if cpu > _HIGH_CPU_THRESHOLD:
                self.emit("high_cpu", {"cpu_percent": cpu})
        except Exception:
            pass

        # Memory pruefen
        try:
            mem = psutil.virtual_memory().percent
            if mem > _HIGH_MEMORY_THRESHOLD:
                self.emit("high_memory", {"memory_percent": mem})
        except Exception:
            pass

        # Idle pruefen
        idle = self.get_idle_time()
        if idle > _IDLE_THRESHOLD:
            self.emit("idle_detected", {"idle_seconds": idle})

        # Clipboard pruefen
        clipboard = self.get_clipboard()
        with self._lock:
            prev_clip = self._last_clipboard
            self._last_clipboard = clipboard

        if clipboard and clipboard != prev_clip:
            self.emit("clipboard_changed", {"text": clipboard})

        # App open/close Detection
        current_apps = set(self.get_running_apps())
        with self._lock:
            prev_apps = self._prev_running_apps.copy()
            self._prev_running_apps = current_apps.copy()

        if prev_apps:  # Nicht beim ersten Durchlauf
            opened = current_apps - prev_apps
            closed = prev_apps - current_apps

            for app in opened:
                self.emit("app_opened", {"app": app})
            for app in closed:
                self.emit("app_closed", {"app": app})

    # ══════════════════════════════════════════════════
    #  CACHED CONTEXT (fuer schnelle Abfragen)
    # ══════════════════════════════════════════════════

    def get_cached_context(self) -> dict[str, Any]:
        """Gibt den zuletzt gecachten Kontext zurueck (ohne neue Abfrage)."""
        with self._lock:
            return self._current_context.copy()


# ── Singleton-Instanz ─────────────────────────────────────
context_monitor = ContextMonitor()
