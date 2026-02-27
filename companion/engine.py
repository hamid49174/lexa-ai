"""Lexa AI — Companion Engine
Steuert den Windows-PC direkt via PyAutoGUI, psutil, subprocess
"""

import json
import logging
import subprocess
from pathlib import Path

import psutil
import pyperclip

from backend.security import is_command_allowed, audit_log

# Phase 3 Module
from companion import browser as web
from companion import file_tools
from companion import media
from companion import communication as comm

# Phase 4 Module
from backend import memory as mem

logger = logging.getLogger("lexa.companion")

PROJECT_ROOT = Path(__file__).parent.parent


class CompanionEngine:
    """Hauptklasse für PC-Kontrolle."""

    def __init__(self):
        self.commands = {
            "app_open": self.open_app,
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
        }

    def execute(self, command: str, params: dict | None = None) -> dict:
        """Execute a command with security checks."""
        params = params or {}

        # Security check
        permission = is_command_allowed(command)
        if permission == "blocked":
            audit_log(command, "blocked", f"params={params}")
            return {"success": False, "error": f"Command '{command}' ist blockiert."}

        if command not in self.commands:
            return {"success": False, "error": f"Unbekannter Befehl: {command}"}

        try:
            result = self.commands[command](**params)
            audit_log(command, "executed", f"params={params}")
            return {"success": True, "data": result}
        except Exception as e:
            audit_log(command, "error", str(e))
            logger.error(f"Command {command} failed: {e}")
            return {"success": False, "error": str(e)}

    def open_app(self, name: str = "", path: str = "") -> str:
        """Öffne eine App per Name oder Pfad."""
        app_map = {
            "notepad": "notepad.exe",
            "editor": "notepad.exe",
            "rechner": "calc.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "datei-explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "terminal": "cmd.exe",
            "powershell": "powershell.exe",
            "task-manager": "taskmgr.exe",
            "paint": "mspaint.exe",
            "snipping": "SnippingTool.exe",
            "einstellungen": "ms-settings:",
            "settings": "ms-settings:",
            "browser": "start msedge",
            "edge": "msedge.exe",
            "chrome": "chrome.exe",
            "firefox": "firefox.exe",
        }

        target = name.lower().strip()
        if target in app_map:
            executable = app_map[target]
            if executable.startswith("ms-"):
                subprocess.Popen(["start", executable], shell=True)
            else:
                subprocess.Popen(executable, shell=True)
            return f"{name} geöffnet."
        elif path:
            subprocess.Popen(path, shell=True)
            return f"{path} geöffnet."
        else:
            # Try to start by name directly
            try:
                subprocess.Popen(f"start {name}", shell=True)
                return f"Versuche {name} zu öffnen..."
            except Exception:
                return f"App '{name}' nicht gefunden."

    def list_apps(self) -> list[dict]:
        """Liste alle laufenden Apps."""
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

        screenshots_dir = PROJECT_ROOT / "screenshots"
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
        """Prozess beenden (braucht Bestätigung)."""
        if pid:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            proc.terminate()
            return f"Prozess {proc_name} (PID {pid}) beendet."
        elif name:
            killed = 0
            for proc in psutil.process_iter(["name"]):
                if proc.info["name"].lower() == name.lower():
                    proc.terminate()
                    killed += 1
            return f"{killed} Prozess(e) mit Name '{name}' beendet."
        return "Kein PID oder Name angegeben."

    def read_clipboard(self) -> str:
        """Clipboard-Inhalt lesen."""
        return pyperclip.paste()

    def write_clipboard(self, text: str = "") -> str:
        """Text in Clipboard schreiben."""
        pyperclip.copy(text)
        return "In Clipboard kopiert."

    def set_volume(self, level: int = 50) -> str:
        """System-Lautstärke setzen (0-100)."""
        level = max(0, min(100, level))
        # Use nircmd or PowerShell for volume control
        try:
            # PowerShell-based volume control
            ps_cmd = f"""
            $wshShell = New-Object -ComObject WScript.Shell
            1..50 | ForEach-Object {{ $wshShell.SendKeys([char]174) }}
            $steps = [math]::Round({level} / 2)
            1..$steps | ForEach-Object {{ $wshShell.SendKeys([char]175) }}
            """
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                timeout=10,
            )
            return f"Lautstärke auf {level}% gesetzt."
        except Exception as e:
            return f"Lautstärke konnte nicht gesetzt werden: {e}"

    def search_files(self, query: str = "", path: str = "C:/Users", extension: str = "") -> list[str]:
        """Dateien suchen."""
        import os

        results = []
        search_path = Path(path)
        max_results = 20

        for root, dirs, files in os.walk(search_path):
            # Skip system/hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                "node_modules", "__pycache__", ".git", "AppData", "Windows",
            )]
            for filename in files:
                if query.lower() in filename.lower():
                    if extension and not filename.endswith(extension):
                        continue
                    results.append(os.path.join(root, filename))
                    if len(results) >= max_results:
                        return results
        return results

    # ── NEUE BEFEHLE (Phase 2) ─────────────────────

    def mute_volume(self) -> str:
        """System stumm schalten."""
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
                capture_output=True, timeout=5,
            )
            return "Stummschaltung umgeschaltet."
        except Exception as e:
            return f"Fehler: {e}"

    def list_windows(self) -> list[dict]:
        """Alle sichtbaren Fenster auflisten."""
        try:
            ps = '''
            Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            using System.Text;
            using System.Collections.Generic;
            public class WinList {
                [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
                [DllImport("user32.dll")] static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
                [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
                delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
                public static List<string> Get() {
                    var r = new List<string>();
                    EnumWindows((h, l) => {
                        if (IsWindowVisible(h)) {
                            var sb = new StringBuilder(256);
                            GetWindowText(h, sb, 256);
                            if (sb.Length > 0) r.Add(sb.ToString());
                        }
                        return true;
                    }, IntPtr.Zero);
                    return r;
                }
            }
"@
            [WinList]::Get() | ConvertTo-Json
            '''
            result = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=10,
            )
            import json
            titles = json.loads(result.stdout) if result.stdout.strip() else []
            if isinstance(titles, str):
                titles = [titles]
            return [{"title": t} for t in titles if t.strip()]
        except Exception as e:
            return [{"error": str(e)}]

    def focus_window(self, title: str = "") -> str:
        """Fenster in den Vordergrund bringen."""
        try:
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
            [WinFocus]::Focus("{title}")
            '''
            result = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=10,
            )
            return f"Fenster '{title}' fokussiert."
        except Exception as e:
            return f"Fehler: {e}"

    def set_brightness(self, level: int = 50) -> str:
        """Monitor-Helligkeit setzen (0-100)."""
        level = max(0, min(100, level))
        try:
            ps = f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})'
            subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, timeout=5,
            )
            return f"Helligkeit auf {level}% gesetzt."
        except Exception as e:
            return f"Helligkeit nicht verfügbar (Desktop-PC?): {e}"

    def get_brightness(self) -> dict:
        """Aktuelle Monitor-Helligkeit abrufen."""
        try:
            ps = '(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness'
            result = subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, text=True, timeout=5,
            )
            return {"brightness": int(result.stdout.strip())}
        except Exception:
            return {"brightness": None, "note": "Nicht verfügbar (Desktop-PC)"}

    def wifi_status(self) -> dict:
        """WLAN-Status abrufen."""
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.strip().split("\n")
            info = {}
            for line in lines:
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip().lower()
                    val = val.strip()
                    if "ssid" in key and "bssid" not in key:
                        info["ssid"] = val
                    elif "signal" in key:
                        info["signal"] = val
                    elif "state" in key or "status" in key:
                        info["status"] = val
            return info if info else {"status": "Kein WLAN gefunden"}
        except Exception as e:
            return {"error": str(e)}

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
        """Timer setzen (läuft im Hintergrund)."""
        import threading

        def _timer():
            import time
            time.sleep(seconds)
            # Show Windows notification
            try:
                ps = f'''
                [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null
                $n = New-Object System.Windows.Forms.NotifyIcon
                $n.Icon = [System.Drawing.SystemIcons]::Information
                $n.BalloonTipTitle = "Lexa Timer"
                $n.BalloonTipText = "{message}"
                $n.Visible = $true
                $n.ShowBalloonTip(5000)
                '''
                subprocess.run(["powershell", "-Command", ps], capture_output=True, timeout=10)
            except Exception:
                pass

        t = threading.Thread(target=_timer, daemon=True)
        t.start()
        mins = seconds // 60
        secs = seconds % 60
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        return f"Timer gesetzt: {time_str} — '{message}'"

    def open_url(self, url: str = "") -> str:
        """URL im Standard-Browser öffnen."""
        if not url:
            return "Keine URL angegeben."
        import webbrowser
        webbrowser.open(url)
        return f"URL geöffnet: {url}"

    def shutdown_pc(self, delay: int = 30) -> str:
        """PC herunterfahren (braucht Bestätigung)."""
        subprocess.Popen(f"shutdown /s /t {delay}", shell=True)
        return f"PC fährt in {delay} Sekunden herunter."

    def restart_pc(self, delay: int = 30) -> str:
        """PC neustarten (braucht Bestätigung)."""
        subprocess.Popen(f"shutdown /r /t {delay}", shell=True)
        return f"PC startet in {delay} Sekunden neu."


# Singleton
companion = CompanionEngine()
