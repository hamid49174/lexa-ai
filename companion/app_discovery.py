"""Lexa AI — Universal App Discovery (Phase 40+)
Professionelles App-Discovery-System für Windows 10/11.
Basiert auf der gleichen Architektur wie PowerToys Run / Flow Launcher.

Tier 1: Protocol URIs (instant, 0ms) — System-Apps wie Einstellungen, Rechner
Tier 2: Get-StartApps Cache (fast fuzzy) — ALLE installierten Apps (Win32 + UWP)
        Gibt automatisch lokalisierte Namen zurück (DE: "Rechner", EN: "Calculator")
Tier 3: Registry App Paths (fallback) — Apps ohne Start Menu Eintrag

Fuzzy Matching: rapidfuzz (C++ Backend, >10x schneller als difflib)
                Fallback auf difflib wenn rapidfuzz nicht installiert.
Launch: shell:AppsFolder\\{AppID} — einheitlich für Win32 + UWP.

KEIN hardcoded Alias-Map — Get-StartApps liefert lokalisierte Namen dynamisch.
"""

import json
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from backend.config import LEXA_DATA_DIR

logger = logging.getLogger("lexa.app_discovery")

# ══════════════════════════════════════════════════
#  FUZZY MATCHING — rapidfuzz (preferred) or difflib (fallback)
# ══════════════════════════════════════════════════

try:
    from rapidfuzz import fuzz as _rf_fuzz
    from rapidfuzz import process as _rf_process
    _HAS_RAPIDFUZZ = True
    logger.debug("rapidfuzz available — using C++ fuzzy matching")
except ImportError:
    _HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher
    logger.debug("rapidfuzz not installed — falling back to difflib")


def _fuzzy_score(query: str, candidate: str) -> float:
    """Score 0-100 how well query matches candidate. Higher = better."""
    if _HAS_RAPIDFUZZ:
        # token_set_ratio handles word order: "Chrome" matches "Google Chrome"
        return _rf_fuzz.token_set_ratio(query, candidate)
    else:
        return SequenceMatcher(None, query.lower(), candidate.lower()).ratio() * 100


def _fuzzy_best_match(query: str, candidates: list[str],
                      threshold: int = 55) -> Optional[tuple[str, float, int]]:
    """Find best fuzzy match. Returns (matched_str, score, index) or None."""
    if not candidates:
        return None
    if _HAS_RAPIDFUZZ:
        result = _rf_process.extractOne(
            query, candidates,
            scorer=_rf_fuzz.token_set_ratio,
            score_cutoff=threshold,
        )
        return result  # (str, score, index) or None
    else:
        # difflib fallback
        best_score = 0.0
        best_idx = -1
        q_lower = query.lower()
        for i, c in enumerate(candidates):
            score = SequenceMatcher(None, q_lower, c.lower()).ratio() * 100
            if score > best_score:
                best_score = score
                best_idx = i
        if best_score >= threshold and best_idx >= 0:
            return (candidates[best_idx], best_score, best_idx)
        return None


# ══════════════════════════════════════════════════
#  PROTOCOL URIs — Instant launch for system apps (Tier 1)
#  These are built into Windows and work on ANY Windows 10/11 PC.
#  No scanning needed — just "start ms-settings:" etc.
# ══════════════════════════════════════════════════

_PROTOCOL_URIS: dict[str, str] = {
    # DE
    "einstellungen": "ms-settings:",
    "systemeinstellungen": "ms-settings:",
    "rechner": "calculator:",
    "taschenrechner": "calculator:",
    "kamera": "microsoft.windows.camera:",
    "karten": "bingmaps:",
    "uhr": "ms-clock:",
    "wecker": "ms-clock:alarm",
    "wetter": "msnweather:",
    "fotos": "ms-photos:",
    "bilder": "ms-photos:",
    # EN
    "settings": "ms-settings:",
    "calculator": "calculator:",
    "camera": "microsoft.windows.camera:",
    "maps": "bingmaps:",
    "clock": "ms-clock:",
    "alarm": "ms-clock:alarm",
    "weather": "msnweather:",
    "photos": "ms-photos:",
    # Common
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
}

# ══════════════════════════════════════════════════
#  MINI ALIAS MAP — Only for abbreviations/nicknames
#  that differ significantly from the actual app name.
#  NOT for translations (Get-StartApps handles that).
# ══════════════════════════════════════════════════

_NICKNAMES: dict[str, list[str]] = {
    # Abbreviations that users type but don't match display names
    "vscode": ["Visual Studio Code"],
    "vs code": ["Visual Studio Code"],
    "npp": ["Notepad++"],
    "cmd": ["Eingabeaufforderung", "Command Prompt"],
    "ps": ["PowerShell", "Windows PowerShell"],
    "7zip": ["7-Zip File Manager", "7-Zip"],
    "7-zip": ["7-Zip File Manager", "7-Zip"],
    "obs": ["OBS Studio"],
    "vlc": ["VLC media player", "VLC"],
    # German generic words → common app categories
    "browser": ["Microsoft Edge", "Google Chrome", "Firefox", "Brave"],
    "editor": ["Notepad", "Notepad++", "Visual Studio Code"],
    "texteditor": ["Notepad", "Notepad++", "Visual Studio Code"],
    "terminal": ["Terminal", "Windows Terminal", "PowerShell"],
    "konsole": ["Terminal", "Windows Terminal", "PowerShell"],
    "kommandozeile": ["Eingabeaufforderung", "PowerShell"],
    "musik": ["Spotify", "Groove-Musik", "Windows Media Player"],
    "mail": ["Outlook", "Mail", "Thunderbird"],
    "taskmanager": ["Task-Manager"],
    "task-manager": ["Task-Manager"],
    "task manager": ["Task-Manager"],
    "gerätemanager": ["Geräte-Manager", "Device Manager"],
    "systemsteuerung": ["Systemsteuerung", "Control Panel"],
    "bildschirmtastatur": ["Bildschirmtastatur"],
    "snipping": ["Snipping Tool", "Ausschneiden und Skizzieren"],
    "aufnahme": ["Sprachrekorder", "Voice Recorder"],
    "zeichnen": ["Paint"],
    "3d": ["Paint 3D", "Blender"],
}

# ══════════════════════════════════════════════════
#  CACHE — Stores Get-StartApps results
# ══════════════════════════════════════════════════

_app_list: list[dict] = []  # [{"name": str, "app_id": str}]
_app_names: list[str] = []  # Parallel list of just names for fuzzy matching
_cache_lock = threading.Lock()
_cache_timestamp: float = 0.0
_CACHE_TTL = 300  # 5 minutes

# Optional: persist cache to disk for faster cold starts
_CACHE_FILE = LEXA_DATA_DIR / "app_cache.json"


# ══════════════════════════════════════════════════
#  DISCOVERY — Get-StartApps (Tier 2, primary)
# ══════════════════════════════════════════════════

def _scan_start_apps() -> list[dict]:
    """Call PowerShell Get-StartApps — returns ALL installed apps (Win32 + UWP).

    This is the same API that PowerToys Run uses internally.
    Returns localized app names automatically (German on German Windows).
    Available on Windows 10/11 (StartLayout module).
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            logger.warning(f"Get-StartApps failed: {result.stderr[:200]}")
            return []

        stdout = result.stdout.strip()
        if not stdout:
            return []

        data = json.loads(stdout)
        if isinstance(data, dict):
            data = [data]

        apps = []
        seen_names: set[str] = set()
        for item in data:
            name = item.get("Name", "").strip()
            app_id = item.get("AppID", "").strip()
            if not name or not app_id or len(name) <= 1:
                continue
            # Skip uninstallers
            name_lower = name.lower()
            if any(skip in name_lower for skip in ("uninstall", "deinstall", "entfernen")):
                continue
            # Deduplicate by name
            if name_lower not in seen_names:
                seen_names.add(name_lower)
                apps.append({"name": name, "app_id": app_id})

        return apps

    except json.JSONDecodeError as e:
        logger.warning(f"Get-StartApps JSON parse error: {e}")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("Get-StartApps timed out (15s)")
        return []
    except Exception as e:
        logger.warning(f"Get-StartApps error: {e}")
        return []


def _scan_registry_app_paths() -> list[dict]:
    """Scan Registry App Paths — catches apps not in Start Menu (Tier 3)."""
    try:
        import winreg
    except ImportError:
        return []

    apps = []
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for hive, path in reg_paths:
        try:
            key = winreg.OpenKey(hive, path)
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    try:
                        exe_path, _ = winreg.QueryValueEx(subkey, "")
                        if exe_path and os.path.isfile(exe_path):
                            # Use filename without .exe as display name
                            name = Path(subkey_name).stem
                            apps.append({
                                "name": name,
                                "app_id": exe_path,  # Direct exe path
                                "_source": "registry",
                            })
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(subkey)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError):
            continue

    return apps


def _scan_path_executables() -> list[dict]:
    """Scan PATH directories for executables (Tier 4).

    Catches CLI tools like git, node, python, code, etc. that users
    might want to launch but aren't in Start Menu or Registry App Paths.
    Only scans for .exe files to avoid noise from .dll, .bat, etc.
    """
    import shutil

    # Well-known CLI tools that users might want to launch
    # Only scan for these to avoid returning 100s of system executables
    _CLI_TOOLS = {
        "git", "node", "npm", "npx", "python", "python3", "pip",
        "code", "cursor", "subl", "atom", "notepad++",
        "cargo", "rustc", "go", "java", "javac", "dotnet",
        "flutter", "dart", "ruby", "perl", "php",
        "conda", "mamba", "jupyter", "ipython",
        "ffmpeg", "ffprobe", "magick", "convert",
        "docker", "kubectl", "terraform", "ansible",
        "aws", "az", "gcloud",
        "wget", "curl", "ssh", "scp", "rsync",
        "mysql", "psql", "mongosh", "redis-cli",
        "nvim", "vim", "nano", "emacs",
        "wt", "alacritty", "kitty",
        "scoop", "choco", "winget",
        "ollama", "yt-dlp",
    }

    apps = []
    seen = set()

    for tool_name in _CLI_TOOLS:
        path = shutil.which(tool_name)
        if path and tool_name not in seen:
            seen.add(tool_name)
            apps.append({
                "name": tool_name,
                "app_id": path,
                "_source": "path",
            })

    return apps


# ══════════════════════════════════════════════════
#  CACHE MANAGEMENT
# ══════════════════════════════════════════════════

def _rebuild_cache() -> None:
    """Rebuild the app cache from Get-StartApps + Registry."""
    global _app_list, _app_names, _cache_timestamp

    logger.info("Rebuilding app discovery cache...")
    t0 = time.time()

    # Primary: Get-StartApps (covers Win32 + UWP, localized names)
    apps = _scan_start_apps()

    # Secondary: Registry App Paths (catches stragglers)
    seen_lower = {a["name"].lower() for a in apps} if apps else set()
    for reg_app in _scan_registry_app_paths():
        if reg_app["name"].lower() not in seen_lower:
            apps.append(reg_app)
            seen_lower.add(reg_app["name"].lower())

    # Tertiary: PATH executables (CLI tools like git, node, python, etc.)
    for path_app in _scan_path_executables():
        if path_app["name"].lower() not in seen_lower:
            apps.append(path_app)
            seen_lower.add(path_app["name"].lower())

    with _cache_lock:
        _app_list = apps
        _app_names = [a["name"] for a in apps]
        _cache_timestamp = time.time()

    elapsed = time.time() - t0
    logger.info(f"App discovery: {len(apps)} apps found in {elapsed:.1f}s")

    # Persist to disk for faster cold starts
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"apps": apps, "timestamp": time.time()}, f, ensure_ascii=False)
    except Exception as e:
        logger.debug(f"Failed to persist app cache: {e}")


def _load_disk_cache() -> bool:
    """Load cached apps from disk (for fast cold starts)."""
    global _app_list, _app_names, _cache_timestamp
    try:
        if not _CACHE_FILE.exists():
            return False
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        ts = data.get("timestamp", 0)
        # Disk cache valid for 1 hour
        if time.time() - ts > 3600:
            return False
        apps = data.get("apps", [])
        if not apps:
            return False
        with _cache_lock:
            _app_list = apps
            _app_names = [a["name"] for a in apps]
            _cache_timestamp = ts
        logger.info(f"Loaded {len(apps)} apps from disk cache")
        return True
    except Exception:
        return False


def _ensure_cache() -> None:
    """Ensure cache is populated."""
    now = time.time()
    if _app_list and (now - _cache_timestamp) < _CACHE_TTL:
        return
    # Try disk cache first (fast), then full scan
    if not _load_disk_cache():
        _rebuild_cache()


def invalidate_cache() -> None:
    """Force cache rebuild on next access."""
    global _cache_timestamp
    _cache_timestamp = 0.0


# ══════════════════════════════════════════════════
#  QUERY NORMALIZATION
# ══════════════════════════════════════════════════

def _normalize_query(query: str) -> str:
    """Normalize user query for matching."""
    q = query.strip()
    if not q:
        return ""
    # Remove common prefixes users add in natural language
    q_lower = q.lower()
    for prefix in ("die app ", "das programm ", "programm ", "app ",
                   "die ", "das ", "den ", "the app ", "the "):
        if q_lower.startswith(prefix):
            q = q[len(prefix):]
            break
    return q.strip()


# ══════════════════════════════════════════════════
#  FIND APP — 3-Tier Resolution
# ══════════════════════════════════════════════════

def find_app(query: str) -> Optional[dict]:
    """Find the best matching app for a user query.

    Resolution order:
    1. Protocol URI (instant, 0ms) — "einstellungen" → ms-settings:
    2. Nickname/abbreviation lookup → fuzzy against cache
    3. Exact match in app list
    4. Substring match (word-boundary)
    5. Fuzzy match via rapidfuzz/difflib

    Returns: {"name": str, "app_id": str, "match_type": str, "score": float}
    or None if no match found.
    """
    if not query:
        return None

    q = _normalize_query(query)
    if not q:
        return None
    q_lower = q.lower()

    # ── Tier 1: Protocol URIs (instant) ──
    if q_lower in _PROTOCOL_URIS:
        return {
            "name": q.title(),
            "app_id": _PROTOCOL_URIS[q_lower],
            "match_type": "protocol",
            "score": 100,
            "_launch": "uri",
        }

    # ── Ensure cache is ready ──
    _ensure_cache()

    # ── Tier 2a: Exact match ──
    for i, app in enumerate(_app_list):
        if app["name"].lower() == q_lower:
            return {**app, "match_type": "exact", "score": 100}

    # ── Tier 2b: Nickname resolution ──
    if q_lower in _NICKNAMES:
        targets = _NICKNAMES[q_lower]
        for target in targets:
            target_lower = target.lower()
            for app in _app_list:
                if app["name"].lower() == target_lower:
                    return {**app, "match_type": "nickname", "score": 95}
            # Partial match on display name
            for app in _app_list:
                app_lower = app["name"].lower()
                if target_lower in app_lower or app_lower.startswith(target_lower):
                    return {**app, "match_type": "nickname", "score": 90}

    # ── Tier 2c: Substring match (word-boundary aware) ──
    best_sub: Optional[dict] = None
    best_sub_len = 999

    for app in _app_list:
        app_lower = app["name"].lower()

        # Query is substring of app name (with word boundary)
        idx = app_lower.find(q_lower)
        if idx >= 0 and (idx == 0 or not app_lower[idx - 1].isalpha()):
            if len(app_lower) < best_sub_len:
                best_sub = {**app, "match_type": "substring", "score": 85}
                best_sub_len = len(app_lower)

    if best_sub:
        return best_sub

    # ── Tier 2d: Fuzzy match ──
    # Higher threshold for short queries to avoid false positives
    fuzzy_threshold = 80 if len(q) <= 5 else 70 if len(q) <= 8 else 65
    match = _fuzzy_best_match(q, _app_names, threshold=fuzzy_threshold)
    if match:
        name, score, idx = match
        # Extra validation: reject matches where query shares no common word start
        # This prevents "blender" → "Kalender", "telegram" → "Steam"
        name_lower = name.lower()
        q_words = set(re.findall(r"[a-zäöüß0-9]+", q_lower))
        name_words = set(re.findall(r"[a-zäöüß0-9]+", name_lower))
        has_word_overlap = any(
            nw.startswith(qw[:3]) or qw.startswith(nw[:3])
            for qw in q_words for nw in name_words
            if len(qw) >= 3 and len(nw) >= 3
        )
        if has_word_overlap or q_lower.startswith(name_lower[:3]) or name_lower.startswith(q_lower[:3]):
            return {**_app_list[idx], "match_type": "fuzzy", "score": round(score, 1)}

    # ── Tier 3: Registry fallback (already in cache from _rebuild_cache) ──
    # If nothing found, return None
    return None


# ══════════════════════════════════════════════════
#  SEARCH APPS — Multiple results
# ══════════════════════════════════════════════════

def search_apps(query: str, limit: int = 10) -> list[dict]:
    """Search installed apps. Returns top matches sorted by relevance."""
    if not query:
        return []

    q = _normalize_query(query)
    if not q:
        return []

    _ensure_cache()
    q_lower = q.lower()

    results: list[tuple[float, dict]] = []

    for i, app in enumerate(_app_list):
        app_lower = app["name"].lower()

        # Exact
        if app_lower == q_lower:
            results.append((100, {**app, "match_type": "exact"}))
            continue

        # Substring
        if q_lower in app_lower:
            score = 80 + (len(q) / max(len(app_lower), 1)) * 20
            results.append((score, {**app, "match_type": "substring"}))
            continue

        # Fuzzy
        score = _fuzzy_score(q, app["name"])
        if score >= 45:
            results.append((score, {**app, "match_type": "fuzzy"}))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:limit]]


def list_installed_apps(limit: int = 100) -> list[dict]:
    """List all discovered installed apps."""
    _ensure_cache()
    apps = sorted(_app_list, key=lambda a: a["name"].lower())
    return [{"name": a["name"], "app_id": a["app_id"]} for a in apps[:limit]]


# ══════════════════════════════════════════════════
#  APP LAUNCHER
# ══════════════════════════════════════════════════

def launch_app(query: str, path: str = "") -> str:
    """Smart app launcher — resolves query and launches the app.

    Args:
        query: App name (natural language, any language)
        path: Optional direct .exe path (bypasses discovery)

    Returns: Status message string
    """
    # Direct path launch (bypasses discovery)
    if path:
        from backend.security import validate_path
        try:
            safe_path = validate_path(path)
        except ValueError as e:
            return f"Pfad blockiert: {e}"
        try:
            subprocess.Popen([safe_path], shell=False)
            return f"{os.path.basename(safe_path)} geöffnet."
        except Exception as e:
            return f"Fehler beim Starten: {e}"

    if not query:
        return "Kein App-Name angegeben."

    # Resolve via 3-tier discovery
    match = find_app(query)

    if not match:
        return f"App '{query}' nicht gefunden. Tipp: Sag 'suche app {query}' für ähnliche Treffer."

    app_name = match["name"]
    app_id = match.get("app_id", "")
    launch_type = match.get("_launch", "")
    match_type = match.get("match_type", "")
    score = match.get("score", 0)

    logger.info(f"App resolved: '{query}' → '{app_name}' (score={score}, {match_type})")

    try:
        if launch_type == "uri":
            # Protocol URI launch (ms-settings:, calculator:, etc.)
            subprocess.Popen(["cmd", "/c", "start", "", app_id], shell=False)
            return f"{app_name} geöffnet."

        elif app_id and os.path.isfile(app_id):
            # Direct .exe path (from Registry App Paths)
            subprocess.Popen([app_id], shell=False)
            return f"{app_name} geöffnet."

        elif app_id:
            # shell:AppsFolder launch — works for BOTH Win32 and UWP
            subprocess.Popen(
                ["explorer", f"shell:AppsFolder\\{app_id}"],
                shell=False,
            )
            return f"{app_name} geöffnet."

        else:
            return f"App '{app_name}' hat keine startbare ID."

    except Exception as e:
        logger.error(f"Failed to launch '{app_name}': {e}", exc_info=True)
        return f"Fehler beim Starten von '{app_name}': {e}"


# ══════════════════════════════════════════════════
#  INIT — Warm cache on import (non-blocking)
# ══════════════════════════════════════════════════

def warm_cache_async() -> None:
    """Start cache build in background thread."""
    def _init():
        if not _load_disk_cache():
            _rebuild_cache()
        else:
            # Disk cache loaded, refresh in background
            _rebuild_cache()

    t = threading.Thread(target=_init, daemon=True, name="app-discovery")
    t.start()


# Auto-warm on import (non-blocking)
warm_cache_async()
