"""Lexa AI — Companion Engine
Steuert den Windows-PC direkt via psutil, subprocess, ctypes
+ Dynamisches Plugin-System (plugins/ Ordner)

Upgraded tools (Phase 40+):
- Volume: pycaw (Windows Core Audio API) — precise, instant, universal
- Media keys: ctypes keybd_event — OS-level, layout-independent
- File search: Windows Search Index (instant) + os.walk fallback
- WiFi: Structured PowerShell (Get-NetConnectionProfile) — language-independent
- Brightness: Hardware detection + graceful fallback
- Process kill: Race-condition safe
"""

import ctypes
import json
import logging
import os
import subprocess
from pathlib import Path

import psutil
import pyperclip

from backend.security import is_command_allowed, audit_log
from backend.i18n import t
from backend.plugin_loader import discover_plugins, list_plugins

# Phase 3 Module
from companion import browser as web
from companion import file_tools
from companion import media
from companion import communication as comm

# Phase 4 Module
from backend import memory as mem

# Phase 19 Module
from backend import productivity as prod

# Phase 21 Module
from companion import system_tools as systools

# Phase 22 Module
from companion import dev_tools as devtools

# Phase 47 Module
from companion import calendar_integration as calendar_int

# Phase 40+ Module
from companion import tool_health

# Upgrade 3: Smart Reminders
from backend import reminders

# Weather Module
from companion import weather

# Upgrade 6: Vision/OCR
from companion import ocr

logger = logging.getLogger("lexa.companion")

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(Path(__file__).resolve().parent.parent))
PROJECT_ROOT = Path(__file__).parent.parent

# ── Global timer results (queryable by frontend) ──
_timer_results = []  # list of {"message": str, "fired_at": float, "acknowledged": bool}


class CompanionEngine:
    """Hauptklasse für PC-Kontrolle."""

    def __init__(self):
        self.commands = {
            "app_open": self.open_app,
            "app_search": self.app_search,
            "app_list_installed": self.app_list_installed,
            "app_list": self.list_apps,
            "system_info": self.get_system_info,
            "screenshot": self.take_screenshot,
            "process_list": self.list_processes,
            "process_kill": self.kill_process,
            "clipboard_read": self.read_clipboard,
            "clipboard_write": self.write_clipboard,
            "volume_set": self.set_volume,
            "volume_mute": self.mute_volume,
            "file_search": self.search_files,
            "window_list": self.list_windows,
            "window_focus": self.focus_window,
            "brightness_set": self.set_brightness,
            "brightness_get": self.get_brightness,
            "wifi_status": self.wifi_status,
            "battery_status": self.battery_status,
            "timer_set": self.set_timer,
            "browser_open": self.open_url,
            "shutdown": self.shutdown_pc,
            "restart": self.restart_pc,
            # ── Phase 3: Browser ──
            "youtube_search": web.search_youtube,
            "youtube_play": web.play_youtube,
            "web_open": web.open_url,
            "web_screenshot": web.website_screenshot,
            "web_pdf": web.website_to_pdf,
            "web_scrape": web.scrape_text,
            "price_check": web.check_price,
            "browser_close": web.close_browser,
            # ── Phase 3: Datei-Tools ──
            "find_duplicates": file_tools.find_duplicates,
            "batch_rename": file_tools.batch_rename,
            "organize_downloads": file_tools.organize_downloads,
            "merge_pdfs": file_tools.merge_pdfs,
            "split_pdf": file_tools.split_pdf,
            "disk_analysis": file_tools.disk_analysis,
            "clean_temp": file_tools.clean_temp,
            # ── Phase 3: Media ──
            "media_play_pause": media.media_play_pause,
            "media_next": media.media_next,
            "media_prev": media.media_prev,
            "media_stop": media.media_stop,
            "spotify_open": media.open_spotify,
            "convert_media": media.convert_media,
            "extract_audio": media.extract_audio,
            "screen_record": media.screen_record,
            # ── Phase 3: Kommunikation ──
            "email_send": comm.email_send,
            "email_read": comm.email_read,
            "email_search": comm.email_search,
            "email_summarize": comm.email_summarize,
            "telegram_send": comm.telegram_send,
            "telegram_read": comm.telegram_read,
            "discord_send": comm.discord_send,
            # ── Phase 4: Gedächtnis & Notizen ──
            "note_create": mem.note_create,
            "note_read": mem.note_read,
            "note_list": mem.note_list,
            "note_delete": mem.note_delete,
            "memory_search": mem.search_memory,
            "memory_add": mem.add_memory,
            "summarize": mem.summarize_text,
            "routine_create": mem.routine_create,
            "routine_list": mem.routine_list,
            "routine_delete": mem.routine_delete,
            "routine_toggle": mem.routine_toggle,
            # ── Phase 19: Produktivität ──
            "todo_create": prod.todo_create,
            "todo_list": prod.todo_list,
            "todo_update": prod.todo_update,
            "todo_complete": prod.todo_complete,
            "todo_delete": prod.todo_delete,
            "pomodoro_start": prod.pomodoro_start,
            "pomodoro_stop": prod.pomodoro_stop,
            "pomodoro_status": prod.pomodoro_status,
            "habit_create": prod.habit_create,
            "habit_log": prod.habit_log,
            "habit_list": prod.habit_list,
            "habit_delete": prod.habit_delete,
            "time_tracking_start": prod.time_tracking_start,
            "time_tracking_stop": prod.time_tracking_stop,
            "time_tracking_report": prod.time_tracking_report,
            "focus_mode_on": prod.focus_mode_on,
            "focus_mode_off": prod.focus_mode_off,
            # ── Phase 20: Dateien erweitert ──
            "archive_create": file_tools.archive_create,
            "archive_extract": file_tools.archive_extract,
            "archive_list": file_tools.archive_list,
            "backup_create": file_tools.backup_create,
            "backup_list": file_tools.backup_list,
            "backup_restore": file_tools.backup_restore,
            "image_convert": file_tools.image_convert,
            "image_resize": file_tools.image_resize,
            "image_batch_resize": file_tools.image_batch_resize,
            "image_info": file_tools.image_info,
            "file_info": file_tools.file_info,
            "folder_size": file_tools.folder_size,
            "file_move": file_tools.file_move,
            "file_copy": file_tools.file_copy,
            "file_delete": file_tools.file_delete,
            "file_open": file_tools.file_open,
            "file_recent_downloads": file_tools.file_recent_downloads,
            "folder_create": file_tools.folder_create,
            # ── Phase 21: PC-Kontrolle erweitert ──
            "window_move": systools.window_move,
            "window_resize": systools.window_resize,
            "window_minimize": systools.window_minimize,
            "window_maximize": systools.window_maximize,
            "window_layout": systools.window_layout,
            "autostart_list": systools.autostart_list,
            "autostart_add": systools.autostart_add,
            "autostart_remove": systools.autostart_remove,
            "service_list": systools.service_list,
            "service_info": systools.service_info,
            "service_start": systools.service_start_cmd,
            "service_stop": systools.service_stop_cmd,
            "env_list": systools.env_list,
            "env_get": systools.env_get,
            "env_set": systools.env_set,
            "system_uptime": systools.system_uptime,
            "installed_apps": systools.installed_apps,
            "ping": systools.ping_host,
            "dns_lookup": systools.dns_lookup,
            "port_check": systools.port_check,
            "network_info": systools.network_info,
            "public_ip": systools.public_ip,
            "traceroute": systools.traceroute,
            "flush_dns": systools.flush_dns,
            # ── Phase 22: Entwickler-Tools ──
            "git_status": devtools.git_status,
            "git_log": devtools.git_log,
            "git_diff": devtools.git_diff,
            "git_branch_list": devtools.git_branch_list,
            "git_add": devtools.git_add,
            "git_commit": devtools.git_commit,
            "git_pull": devtools.git_pull,
            "git_push": devtools.git_push,
            "docker_ps": devtools.docker_ps,
            "docker_images": devtools.docker_images,
            "docker_start": devtools.docker_start,
            "docker_stop": devtools.docker_stop,
            "docker_logs": devtools.docker_logs,
            "docker_stats": devtools.docker_stats,
            "http_request": devtools.http_request,
            "log_analyze": devtools.log_analyze,
            "server_check": devtools.server_check,
            "multi_server_check": devtools.multi_server_check,
            "json_format": devtools.json_format,
            "regex_test": devtools.regex_test,
            "base64_encode": devtools.base64_encode,
            "base64_decode": devtools.base64_decode,
            "hash_text": devtools.hash_text,
            "generate_uuid": devtools.generate_uuid,
            "timestamp_convert": devtools.timestamp_convert,
            # ── Phase 47: Google Calendar ──
            "calendar_today": calendar_int.calendar_today,
            "calendar_week": calendar_int.calendar_week,
            "calendar_next": calendar_int.calendar_next,
            "calendar_create": calendar_int.calendar_create,
            "calendar_delete": calendar_int.calendar_delete,
            "calendar_search": calendar_int.calendar_search,
            # ── Weather ──
            "weather_current": weather.weather_current,
            "weather_forecast": weather.weather_forecast,
            # ── Upgrade 3: Smart Reminders ──
            "reminder_create": reminders.reminder_create,
            "reminder_list": reminders.reminder_list,
            "reminder_delete": reminders.reminder_delete,
            # ── Upgrade 6: Vision/OCR ──
            "screen_analyze": self.screen_analyze,
            "screen_read_text": self.screen_read_text,
            "screen_ocr": self.screen_ocr,
        }

        # ── Dynamic Plugins ──
        self._loaded_plugins = {}
        try:
            plugin_commands = discover_plugins()
            for cmd_name, info in plugin_commands.items():
                if cmd_name in self.commands:
                    logger.warning(t("plugin.overwrite", name=cmd_name))
                    continue
                self.commands[cmd_name] = info["func"]
                self._loaded_plugins[cmd_name] = info["plugin"]
            if plugin_commands:
                logger.info(t("plugin.registered", count=len(plugin_commands), total=len(self.commands)))
        except Exception as e:
            logger.warning(t("plugin.loaderError", error=str(e)))

    def get_plugin_info(self) -> list[dict]:
        """Get info about loaded plugins."""
        return list_plugins()

    def execute(self, command: str, params: dict | None = None) -> dict:
        """Execute a command with security checks."""
        params = params or {}

        # Limit param count and key length to prevent abuse
        if len(params) > 20:
            return {"success": False, "error": "Zu viele Parameter angegeben (max 20)."}

        # Security check
        permission = is_command_allowed(command)
        if permission == "blocked":
            audit_log(command, "blocked", f"params={list(params.keys())}")
            return {"success": False, "error": t("command.blockedEngine", command=command)}

        if command not in self.commands:
            # Suggest similar commands
            similar = [c for c in self.commands if c.startswith(command[:4])] if len(command) >= 4 else []
            hint = f" Meintest du: {', '.join(similar[:3])}?" if similar else ""
            return {"success": False, "error": t("command.unknownEngine", command=command, hint=hint)}

        try:
            result = self.commands[command](**params)
            audit_log(command, "executed", f"params={list(params.keys())}")
            return {"success": True, "data": result}
        except TypeError as e:
            # Wrong parameters
            import inspect
            func = self.commands[command]
            sig = str(inspect.signature(func))
            audit_log(command, "param_error", str(e))
            logger.warning(f"Command {command} Paramter-Fehler: {e}")
            return {"success": False, "error": t("error.paramError", command=command, sig=sig, error=str(e))}
        except Exception as e:
            audit_log(command, "error", str(e)[:200])
            logger.error(f"Command {command} failed: {e}", exc_info=True)
            return {"success": False, "error": t("error.commandError", command=command, error=str(e))}

    def open_app(self, name: str = "", path: str = "") -> str:
        """Öffne eine App per Name oder Pfad — Smart Discovery mit Fuzzy Matching."""
        from companion.app_discovery import launch_app
        return launch_app(name, path)

    def app_search(self, query: str = "") -> list[dict]:
        """Suche nach installierten Apps per Name (Fuzzy-Matching)."""
        from companion.app_discovery import search_apps
        if not query:
            return [{"error": "Kein Suchbegriff angegeben."}]
        results = search_apps(query, limit=10)
        return [{"name": r["name"], "app_id": r.get("app_id", ""), "match": r.get("match_type", "")} for r in results]

    def app_list_installed(self, limit: int = 50) -> list[dict]:
        """Liste aller installierten Apps (aus Start Menu, Registry, PATH)."""
        from companion.app_discovery import list_installed_apps
        return list_installed_apps(limit=min(limit, 200))

    def list_apps(self) -> list[dict]:
        """Liste alle laufenden Apps/Prozesse."""
        apps = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                apps.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu": info["cpu_percent"],
                    "memory_mb": round(info["memory_info"].rss / 1024 / 1024, 1)
                    if info["memory_info"]
                    else 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(apps, key=lambda x: x["memory_mb"], reverse=True)[:30]

    def get_system_info(self) -> dict:
        """System-Informationen abrufen."""
        cpu_freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "cpu_cores": psutil.cpu_count(),
            "cpu_freq_mhz": round(cpu_freq.current) if cpu_freq else None,
            "ram_total_gb": round(mem.total / 1024**3, 1),
            "ram_used_gb": round(mem.used / 1024**3, 1),
            "ram_percent": mem.percent,
            "disk_total_gb": round(disk.total / 1024**3, 1),
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_percent": round(disk.percent, 1),
            "battery_percent": battery.percent if battery else None,
            "battery_plugged": battery.power_plugged if battery else None,
        }

    def take_screenshot(self, save_path: str = "") -> str:
        """Screenshot machen und speichern."""
        import mss

        screenshots_dir = Path(_DATA_DIR) / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)

        if not save_path:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(screenshots_dir / f"screenshot_{timestamp}.png")

        with mss.mss() as sct:
            sct.shot(output=save_path)

        return save_path

    def list_processes(self) -> list[dict]:
        """Alle laufenden Prozesse auflisten."""
        return self.list_apps()

    def kill_process(self, pid: int = 0, name: str = "") -> str:
        """Prozess beenden (braucht Bestätigung). Race-condition safe."""
        if pid:
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
                proc.terminate()
                return f"Prozess {proc_name} (PID {pid}) beendet."
            except psutil.NoSuchProcess:
                return f"Prozess mit PID {pid} existiert nicht mehr."
            except psutil.AccessDenied:
                return f"Keine Berechtigung, Prozess {pid} zu beenden. Admin-Rechte nötig?"
        elif name:
            # Collect matching PIDs first, then terminate (avoids race conditions)
            targets = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() == name.lower():
                        targets.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            killed = 0
            errors = []
            for pid_target in targets:
                try:
                    p = psutil.Process(pid_target)
                    p.terminate()
                    killed += 1
                except psutil.NoSuchProcess:
                    continue  # Already exited — not an error
                except psutil.AccessDenied:
                    errors.append(f"PID {pid_target}: Zugriff verweigert")

            result = f"{killed} Prozess(e) mit Name '{name}' beendet."
            if errors:
                result += f" Fehler: {'; '.join(errors[:3])}"
            if killed == 0 and not errors:
                result = f"Kein Prozess mit Name '{name}' gefunden."
            return result
        return "Kein PID oder Name angegeben."

    def read_clipboard(self) -> str:
        """Clipboard-Inhalt lesen."""
        return pyperclip.paste()

    def write_clipboard(self, text: str = "") -> str:
        """Text in Clipboard schreiben."""
        pyperclip.copy(text)
        return "In Clipboard kopiert."

    def set_volume(self, level: int = 50) -> str:
        """System-Lautstärke setzen (0-100) via Windows Core Audio API.

        Primary: pycaw (precise, instant, sets exact percentage)
        Fallback: ctypes keybd_event (works without pycaw, ±2% precision)
        """
        level = max(0, min(100, level))
        try:
            # Primary: pycaw — precise volume control via Windows Core Audio API
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"Lautstärke auf {level}% gesetzt."
        except ImportError:
            logger.info("pycaw not installed, falling back to keybd_event")
        except Exception as e:
            logger.warning(f"pycaw volume set failed: {e}, falling back to keybd_event")

        # Fallback: keybd_event — press volume keys (each step = 2%)
        try:
            VK_VOLUME_DOWN = 0xAE
            VK_VOLUME_UP = 0xAF
            KEYEVENTF_KEYUP = 0x0002
            keybd = ctypes.windll.user32.keybd_event
            # Go to 0 first (50 steps × 2% = 100%)
            for _ in range(50):
                keybd(VK_VOLUME_DOWN, 0, 0, 0)
                keybd(VK_VOLUME_DOWN, 0, KEYEVENTF_KEYUP, 0)
            # Go up to target level
            steps = level // 2
            for _ in range(steps):
                keybd(VK_VOLUME_UP, 0, 0, 0)
                keybd(VK_VOLUME_UP, 0, KEYEVENTF_KEYUP, 0)
            return f"Lautstärke auf ~{level}% gesetzt."
        except Exception as e:
            return f"Lautstärke konnte nicht gesetzt werden: {e}"

    def search_files(self, query: str = "", path: str = "C:/Users", extension: str = "",
                      max_results: int = 50) -> list[str]:
        """Dateien suchen — Windows Search Index (instant) mit os.walk Fallback.

        Primary: Windows Search Index via ADODB (uses pre-built index, <100ms)
        Fallback: os.walk (slower but always works, with 10s timeout)
        """
        from backend.security import validate_path
        max_results = max(1, min(100, max_results))

        if not query:
            return ["Kein Suchbegriff angegeben."]

        try:
            validate_path(path)
        except ValueError as e:
            return [f"Pfad blockiert: {e}"]

        # --- Primary: Windows Search Index (instant, indexed) ---
        try:
            results = self._search_index(query, path, extension, max_results)
            if results is not None:
                return results
        except Exception as e:
            logger.debug(f"Windows Search Index unavailable: {e}")

        # --- Fallback: os.walk (slower, 10s timeout) ---
        return self._search_walk(query, path, extension, max_results)

    def _search_index(self, query: str, path: str, extension: str, limit: int) -> list[str] | None:
        """Search via Windows Search Index (ADODB + Search.CollatorDSO).

        Returns list of paths, or None if the index is unavailable.
        This is the same index used by Windows Explorer search — instant results.
        """
        # Sanitize query for SQL LIKE (escape single quotes)
        safe_query = query.replace("'", "''")[:200]
        safe_path = path.replace("'", "''").replace("/", "\\")

        # Build SQL query for Windows Search Index
        where_clauses = [f"System.FileName LIKE '%{safe_query}%'"]
        if safe_path:
            where_clauses.append(f"SCOPE='file:{safe_path}'")
        if extension:
            safe_ext = extension.lstrip(".").replace("'", "''")[:10]
            where_clauses.append(f"System.FileExtension = '.{safe_ext}'")

        sql = f"SELECT TOP {limit} System.ItemPathDisplay FROM SystemIndex WHERE {' AND '.join(where_clauses)}"

        ps = f'''
        try {{
            $conn = New-Object -ComObject "ADODB.Connection"
            $conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows'")
            $rs = $conn.Execute("{sql}")
            $results = @()
            while (-not $rs.EOF) {{
                $results += $rs.Fields[0].Value
                $rs.MoveNext()
            }}
            $rs.Close()
            $conn.Close()
            $results | ConvertTo-Json -Compress
        }} catch {{
            Write-Output "INDEX_ERROR"
        }}
        '''
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout.strip()
        if not output or output == "INDEX_ERROR":
            return None

        try:
            data = json.loads(output)
            if isinstance(data, str):
                data = [data]
            return data[:limit]
        except json.JSONDecodeError:
            # Single result without JSON array
            if output and not output.startswith("INDEX"):
                return [output]
            return None

    def _search_walk(self, query: str, path: str, extension: str, limit: int) -> list[str]:
        """Fallback file search using os.walk with timeout protection."""
        import time

        results = []
        search_path = Path(path)
        query_lower = query.lower()
        start_time = time.monotonic()
        timeout = 10.0  # 10 second max

        skip_dirs = {
            "node_modules", "__pycache__", ".git", ".hg", ".svn",
            "AppData", "Windows", "$Recycle.Bin", "ProgramData",
            ".cache", ".npm", ".nuget", "venv", ".venv",
        }

        for root, dirs, files in os.walk(search_path):
            # Timeout check
            if time.monotonic() - start_time > timeout:
                logger.info(f"File search timeout after {timeout}s, returning {len(results)} results")
                break

            # Skip system/hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]

            for filename in files:
                if query_lower in filename.lower():
                    if extension and not filename.lower().endswith(extension.lower()):
                        continue
                    results.append(os.path.join(root, filename))
                    if len(results) >= limit:
                        return results
        return results

    # ── NEUE BEFEHLE (Phase 2) ─────────────────────

    def mute_volume(self) -> str:
        """System stumm/laut schalten via Windows Core Audio API.

        Primary: pycaw (can also report current mute state)
        Fallback: ctypes keybd_event VK_VOLUME_MUTE
        """
        try:
            # Primary: pycaw — toggle mute with state feedback
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            current_mute = volume.GetMute()
            volume.SetMute(not current_mute, None)
            if current_mute:
                return "Ton wieder an."
            return "Stummgeschaltet."
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"pycaw mute failed: {e}")

        # Fallback: keybd_event VK_VOLUME_MUTE
        try:
            VK_VOLUME_MUTE = 0xAD
            KEYEVENTF_KEYUP = 0x0002
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)
            return "Stummschaltung umgeschaltet."
        except Exception as e:
            return t("error.generic", error=str(e))

    def list_windows(self) -> list[dict]:
        """Alle sichtbaren Fenster auflisten via ctypes (instant, kein PowerShell).

        Uses EnumWindows + GetWindowText directly via ctypes — same Win32 API
        as the PowerShell version, but without spawning a process (~100x faster).
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            windows = []

            def callback(hwnd, lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()
                        if title:
                            # Get process ID for extra context
                            pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            windows.append({"title": title, "pid": pid.value})
                return True

            user32.EnumWindows(EnumWindowsProc(callback), 0)
            return windows
        except Exception as e:
            return [{"error": str(e)}]

    def focus_window(self, title: str = "") -> str:
        """Fenster in den Vordergrund bringen."""
        try:
            # Sanitize title to prevent PowerShell injection
            safe_title = title.replace('"', '').replace("'", '').replace('`', '').replace('$', '').replace('{', '').replace('}', '')
            ps = f'''
            Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            public class WinFocus {{
                [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
                [DllImport("user32.dll")] static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
                public static bool Focus(string title) {{
                    var ps = System.Diagnostics.Process.GetProcesses();
                    foreach (var p in ps) {{
                        if (p.MainWindowTitle.Contains(title, StringComparison.OrdinalIgnoreCase)) {{
                            return SetForegroundWindow(p.MainWindowHandle);
                        }}
                    }}
                    return false;
                }}
            }}
"@
            [WinFocus]::Focus("{safe_title}")
            '''
            result = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=10,
            )
            return f"Fenster '{title}' fokussiert."
        except Exception as e:
            return t("error.generic", error=str(e))

    def set_brightness(self, level: int = 50) -> str:
        """Monitor-Helligkeit setzen (0-100).

        Uses WMI WmiMonitorBrightnessMethods — works on laptops and some monitors with DDC/CI.
        Detects hardware support first and gives clear feedback if unavailable.
        """
        level = max(0, min(100, level))
        try:
            # Check hardware support first, then set
            ps = f'''
            $methods = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction Stop
            if ($methods) {{
                $methods.WmiSetBrightness(1, {level})
                "OK"
            }} else {{
                "NO_SUPPORT"
            }}
            '''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=5,
            )
            if "OK" in result.stdout:
                return f"Helligkeit auf {level}% gesetzt."
            if result.stderr.strip():
                err = result.stderr.strip()[:200]
                if "not supported" in err.lower() or "nicht" in err.lower() or "ManagementObject" in err:
                    return "Helligkeitssteuerung nicht verfügbar. Mögliche Gründe: Desktop-PC, externer Monitor ohne DDC/CI, oder fehlende Treiber."
                return f"Helligkeit konnte nicht gesetzt werden: {err}"
            return "Helligkeitssteuerung nicht verfügbar auf diesem Gerät."
        except subprocess.TimeoutExpired:
            return "Helligkeitssteuerung: Timeout (WMI nicht verfügbar)."
        except Exception as e:
            return f"Helligkeit nicht verfügbar: {e}"

    def get_brightness(self) -> dict:
        """Aktuelle Monitor-Helligkeit abrufen mit Hardware-Erkennung."""
        try:
            ps = '''
            try {
                $b = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness -ErrorAction Stop).CurrentBrightness
                @{ brightness = $b; supported = $true } | ConvertTo-Json -Compress
            } catch {
                @{ brightness = $null; supported = $false; note = "Helligkeitssteuerung nicht verfuegbar (Desktop-PC oder Monitor ohne DDC/CI)" } | ConvertTo-Json -Compress
            }
            '''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                return json.loads(result.stdout.strip())
            return {"brightness": None, "supported": False, "note": "Keine Antwort von WMI"}
        except Exception:
            return {"brightness": None, "supported": False, "note": "WMI nicht verfügbar"}

    def wifi_status(self) -> dict:
        """WLAN/Netzwerk-Status abrufen — language-independent via PowerShell/WMI.

        Primary: Get-NetConnectionProfile + Get-NetAdapter (structured, language-independent)
        Supplement: netsh for SSID/signal strength (WiFi-specific details)
        """
        info = {}

        # Primary: Structured network info (works in any Windows language)
        try:
            ps = '''
            $profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
            $adapter = if ($profile) { Get-NetAdapter -InterfaceIndex $profile.InterfaceIndex -ErrorAction SilentlyContinue } else { $null }
            $ip = if ($profile) { (Get-NetIPAddress -InterfaceIndex $profile.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress } else { $null }
            @{
                connected = if ($profile) { $true } else { $false }
                network_name = if ($profile) { $profile.Name } else { $null }
                interface = if ($adapter) { $adapter.Name } else { $null }
                type = if ($adapter) { $adapter.MediaType } else { $null }
                speed_mbps = if ($adapter) { [math]::Round($adapter.LinkSpeed.Split(" ")[0]) } else { $null }
                ip = $ip
                connectivity = if ($profile) { $profile.IPv4Connectivity.ToString() } else { "NoTraffic" }
            } | ConvertTo-Json -Compress
            '''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            )
            if result.stdout.strip():
                info = json.loads(result.stdout.strip())
        except Exception as e:
            logger.debug(f"Get-NetConnectionProfile failed: {e}")

        # Supplement: netsh for WiFi-specific details (SSID, signal)
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if ":" not in line:
                        continue
                    key, _, val = line.partition(":")
                    key_stripped = key.strip()
                    val_stripped = val.strip()
                    # Match by field position/pattern rather than language-specific labels
                    # SSID is always after "SSID" (same in all languages)
                    if "SSID" in key_stripped and "BSSID" not in key_stripped:
                        info["ssid"] = val_stripped
                    # Signal is always a percentage like "95%"
                    elif "%" in val_stripped and len(val_stripped) <= 5:
                        info["signal"] = val_stripped
                    # Radio type (802.11ax, 802.11ac, etc.)
                    elif "802.11" in val_stripped:
                        info["radio_type"] = val_stripped
        except Exception as e:
            logger.debug(f"netsh wlan failed: {e}")

        if not info:
            return {"status": "Kein Netzwerk gefunden", "connected": False}

        # Set a friendly status string
        if info.get("connected"):
            ssid = info.get("ssid", info.get("network_name", ""))
            signal = info.get("signal", "")
            if ssid:
                info["status"] = f"Verbunden mit {ssid}" + (f" ({signal})" if signal else "")
            else:
                info["status"] = "Verbunden (Ethernet)"
        else:
            info["status"] = "Nicht verbunden"

        return info

    def battery_status(self) -> dict:
        """Akku-Status abrufen."""
        bat = psutil.sensors_battery()
        if bat:
            return {
                "percent": bat.percent,
                "plugged": bat.power_plugged,
                "time_left_min": round(bat.secsleft / 60) if bat.secsleft > 0 else None,
            }
        return {"status": "Kein Akku (Desktop-PC)"}

    def set_timer(self, seconds: int = 60, message: str = "Timer abgelaufen!") -> str:
        """Timer setzen (läuft im Hintergrund, persistent in SQLite). Max 24h."""
        import threading
        import time as _time

        # Clamp seconds: min 1s, max 24h
        seconds = max(1, min(86400, int(seconds)))
        message = str(message)[:200]

        fire_at = _time.time() + seconds

        # Persist to DB for crash-recovery
        try:
            from backend import memory as mem_module
            timer_id = mem_module.timer_create(fire_at, message)
        except Exception:
            timer_id = None

        def _timer():
            _time.sleep(seconds)
            # Store in global list for fast frontend polling
            _timer_results.append({
                "message": message,
                "fired_at": _time.time(),
                "acknowledged": False,
            })
            # Mark as fired in DB
            if timer_id is not None:
                try:
                    from backend import memory as mem_module
                    mem_module.timer_acknowledge(timer_id)
                except Exception:
                    pass
            logger.info(f"Timer fired: {message}")

        t = threading.Thread(target=_timer, daemon=True)
        t.start()
        mins = seconds // 60
        secs = seconds % 60
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        return f"Timer gesetzt: {time_str} — '{message}'"

    def open_url(self, url: str = "") -> str:
        """URL im Standard-Browser öffnen (nur http/https)."""
        if not url:
            return t("command.noUrl")
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "Nur http:// und https:// URLs erlaubt."
        if len(url) > 2000:
            return "URL zu lang."
        import webbrowser
        webbrowser.open(url)
        return f"URL geöffnet: {url}"

    def shutdown_pc(self, delay: int = 30) -> str:
        """PC herunterfahren (braucht Bestätigung)."""
        delay = max(0, min(3600, int(delay)))  # Clamp 0–3600s
        subprocess.Popen(["shutdown", "/s", "/t", str(delay)], shell=False)
        return f"PC fährt in {delay} Sekunden herunter."

    def restart_pc(self, delay: int = 30) -> str:
        """PC neustarten (braucht Bestätigung)."""
        delay = max(0, min(3600, int(delay)))  # Clamp 0–3600s
        subprocess.Popen(["shutdown", "/r", "/t", str(delay)], shell=False)
        return f"PC startet in {delay} Sekunden neu."


    # ── Upgrade 6: Vision/OCR Commands ─────────────

    def screen_analyze(self, prompt: str = "Was ist auf dem Bildschirm zu sehen?", window: str = "") -> dict:
        """Screenshot analysieren via Groq/Gemini/OpenAI Vision."""
        import asyncio
        from backend.vision import analyze_screenshot
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, analyze_screenshot(prompt, window_title=window or None))
                    result = future.result(timeout=30)
            else:
                result = asyncio.run(analyze_screenshot(prompt, window_title=window or None))
            return result
        except Exception as e:
            return {"error": str(e)}

    def screen_read_text(self, window: str = "") -> dict:
        """Text vom Bildschirm lesen via lokalem OCR (schnell, offline)."""
        return ocr.ocr_screenshot(window_title=window or None)

    def screen_ocr(self, window: str = "") -> dict:
        """Alias fuer screen_read_text — OCR vom Bildschirm."""
        return ocr.ocr_screenshot(window_title=window or None)

    # ── Timer query helpers (module-level accessible) ──

    @staticmethod
    def get_pending_timers() -> list[dict]:
        """Return timer results that fired within the last 60s and are not yet acknowledged."""
        import time as _time
        now = _time.time()
        pending = []
        for t in _timer_results:
            if not t["acknowledged"] and (now - t["fired_at"]) < 60:
                pending.append({"message": t["message"], "fired_at": t["fired_at"]})
        return pending

    @staticmethod
    def acknowledge_timers() -> str:
        """Acknowledge all pending timer notifications."""
        count = 0
        for t in _timer_results:
            if not t["acknowledged"]:
                t["acknowledged"] = True
                count += 1
        # Clean up old acknowledged entries (older than 5 minutes)
        import time as _time
        now = _time.time()
        _timer_results[:] = [t for t in _timer_results if (now - t["fired_at"]) < 300]
        return f"{count} Timer-Benachrichtigung(en) bestätigt."


# Singleton
companion = CompanionEngine()
