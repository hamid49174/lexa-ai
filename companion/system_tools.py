"""Lexa AI — System Tools (Phase 21)
Erweiterte PC-Kontrolle: Fenster-Management, Autostart, Dienste,
Umgebungsvariablen, System-Infos, Netzwerk-Tools
"""

import json
import logging
import re
import subprocess
import socket
import os

from backend.i18n import t

logger = logging.getLogger("lexa.system_tools")


def _sanitize_ps_arg(s: str, max_len: int = 200) -> str:
    """Escape a string for safe embedding inside a PowerShell double-quoted string."""
    if not s:
        return ""
    s = str(s)[:max_len]
    # Escape PowerShell special characters in double-quoted strings
    s = s.replace("`", "``")      # backtick is PS escape char
    s = s.replace('"', '`"')      # escape double-quotes
    s = s.replace("$", "`$")      # prevent variable expansion
    s = s.replace("\n", "")       # strip newlines
    s = s.replace("\r", "")       # strip carriage returns
    return s


# ══════════════════════════════════════════════════════
#  FENSTER-STEUERUNG
# ══════════════════════════════════════════════════════

def window_move(title: str = "", x: int = 0, y: int = 0) -> str:
    """Fenster an Position (x, y) verschieben."""
    if not title:
        return t("window.noTitle")
    try:
        safe_title = _sanitize_ps_arg(title)
        x = int(x)
        y = int(y)
        ps = f'''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Diagnostics;
        public class WinMove {{
            [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
            [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
            [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left, Top, Right, Bottom; }}
            public static string Move(string title, int x, int y) {{
                foreach (var p in Process.GetProcesses()) {{
                    if (p.MainWindowTitle.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0 && p.MainWindowHandle != IntPtr.Zero) {{
                        RECT r; GetWindowRect(p.MainWindowHandle, out r);
                        int w = r.Right - r.Left; int h = r.Bottom - r.Top;
                        SetWindowPos(p.MainWindowHandle, IntPtr.Zero, x, y, w, h, 0x0004);
                        return "OK:" + p.MainWindowTitle;
                    }}
                }}
                return "NOT_FOUND";
            }}
        }}
"@
        [WinMove]::Move("{safe_title}", {x}, {y})
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        if out.startswith("OK:"):
            return t("window.moved", title=out[3:], x=x, y=y)
        return t("window.notFound", title=safe_title)
    except Exception as e:
        return t("error.generic", error=str(e))


def window_resize(title: str = "", width: int = 800, height: int = 600) -> str:
    """Fenster auf Größe (width x height) ändern."""
    if not title:
        return t("window.noTitle")
    try:
        safe_title = _sanitize_ps_arg(title)
        width = int(width)
        height = int(height)
        ps = f'''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Diagnostics;
        public class WinResize {{
            [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
            [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
            [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left, Top, Right, Bottom; }}
            public static string Resize(string title, int w, int h) {{
                foreach (var p in Process.GetProcesses()) {{
                    if (p.MainWindowTitle.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0 && p.MainWindowHandle != IntPtr.Zero) {{
                        RECT r; GetWindowRect(p.MainWindowHandle, out r);
                        SetWindowPos(p.MainWindowHandle, IntPtr.Zero, r.Left, r.Top, w, h, 0x0004);
                        return "OK:" + p.MainWindowTitle;
                    }}
                }}
                return "NOT_FOUND";
            }}
        }}
"@
        [WinResize]::Resize("{safe_title}", {width}, {height})
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        if out.startswith("OK:"):
            return t("window.resized", title=out[3:], width=width, height=height)
        return t("window.notFound", title=safe_title)
    except Exception as e:
        return t("error.generic", error=str(e))


def window_minimize(title: str = "") -> str:
    """Fenster minimieren."""
    if not title:
        return t("window.noTitle")
    try:
        safe_title = _sanitize_ps_arg(title)
        ps = f'''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Diagnostics;
        public class WinMin {{
            [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            public static string Min(string title) {{
                foreach (var p in Process.GetProcesses()) {{
                    if (p.MainWindowTitle.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0 && p.MainWindowHandle != IntPtr.Zero) {{
                        ShowWindow(p.MainWindowHandle, 6);
                        return "OK:" + p.MainWindowTitle;
                    }}
                }}
                return "NOT_FOUND";
            }}
        }}
"@
        [WinMin]::Min("{safe_title}")
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        if out.startswith("OK:"):
            return t("window.minimized", title=out[3:])
        return t("window.notFound", title=safe_title)
    except Exception as e:
        return t("error.generic", error=str(e))


def window_maximize(title: str = "") -> str:
    """Fenster maximieren."""
    if not title:
        return t("window.noTitle")
    try:
        safe_title = _sanitize_ps_arg(title)
        ps = f'''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Diagnostics;
        public class WinMax {{
            [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            public static string Max(string title) {{
                foreach (var p in Process.GetProcesses()) {{
                    if (p.MainWindowTitle.IndexOf(title, StringComparison.OrdinalIgnoreCase) >= 0 && p.MainWindowHandle != IntPtr.Zero) {{
                        ShowWindow(p.MainWindowHandle, 3);
                        return "OK:" + p.MainWindowTitle;
                    }}
                }}
                return "NOT_FOUND";
            }}
        }}
"@
        [WinMax]::Max("{safe_title}")
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        out = result.stdout.strip()
        if out.startswith("OK:"):
            return t("window.maximized", title=out[3:])
        return t("window.notFound", title=safe_title)
    except Exception as e:
        return t("error.generic", error=str(e))


def window_layout(layout: str = "left-half") -> str:
    """Fenster-Layout anwenden (left-half, right-half, top-half, bottom-half, center)."""
    layouts = {
        "left-half": "0, 0, $w/2, $h",
        "right-half": "$w/2, 0, $w/2, $h",
        "top-half": "0, 0, $w, $h/2",
        "bottom-half": "0, $h/2, $w, $h/2",
        "center": "$w/4, $h/4, $w/2, $h/2",
        "top-left": "0, 0, $w/2, $h/2",
        "top-right": "$w/2, 0, $w/2, $h/2",
        "bottom-left": "0, $h/2, $w/2, $h/2",
        "bottom-right": "$w/2, $h/2, $w/2, $h/2",
    }
    if layout not in layouts:
        return t("system.unknownLayout", layout=layout, available=', '.join(layouts.keys()))

    try:
        ps = f'''
        Add-Type @"
        using System;
        using System.Runtime.InteropServices;
        using System.Diagnostics;
        public class WinLayout {{
            [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
            [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
            [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            public static string Apply(int x, int y, int w, int h) {{
                IntPtr hwnd = GetForegroundWindow();
                if (hwnd == IntPtr.Zero) return "NO_WINDOW";
                ShowWindow(hwnd, 1);
                SetWindowPos(hwnd, IntPtr.Zero, x, y, w, h, 0x0004);
                return "OK";
            }}
        }}
"@
        Add-Type -AssemblyName System.Windows.Forms
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
        $w = $screen.Width; $h = $screen.Height
        $x = [int]({layouts[layout].split(",")[0].strip()})
        $y = [int]({layouts[layout].split(",")[1].strip()})
        $cw = [int]({layouts[layout].split(",")[2].strip()})
        $ch = [int]({layouts[layout].split(",")[3].strip()})
        [WinLayout]::Apply($x, $y, $cw, $ch)
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return t("system.layoutError", layout=layout, error=str(err))
        return t("system.layoutApplied", layout=layout)
    except Exception as e:
        return t("error.generic", error=str(e))


# ══════════════════════════════════════════════════════
#  AUTOSTART-MANAGER
# ══════════════════════════════════════════════════════

def autostart_list() -> list[dict]:
    """Alle Autostart-Einträge auflisten (Registry + Startup-Ordner)."""
    entries = []
    try:
        ps = '''
        $reg = @(
            "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        )
        $result = @()
        foreach ($path in $reg) {
            try {
                $props = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
                if ($props) {
                    $props.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } | ForEach-Object {
                        $result += @{ name = $_.Name; value = $_.Value; source = $path }
                    }
                }
            } catch {}
        }
        # Startup folder
        $startupPath = [System.Environment]::GetFolderPath("Startup")
        Get-ChildItem $startupPath -ErrorAction SilentlyContinue | ForEach-Object {
            $result += @{ name = $_.Name; value = $_.FullName; source = "StartupFolder" }
        }
        $result | ConvertTo-Json -Depth 3
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            entries = data
    except Exception as e:
        logger.error(f"autostart_list: {e}")
    return entries


def autostart_add(name: str = "", path: str = "") -> str:
    """App zum Autostart hinzufügen (Registry HKCU Run)."""
    if not name or not path:
        return t("autostart.nameAndPathRequired")
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        safe_path = _sanitize_ps_arg(path, max_len=500)
        ps = f'''
        Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "{safe_name}" -Value "{safe_path}"
        "OK"
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            return t("autostart.added", name=safe_name)
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def autostart_remove(name: str = "") -> str:
    """App aus dem Autostart entfernen (Registry HKCU Run)."""
    if not name:
        return t("autostart.nameRequired")
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        ps = f'''
        Remove-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "{safe_name}" -ErrorAction Stop
        "OK"
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            return t("autostart.removed", name=safe_name)
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


# ══════════════════════════════════════════════════════
#  DIENSTE-MANAGER (Windows Services)
# ══════════════════════════════════════════════════════

def service_list(filter_status: str = "") -> list[dict]:
    """Windows-Dienste auflisten (optional: running, stopped)."""
    try:
        status_filter = ""
        if filter_status.lower() == "running":
            status_filter = "| Where-Object { $_.Status -eq 'Running' }"
        elif filter_status.lower() == "stopped":
            status_filter = "| Where-Object { $_.Status -eq 'Stopped' }"

        ps = f'''
        Get-Service {status_filter} | Select-Object -First 50 Name, DisplayName, Status, StartType |
        ForEach-Object {{ @{{ name=$_.Name; display_name=$_.DisplayName; status=$_.Status.ToString(); start_type=$_.StartType.ToString() }} }} |
        ConvertTo-Json -Depth 2
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            return data
        return []
    except Exception as e:
        return [{"error": str(e)}]


def service_info(name: str = "") -> dict:
    """Detaillierte Informationen zu einem Windows-Dienst."""
    if not name:
        return {"error": t("service.required")}
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        ps = f'''
        $s = Get-Service -Name "{safe_name}" -ErrorAction Stop
        $wmi = Get-WmiObject Win32_Service -Filter "Name='{safe_name}'" -ErrorAction SilentlyContinue
        @{{
            name = $s.Name
            display_name = $s.DisplayName
            status = $s.Status.ToString()
            start_type = $s.StartType.ToString()
            description = if ($wmi) {{ $wmi.Description }} else {{ "" }}
            path = if ($wmi) {{ $wmi.PathName }} else {{ "" }}
            pid = if ($wmi) {{ $wmi.ProcessId }} else {{ 0 }}
        }} | ConvertTo-Json
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": t("service.notFound", name=safe_name)}
    except Exception as e:
        return {"error": str(e)}


def _check_admin() -> bool:
    """Check if the current process has admin/elevated privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def service_start_cmd(name: str = "") -> str:
    """Windows-Dienst starten mit Admin-Erkennung.

    Detects whether we have admin privileges BEFORE attempting,
    and gives clear instructions if elevation is needed.
    """
    if not name:
        return t("service.required")
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        ps = f'Start-Service -Name "{safe_name}" -ErrorAction Stop; "OK"'
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if "OK" in result.stdout:
            return t("service.started", name=safe_name)

        stderr = result.stderr.strip()
        # Detect permission/access denied errors
        if any(kw in stderr.lower() for kw in ["access is denied", "zugriff verweigert",
                                               "accessdenied", "permission", "berechtigung",
                                               "cannot open", "service controller"]):
            is_admin = _check_admin()
            if not is_admin:
                return (f"Dienst '{name}' konnte nicht gestartet werden: Admin-Rechte erforderlich.\n"
                        f"Lexa läuft aktuell OHNE Admin-Rechte.\n"
                        f"Lösung: Lexa als Administrator neu starten (Rechtsklick → Als Administrator).")
            return f"Dienst '{name}' konnte nicht gestartet werden trotz Admin-Rechten: {stderr[:200]}"
        return t("error.stderr", stderr=stderr)
    except Exception as e:
        return t("error.generic", error=str(e))


def service_stop_cmd(name: str = "") -> str:
    """Windows-Dienst stoppen mit Admin-Erkennung.

    Detects whether we have admin privileges BEFORE attempting,
    and gives clear instructions if elevation is needed.
    """
    if not name:
        return t("service.required")
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        ps = f'Stop-Service -Name "{safe_name}" -Force -ErrorAction Stop; "OK"'
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if "OK" in result.stdout:
            return t("service.stopped", name=safe_name)

        stderr = result.stderr.strip()
        if any(kw in stderr.lower() for kw in ["access is denied", "zugriff verweigert",
                                               "accessdenied", "permission", "berechtigung",
                                               "cannot open", "service controller"]):
            is_admin = _check_admin()
            if not is_admin:
                return (f"Dienst '{name}' konnte nicht gestoppt werden: Admin-Rechte erforderlich.\n"
                        f"Lexa läuft aktuell OHNE Admin-Rechte.\n"
                        f"Lösung: Lexa als Administrator neu starten (Rechtsklick → Als Administrator).")
            return f"Dienst '{name}' konnte nicht gestoppt werden trotz Admin-Rechten: {stderr[:200]}"
        return t("error.stderr", stderr=stderr)
    except Exception as e:
        return t("error.generic", error=str(e))


# ══════════════════════════════════════════════════════
#  UMGEBUNGSVARIABLEN + SYSTEM-TOOLS
# ══════════════════════════════════════════════════════

def env_list() -> dict:
    """Alle Umgebungsvariablen auflisten."""
    env_vars = {}
    for key, value in sorted(os.environ.items()):
        env_vars[key] = value
    return env_vars


def env_get(name: str = "") -> dict:
    """Einzelne Umgebungsvariable lesen."""
    if not name:
        return {"error": t("env.nameRequired")}
    value = os.environ.get(name)
    if value is not None:
        return {"name": name, "value": value}
    return {"name": name, "value": None, "note": t("service.notSet")}


def env_set(name: str = "", value: str = "") -> str:
    """Umgebungsvariable setzen (User-Level, persistent)."""
    if not name:
        return t("env.nameRequired")
    try:
        safe_name = _sanitize_ps_arg(name, max_len=100)
        safe_value = _sanitize_ps_arg(value, max_len=2000)
        ps = f'[System.Environment]::SetEnvironmentVariable("{safe_name}", "{safe_value}", "User"); "OK"'
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if "OK" in result.stdout:
            os.environ[name] = value
            return t("env.set", name=safe_name)
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def system_uptime() -> dict:
    """System-Uptime anzeigen."""
    try:
        ps = '''
        $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
        $up = (Get-Date) - $boot
        @{
            boot_time = $boot.ToString("yyyy-MM-dd HH:mm:ss")
            days = $up.Days
            hours = $up.Hours
            minutes = $up.Minutes
            total_hours = [math]::Round($up.TotalHours, 1)
            formatted = "$($up.Days)d $($up.Hours)h $($up.Minutes)m"
        } | ConvertTo-Json
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": t("system.uptimeError")}
    except Exception as e:
        return {"error": str(e)}


def installed_apps(search: str = "") -> list[dict]:
    """Installierte Programme auflisten (optional mit Suchbegriff)."""
    try:
        filter_cmd = ""
        if search:
            safe_search = _sanitize_ps_arg(search, max_len=100)
            safe_search = safe_search.replace("*", "``*").replace("?", "``?")
            filter_cmd = f"| Where-Object {{ $_.DisplayName -like '*{safe_search}*' }}"

        ps = f'''
        $apps = @()
        $paths = @(
            "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
            "HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
            "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
        )
        foreach ($path in $paths) {{
            Get-ItemProperty $path -ErrorAction SilentlyContinue |
            Where-Object {{ $_.DisplayName }} {filter_cmd} |
            ForEach-Object {{
                $apps += @{{
                    name = $_.DisplayName
                    version = $_.DisplayVersion
                    publisher = $_.Publisher
                    install_date = $_.InstallDate
                    size_mb = if ($_.EstimatedSize) {{ [math]::Round($_.EstimatedSize / 1024, 1) }} else {{ $null }}
                }}
            }}
        }}
        $apps | Sort-Object {{ $_.name }} | Select-Object -First 100 | ConvertTo-Json -Depth 2
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            return data
        return []
    except Exception as e:
        return [{"error": str(e)}]


# ══════════════════════════════════════════════════════
#  NETZWERK-TOOLS
# ══════════════════════════════════════════════════════

def ping_host(host: str = "", count: int = 4) -> dict:
    """Host anpingen."""
    if not host:
        return {"error": t("network.hostRequired")}
    if len(host) > 253 or not re.match(r'^[a-zA-Z0-9.\-:]+$', host):
        return {"error": t("validation.invalidHostname")}
    count = max(1, min(10, count))
    try:
        result = subprocess.run(
            ["ping", "-n", str(count), host],
            capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        # Parse summary
        stats = {}
        for line in lines:
            line = line.strip()
            if "Verlust" in line or "loss" in line.lower():
                stats["summary"] = line
            if "Minimum" in line or "Average" in line or "Mittelwert" in line:
                stats["timing"] = line

        return {
            "host": host,
            "reachable": result.returncode == 0,
            "output": result.stdout.strip()[-500:],
            **stats,
        }
    except subprocess.TimeoutExpired:
        return {"host": host, "reachable": False, "error": "Timeout"}
    except Exception as e:
        return {"host": host, "reachable": False, "error": str(e)}


def dns_lookup(host: str = "") -> dict:
    """DNS-Lookup für einen Hostnamen."""
    if not host:
        return {"error": t("network.hostnameRequired")}
    if len(host) > 253 or not re.match(r'^[a-zA-Z0-9.\-:]+$', host):
        return {"error": t("validation.invalidHostname")}
    try:
        results = []
        for info in socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
            family, _, _, _, addr = info
            ip = addr[0]
            family_name = "IPv4" if family == socket.AF_INET else "IPv6"
            entry = {"ip": ip, "family": family_name}
            if entry not in results:
                results.append(entry)

        return {
            "host": host,
            "addresses": results,
            "primary_ip": results[0]["ip"] if results else None,
        }
    except socket.gaierror as e:
        return {"host": host, "error": t("network.dnsError", error=str(e))}
    except Exception as e:
        return {"host": host, "error": str(e)}


def port_check(host: str = "127.0.0.1", port: int = 80, timeout: int = 3) -> dict:
    """Prüfen ob ein Port auf einem Host offen ist."""
    if not host:
        return {"error": t("network.hostRequired")}
    if not port:
        return {"error": t("network.portRequired")}
    timeout = max(1, min(10, timeout))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        is_open = result == 0
        return {
            "host": host,
            "port": int(port),
            "open": is_open,
            "status": t("network.portOpen") if is_open else t("network.portClosed"),
        }
    except Exception as e:
        return {"host": host, "port": int(port), "open": False, "error": str(e)}


def network_info() -> dict:
    """Netzwerk-Adapter-Informationen abrufen."""
    try:
        ps = '''
        $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue |
        Where-Object { $_.Status -eq "Up" } |
        ForEach-Object {
            $ip = Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                  Select-Object -First 1
            @{
                name = $_.Name
                description = $_.InterfaceDescription
                status = $_.Status.ToString()
                speed_mbps = [math]::Round($_.LinkSpeed.Split(" ")[0])
                mac = $_.MacAddress
                ip = if ($ip) { $ip.IPAddress } else { "N/A" }
            }
        }
        $adapters | ConvertTo-Json -Depth 2
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data = [data]
            return {"adapters": data}
        return {"adapters": []}
    except Exception as e:
        return {"error": str(e)}


def public_ip() -> dict:
    """Öffentliche IP-Adresse abrufen."""
    try:
        ps = '''
        try {
            $ip = (Invoke-RestMethod -Uri "https://api.ipify.org?format=json" -TimeoutSec 5).ip
            @{ ip = $ip; source = "ipify.org" } | ConvertTo-Json
        } catch {
            try {
                $ip = (Invoke-RestMethod -Uri "https://ifconfig.me/ip" -TimeoutSec 5).Trim()
                @{ ip = $ip; source = "ifconfig.me" } | ConvertTo-Json
            } catch {
                @{ error = "Konnte öffentliche IP nicht abrufen." } | ConvertTo-Json
            }
        }
        '''
        result = subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": t("system.noResponse")}
    except Exception as e:
        return {"error": str(e)}


def traceroute(host: str = "", max_hops: int = 15) -> dict:
    """Traceroute zu einem Host."""
    if not host:
        return {"error": t("network.hostRequired")}
    if len(host) > 253 or not re.match(r'^[a-zA-Z0-9.\-:]+$', host):
        return {"error": t("validation.invalidHostname")}
    max_hops = max(5, min(30, max_hops))
    try:
        result = subprocess.run(
            ["tracert", "-d", "-h", str(max_hops), host],
            capture_output=True, text=True, timeout=60,
        )
        lines = result.stdout.strip().split("\n")
        hops = []
        for line in lines[3:]:
            line = line.strip()
            if line and not line.startswith("Trace") and not line.startswith("Ablauf"):
                hops.append(line)
        return {
            "host": host,
            "hops": hops[:max_hops],
            "hop_count": len(hops),
        }
    except subprocess.TimeoutExpired:
        return {"host": host, "error": t("network.tracerouteTimeout")}
    except Exception as e:
        return {"host": host, "error": str(e)}


def flush_dns() -> str:
    """DNS-Cache leeren."""
    try:
        result = subprocess.run(
            ["ipconfig", "/flushdns"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() or t("network.dnsFlushed")
    except Exception as e:
        return t("error.generic", error=str(e))
