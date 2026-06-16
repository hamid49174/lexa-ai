"""Lexa AI — Security Module
Input-Validierung, Rate Limiting, Command Whitelist, Audit Log, Path/URL Protection
"""

import os
import json
import sys
import time
import re
import hashlib
import logging
import threading
import unicodedata
import ipaddress
from pathlib import Path
from collections import deque
from datetime import datetime
from urllib.parse import urlparse

from backend.config import (
    LEXA_DATA_DIR,
    RATE_LIMIT_AUDIT_READ,
    RATE_LIMIT_CHAT,
    RATE_LIMIT_DEFAULT,
    RATE_LIMIT_EXECUTE,
    RATE_LIMIT_STRIPE_READ,
    RATE_LIMIT_VISION,
    RATE_LIMIT_VOICE,
    RATE_LIMIT_WORKFLOWS,
)
from backend.i18n import t

logger = logging.getLogger("lexa.security")

PROJECT_ROOT = Path(__file__).parent.parent
WHITELIST_PATH = PROJECT_ROOT / "command_whitelist.json"

AUDIT_LOG_PATH = LEXA_DATA_DIR / "audit.log"

# Rate Limiting — per endpoint type, thread-safe with lock
_rate_limit_lock = threading.Lock()
_RATE_LIMITS: dict[str, dict] = {
    "chat": {"max": RATE_LIMIT_CHAT, "timestamps": deque()},
    "execute": {"max": RATE_LIMIT_EXECUTE, "timestamps": deque()},  # PC-Befehle strenger
    "voice": {"max": RATE_LIMIT_VOICE, "timestamps": deque()},  # Voice großzügiger
    "vision": {"max": RATE_LIMIT_VISION, "timestamps": deque()},  # Vision-API (Screenshot + Analyse)
    "workflows": {"max": RATE_LIMIT_WORKFLOWS, "timestamps": deque()},  # Workflow-Operationen
    "stripe_read": {"max": RATE_LIMIT_STRIPE_READ, "timestamps": deque()},  # Stripe read endpoints (no auth)
    "audit_read": {"max": RATE_LIMIT_AUDIT_READ, "timestamps": deque()},  # Read-only UI trust/history surfaces
    "default": {"max": RATE_LIMIT_DEFAULT, "timestamps": deque()},
}
_ACTION_RATE_LIMITS: dict[str, dict] = {
    "execute": {"max": RATE_LIMIT_EXECUTE, "entries": deque()},
}
_ACTION_RATE_COSTS: dict[str, int] = {
    "file_delete": 5,
    "folder_delete": 5,
    "file_write": 4,
    "file_move": 4,
    "file_rename": 4,
    "process_kill": 4,
    "shutdown": 5,
    "restart": 5,
    "shell_command": 5,
    "run_command": 5,
    "clipboard_write": 2,
    "ui_click": 3,
    "desktop_click": 3,
    "desktop_click_text": 3,
    "desktop_hotkey": 3,
    "desktop_move": 2,
    "desktop_scroll": 2,
    "desktop_type": 4,
    "hermes_desktop_commit": 4,
    "volume_set": 2,
    "app_open": 2,
}
_READ_ONLY_ACTIONS: frozenset[str] = frozenset({
    "system_info",
    "battery_status",
    "screenshot",
    "weather_check",
    "time_now",
    "date_today",
    "file_read",
    "folder_list",
    "clipboard_read",
    "ui_tree",
    "ui_find",
    "desktop_engine_status",
    "desktop_engine_observe",
    # hermes_desktop_task ist NICHT read-only: es bereitet ueber set_pending_confirmation
    # mutierende Desktop-Aktionen (Klick/Tippen/Hotkey) vor -> darf nie als read-only
    # zaehlen (weder Rate-Limit-Rabatt noch Stream-Auto-Ausfuehrung). Confused-Deputy-Schutz.
    "desktop_position",
    "desktop_wait",
    "window_list",
    "process_list",
    "memory_search",
    "file_search",
    "app_list",
    "app_search",
    "app_list_installed",
    "wifi_status",
    "brightness_get",
})
_READ_ONLY_PREFIXES: tuple[str, ...] = (
    "get_",
    "list_",
    "read_",
    "search_",
    "find_",
    "status_",
)
# Legacy alias (backward-compat)
_command_timestamps = _RATE_LIMITS["default"]["timestamps"]
MAX_COMMANDS_PER_MINUTE = RATE_LIMIT_DEFAULT

# Zero-width characters to strip from input
_ZERO_WIDTH_CHARS = re.compile(
    "[\u200b\u200c\u200d\u200e\u200f"   # zero-width space, joiners, marks
    "\u2060\u2061\u2062\u2063\u2064"     # word joiner, invisible operators
    "\ufeff"                              # BOM / zero-width no-break space
    "\u00ad"                              # soft hyphen
    "\u034f"                              # combining grapheme joiner
    "\u061c"                              # Arabic letter mark
    "\u115f\u1160"                        # Hangul fillers
    "\u17b4\u17b5"                        # Khmer vowel inherent
    "\u180e"                              # Mongolian vowel separator
    "\uffa0"                              # Halfwidth Hangul filler
    "\ufff0-\ufff8"                       # specials
    "]+"
)


def load_whitelist() -> dict:
    try:
        with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load command whitelist from {WHITELIST_PATH}: {e}")
        # Deny-all fallback — no commands allowed if whitelist is missing/corrupt
        return {"commands": {
            "always_allowed": {"list": []},
            "confirmation_required": {"list": []},
            "always_blocked": {"list": []},
        }}


def _normalize_whitelist_sets(whitelist: dict) -> dict[str, frozenset[str]]:
    """Pre-compute lower-cased command sets once (avoids re-normalizing per call)."""
    commands = whitelist.get("commands", {})

    def _normalized(tier: str) -> frozenset[str]:
        return frozenset(
            c.strip().lower()
            for c in commands.get(tier, {}).get("list", [])
        )

    return {
        "always_allowed": _normalized("always_allowed"),
        "confirmation_required": _normalized("confirmation_required"),
        "always_blocked": _normalized("always_blocked"),
    }


_whitelist = load_whitelist()
_whitelist_sets = _normalize_whitelist_sets(_whitelist)


def reload_whitelist():
    """Reload whitelist from file (hot-reload)."""
    global _whitelist, _whitelist_sets
    _whitelist = load_whitelist()
    _whitelist_sets = _normalize_whitelist_sets(_whitelist)


def is_command_allowed(command: str) -> str:
    """Check if a command is allowed.
    Returns: 'allowed', 'confirmation_required', 'blocked', or 'unknown'
    """
    command = command.strip().lower()

    if command in _whitelist_sets["always_blocked"]:
        return "blocked"
    if command in _whitelist_sets["always_allowed"]:
        return "allowed"
    if command in _whitelist_sets["confirmation_required"]:
        return "confirmation_required"
    return "unknown"


def check_rate_limit(endpoint_type: str = "default") -> bool:
    """Returns True if within rate limit, False if exceeded.

    Thread-safe: all deque operations are protected by a lock to prevent
    race conditions under concurrent FastAPI requests.

    endpoint_type: 'chat', 'execute', 'voice', 'audit_read', or 'default'
    """
    bucket = _RATE_LIMITS.get(endpoint_type, _RATE_LIMITS["default"])
    now = time.time()
    cutoff = now - 60
    with _rate_limit_lock:
        timestamps = bucket["timestamps"]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= bucket["max"]:
            return False
        timestamps.append(now)
        return True


def is_read_only_action(action_name: str) -> bool:
    normalized = str(action_name or "").strip().lower()
    return normalized in _READ_ONLY_ACTIONS or normalized.startswith(_READ_ONLY_PREFIXES)


def action_rate_limit_cost(action_name: str) -> int:
    normalized = str(action_name or "").strip().lower()
    if is_read_only_action(normalized):
        return 1
    return max(1, _ACTION_RATE_COSTS.get(normalized, 2))


def check_action_rate_limit(action_name: str, endpoint_type: str = "execute") -> dict:
    """Risk-weighted action budget for actual command execution."""
    bucket = _ACTION_RATE_LIMITS.get(endpoint_type, _ACTION_RATE_LIMITS["execute"])
    now = time.time()
    cutoff = now - 60
    cost = action_rate_limit_cost(action_name)
    read_only = is_read_only_action(action_name)

    with _rate_limit_lock:
        entries = bucket["entries"]
        while entries and entries[0][0] < cutoff:
            entries.popleft()
        used = sum(entry_cost for _ts, entry_cost in entries)
        remaining = max(0, bucket["max"] - used)
        if used + cost > bucket["max"]:
            return {
                "allowed": read_only,
                "read_only": read_only,
                "read_only_only": True,
                "cost": 0 if read_only else cost,
                "limit": bucket["max"],
                "used": used,
                "remaining": remaining,
                "reset_in_seconds": 60,
            }
        entries.append((now, cost))
        return {
            "allowed": True,
            "read_only": read_only,
            "read_only_only": False,
            "cost": cost,
            "limit": bucket["max"],
            "used": used + cost,
            "remaining": max(0, bucket["max"] - used - cost),
            "reset_in_seconds": 60,
        }


# ══════════════════════════════════════════════════
#  INPUT SANITIZATION
# ══════════════════════════════════════════════════

INJECTION_PATTERNS: list[str] = [
    r"ignore previous instructions",
    r"ignore all previous",
    r"disregard.*instructions",
    r"you are now",
    r"new instructions:",
    r"system prompt:",
    r"forget your rules",
    r"override.*safety",
    r"jailbreak",
    r"DAN mode",
    r"bypass.*filter",
    r"act as.*unrestricted",
    r"pretend you.*no restrictions",
    r"<\|system\|>",
    r"<\|endoftext\|>",
    r"\[INST\]",
    r"\[/INST\]",
    # Additional patterns
    r"do anything now",
    r"developer mode",
    r"sudo mode",
    r"admin mode",
    r"god mode",
    r"unrestricted mode",
    r"no restrictions",
    r"ignore.*safety",
    r"ignore.*rules",
    r"break.*character",
    r"break character",
    r"stay in character",
    r"roleplay as",
    r"simulate.*AI",
    r"you have no.*limit",
    r"<system>",
    r"</system>",
    r"\{\{.*\}\}",         # Template injection
    r"##\s*instruction",   # Markdown injection
    r"---\s*system",       # YAML-style injection
]

# Pre-compile all injection patterns at module load for performance
_COMPILED_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS
]


def sanitize_input(user_input: str, max_chars: int = 2000) -> str:
    """Sanitize user input to prevent prompt injection.

    Applies:
    1. Unicode NFKC normalization (catches homoglyph attacks)
    2. Zero-width character stripping (catches invisible char smuggling)
    3. Injection pattern filtering (36 compiled regex patterns)
    4. Length truncation (default max 2000 chars)

    max_chars: Truncation limit. Callers that allow longer payloads (e.g. the
    chat router with MAX_CHAT_MESSAGE_LENGTH) can raise this to avoid silently
    cutting valid input. Defaults to 2000 for backward compatibility.
    """
    # Normalize unicode to catch homoglyph attacks (e.g. ｉｇｎｏｒｅ → ignore)
    sanitized = unicodedata.normalize("NFKC", user_input)

    # Strip zero-width characters that could be used to evade pattern matching
    sanitized = _ZERO_WIDTH_CHARS.sub("", sanitized)

    # Apply pre-compiled injection patterns
    for compiled in _COMPILED_PATTERNS:
        sanitized = compiled.sub("[FILTERED]", sanitized)

    if len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars]
    return sanitized


# ══════════════════════════════════════════════════
#  OUTPUT VALIDATION
# ══════════════════════════════════════════════════

DANGEROUS_COMMANDS: list[str] = [
    "rm -rf", "del /f /s", "format c:", "rmdir /s /q",
    "reg delete", "netsh advfirewall set", "powershell -enc",
    "powershell -encodedcommand", "cmd /c del",
    "shutdown -s -t 0", "bcdedit", "diskpart", "cipher /w",
    "schtasks /delete", "wmic shadowcopy delete",
]


def validate_command_output(output: str) -> str:
    """Validate and sanitize KI output before executing as command.

    Defense-in-depth scanner: matches against DANGEROUS_COMMANDS after
    collapsing all whitespace runs (spaces, tabs, newlines) to a single space,
    so trivial whitespace-padding bypasses like 'rm  -rf' or 'rm\\t-rf' are
    still caught. This is a heuristic blocklist, not the primary gate — command
    authorization happens via is_command_allowed / the whitelist.
    """
    normalized = re.sub(r"\s+", " ", output).lower()
    for cmd in DANGEROUS_COMMANDS:
        if re.sub(r"\s+", " ", cmd).lower() in normalized:
            raise ValueError(f"Dangerous command detected in AI output: {cmd}")
    return output


# ══════════════════════════════════════════════════
#  PATH VALIDATION
# ══════════════════════════════════════════════════

BLOCKED_PATHS: list[str] = [
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64",
    "C:\\Windows\\Boot",
    "C:\\Windows\\Security",
    "C:\\Windows\\Fonts",
    "C:\\Windows\\WinSxS",
    "C:\\ProgramData\\Microsoft\\Windows\\Start Menu",
    "C:\\$Recycle.Bin",
]


def _is_same_or_child_path(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_path(path_str: str) -> str:
    """Validate a file/directory path is safe to access."""
    if not path_str:
        return path_str

    raw_path = Path(path_str)
    resolved_path = raw_path.resolve()

    # Reject traversal only on real path segments ('..'), not on filenames that
    # merely contain '..' as a substring (e.g. 'release..notes.txt').
    if ".." in raw_path.parts:
        raise ValueError("Pfad-Traversierung nicht erlaubt")

    for blocked in BLOCKED_PATHS:
        blocked_path = Path(blocked).resolve()
        if _is_same_or_child_path(resolved_path, blocked_path):
            raise ValueError(t("security.blockedDir", dir=blocked))

    return str(resolved_path)


# ══════════════════════════════════════════════════
#  URL VALIDATION
# ══════════════════════════════════════════════════

# Cloud metadata endpoints — SSRF protection
_BLOCKED_HOSTS: frozenset[str] = frozenset({
    # AWS / DigitalOcean / Oracle Cloud metadata (shared link-local IP)
    "169.254.169.254",
    # Azure metadata
    "169.254.169.253",
    # GCP metadata (non-IP hostnames; IP literals are caught by is_dangerous_network_ip)
    "metadata.google.internal",
    "metadata.google",
    # Alibaba Cloud metadata
    "100.100.100.200",
    # Generic link-local
    "169.254.0.1",
})
_LOCAL_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
})


def is_dangerous_network_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, or reserved.

    Also handles IPv6-mapped IPv4 addresses (e.g. ::ffff:127.0.0.1).
    """
    # For IPv6-mapped IPv4 (e.g. ::ffff:127.0.0.1), check the mapped IPv4 address
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


_is_dangerous_ip = is_dangerous_network_ip


def validate_url(url: str) -> str:
    """Validate a URL is safe to access (SSRF protection).

    Detects private/loopback/link-local/reserved targets two ways: (1) direct parse of a
    canonical IP host, and (2) for non-canonical hosts (DNS names AND alternate IP notations
    like decimal/hex/octal/short-form, which the ipaddress module does NOT parse) by resolving
    the host and checking every resolved address. Unresolvable hosts are left to fail at the
    actual request layer (they cannot reach an internal target).
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urlparse(url)

    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsicheres URL-Schema: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Ungueltige URL: Host fehlt")

    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Ungueltige URL: Port ist ungueltig") from exc

    hostname_lower = hostname.lower().strip("[]").rstrip(".")

    # Check exact blocked hosts (cloud metadata endpoints, etc.)
    if hostname_lower in _BLOCKED_HOSTS:
        raise ValueError(t("security.blockedInternal", host=hostname))
    if hostname_lower in _LOCAL_HOSTNAMES or hostname_lower.endswith(".localhost"):
        raise ValueError(t("security.blockedInternal", host=hostname))

    # Try to parse as IP address (handles all notations: dotted, hex, decimal, IPv6)
    try:
        addr = ipaddress.ip_address(hostname_lower)
    except ValueError:
        addr = None

    if addr is not None and is_dangerous_network_ip(addr):
        raise ValueError(t("security.blockedPrivate", host=hostname))

    # Nicht-kanonische Hosts (DNS-Namen + alternative IP-Notationen decimal/hex/octal/short)
    # aufloesen und JEDE Adresse pruefen — sonst umgehen z.B. http://2130706433/ oder
    # http://0x7f.0.0.1/ den Loopback-Schutz. Aufloesungsfehler sind nicht fatal.
    if addr is None:
        try:
            import socket
            infos = socket.getaddrinfo(hostname_lower, None)
        except Exception:
            infos = []
        for info in infos:
            try:
                resolved = ipaddress.ip_address(info[4][0])
            except (ValueError, IndexError, TypeError):
                continue
            if is_dangerous_network_ip(resolved):
                raise ValueError(t("security.blockedPrivate", host=hostname))

    return url


# ══════════════════════════════════════════════════
#  PARAM VALIDATION
# ══════════════════════════════════════════════════

PATH_PARAM_KEYS: frozenset[str] = frozenset({
    "path", "search_path", "folder", "input_path", "output_path",
    "video_path", "pdf_path", "pdf_paths", "downloads_path", "save_path",
    "backup_path", "attachment_path", "repo_path", "file_path", "dir_path", "log_path",
})

COMMAND_PATH_PARAM_KEYS: dict[str, frozenset[str]] = {
    "archive_create": frozenset({"source", "output"}),
    "archive_extract": frozenset({"archive_path", "dest", "destination"}),
    "backup_create": frozenset({"source", "dest", "destination"}),
    "file_move": frozenset({"source", "destination"}),
    "file_copy": frozenset({"source", "destination"}),
}

URL_PARAM_KEYS: frozenset[str] = frozenset({
    "url", "urls",
})


def _is_path_param(command: str, key: str) -> bool:
    return key in PATH_PARAM_KEYS or key in COMMAND_PATH_PARAM_KEYS.get(command, frozenset())


def _max_string_param_length(command: str, key: str) -> int:
    if command == "file_write" and key == "content":
        return 200_000
    if command == "desktop_type" and key == "text":
        return 1000
    if command == "hermes_desktop_task" and key == "message":
        return 1600
    if command == "hermes_desktop_commit" and key == "typing_text":
        return 1000
    if command in {"desktop_click_text", "ui_find", "ui_click", "hermes_desktop_commit"} and key == "text":
        return 80
    return 5000


def validate_params(command: str, params: dict, _depth: int = 0) -> dict:
    """Validate command parameters for safety. Recurses into nested dicts/lists (max depth 3)."""
    if _depth > 3:
        raise ValueError("Parameter-Verschachtelung zu tief (max 3 Ebenen).")
    clean = {}
    for key, value in params.items():
        if isinstance(value, str):
            max_len = _max_string_param_length(command, key)
            if len(value) > max_len:
                value = value[:max_len]
            if _is_path_param(command, key):
                value = validate_path(value)
            if key in URL_PARAM_KEYS:
                value = validate_url(value)
        elif isinstance(value, dict):
            value = validate_params(command, value, _depth + 1)
        elif isinstance(value, list):
            value = _validate_param_list(command, key, value, _depth + 1)
        clean[key] = value
    return clean


def _validate_param_list(command: str, key: str, items: list, depth: int) -> list:
    """Validate list items recursively."""
    if depth > 3:
        raise ValueError("Parameter-Verschachtelung zu tief (max 3 Ebenen).")
    result = []
    for item in items:
        if isinstance(item, str):
            if len(item) > 5000:
                item = item[:5000]
            if _is_path_param(command, key):
                item = validate_path(item)
            if key in URL_PARAM_KEYS:
                item = validate_url(item)
        elif isinstance(item, dict):
            item = validate_params(command, item, depth)
        elif isinstance(item, list):
            item = _validate_param_list(command, key, item, depth + 1)
        result.append(item)
    return result


# ══════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════

_AUDIT_LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB max
_AUDIT_READ_MAX_BYTES: int = 2 * 1024 * 1024  # Bounded read window for UI summaries
_audit_lock = threading.Lock()
_AUDIT_ENTRY_RE = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+CMD=(?P<command>\S+)\s+STATUS=(?P<status>\S+)(?:\s+(?P<details>.*))?$"
)
_AUDIT_NOISE_COMMANDS: frozenset[str] = frozenset({"system_info", "system_uptime"})
_AUDIT_DETAIL_PAIR_RE = re.compile(
    r"(?P<prefix>(?:^|\s)(?P<key>[A-Za-z_][\w.-]{0,40})=)(?P<value>.*?)(?=(?:\s+[A-Za-z_][\w.-]{0,40}=)|$)"
)
_AUDIT_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_AUDIT_LOCAL_PATH_RE = re.compile(
    # Laufwerks-, UNC/Long-Path- und Unix-/WSL-Pfade (siehe router_chat._LOCAL_PATH_RE).
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>|]+|\\\\[^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc|mnt)/[^\s\"'<>|]+)"
)
_AUDIT_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_AUDIT_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>api[_-]?key|apikey|authorization|credential|password|secret|token)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_AUDIT_SENSITIVE_DETAIL_KEYS: frozenset[str] = frozenset({
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "content",
    "credential",
    "credentials",
    "directory",
    "email",
    "err",
    "error",
    "exception",
    "file",
    "file_path",
    "filepath",
    "filename",
    "folder",
    "input",
    "message",
    "msg",
    "output",
    "password",
    "path",
    "prompt",
    "query",
    "repo_path",
    "reply",
    "response",
    "reason",
    "secret",
    "source",
    "target",
    "text",
    "token",
    "traceback",
    "transcript",
    "url",
    "user_id",
})
_AUDIT_KEYLESS_REDACT_COMMANDS: frozenset[str] = frozenset({
    "stripe_checkout",
    "stripe_portal",
    "stripe_webhook",
})
_AUDIT_KEYLESS_REDACT_STATUS_MARKERS: tuple[str, ...] = (
    "dangerous",
    "error",
    "invalid",
    "param",
    "signature",
)


def _rotate_audit_log() -> None:
    """Rotate audit log if it exceeds max size. Must be called under _audit_lock."""
    try:
        if not AUDIT_LOG_PATH.exists():
            return
        size = AUDIT_LOG_PATH.stat().st_size
        if size < _AUDIT_LOG_MAX_BYTES:
            return
        # Rotate: rename current log to .1, remove old .1 if exists
        rotated = AUDIT_LOG_PATH.with_suffix(".log.1")
        if rotated.exists():
            rotated.unlink()
        AUDIT_LOG_PATH.rename(rotated)
        logger.info(f"Audit-Log rotiert ({size // 1024} KB) -> {rotated.name}")
    except Exception as e:
        logger.warning(f"Audit-Log Rotation fehlgeschlagen: {e}")


def _safe_audit_component(value: object, *, fallback: str, max_chars: int = 120) -> str:
    """Return a command/status component that cannot inject audit lines."""
    text = str(value or "").strip()
    if _AUDIT_COMPONENT_RE.match(text):
        return text[:max_chars]
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{fallback}_{digest}"


def _redact_audit_freeform_text(value: str) -> str:
    text = _AUDIT_LOCAL_PATH_RE.sub("[local-path-redacted]", str(value or ""))
    text = _AUDIT_EMAIL_RE.sub("[email-redacted]", text)
    return _AUDIT_SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}=[redacted]",
        text,
    )


def _safe_audit_entry(command: object, status: object, details: object = "") -> str:
    safe_command = _safe_audit_component(command, fallback="command")
    safe_status = _safe_audit_component(status, fallback="status", max_chars=80)
    raw_details = _clip_audit_field(str(details or ""), 2000)
    if raw_details and _should_redact_keyless_audit_details(safe_command, safe_status, raw_details):
        safe_details = "[redacted]"
    else:
        safe_details, _redacted_fields = _redact_audit_details(raw_details)
    suffix = f" {safe_details}" if safe_details else ""
    return f"CMD={safe_command} STATUS={safe_status}{suffix}"


def audit_log(command: str, status: str, details: str = "") -> None:
    """Log every command execution to audit log (with rotation at 10 MB).

    Falls back to stderr if file writing fails.
    """
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] {_safe_audit_entry(command, status, details)}\n"
    try:
        with _audit_lock:
            _rotate_audit_log()
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(entry)
    except Exception as e:
        # Don't swallow errors — log to stderr as fallback
        print(f"[AUDIT FALLBACK] {entry.strip()} (write failed: {e})", file=sys.stderr)
    # audit.log is the authoritative, rotated sink. Mirror to the general logger
    # only at debug level so (already redacted) audit lines aren't duplicated into
    # stdout/app log, which has different retention/rotation than audit.log.
    logger.debug(entry.strip())


def audit_safe_token(value: object, *, fallback: str = "unknown", max_chars: int = 80) -> str:
    """Return a compact token safe for raw audit metadata values."""
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "_", text).strip("_")
    if not text:
        return fallback
    return text[:max_chars]


def audit_value_metadata(label: str, value: object) -> str:
    """Return length/hash metadata without writing the raw value."""
    safe_label = audit_safe_token(label, fallback="value", max_chars=40)
    text = str(value or "")
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{safe_label}Chars={len(text)} {safe_label}Hash={digest}"


def audit_error_details(error: object, *, source: object | None = None) -> str:
    """Return client/support useful error metadata without raw paths, prompts, or secrets."""
    parts: list[str] = []
    if source is not None:
        parts.append(f"source={audit_safe_token(source)}")
    error_type = type(error).__name__ if not isinstance(error, str) else "message"
    parts.append(f"errorType={audit_safe_token(error_type, fallback='error')}")
    parts.append(audit_value_metadata("error", error))
    return " ".join(parts)


def audit_param_keys_details(params: object) -> str:
    """Return safe parameter-key metadata without values or sensitive key names."""
    if not isinstance(params, dict):
        return "paramCount=0 paramKeys=none"
    keys: list[str] = []
    for key in sorted(str(item) for item in params.keys()):
        if _is_sensitive_audit_key(key):
            keys.append("[sensitive]")
        else:
            keys.append(audit_safe_token(key, fallback="key", max_chars=40))
    clipped = keys[:20]
    key_text = ",".join(clipped) if clipped else "none"
    if len(keys) > len(clipped):
        key_text += ",..."
    return f"paramCount={len(keys)} paramKeys={key_text}"


def _clip_audit_field(value: str, max_chars: int = 500) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 12].rstrip() + " [truncated]"


def _is_sensitive_audit_key(key: str) -> bool:
    normalized = _normalize_audit_key(key)
    return (
        normalized in _AUDIT_SENSITIVE_DETAIL_KEYS
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_api_key")
    )


def _normalize_audit_key(key: str) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def _redact_audit_details(details: str) -> tuple[str, list[str]]:
    """Redact user content, paths, and secrets from UI-facing audit summaries."""
    text = _clip_audit_field(details, 2000)
    if not text:
        return "", []

    redacted_fields: list[str] = []
    seen_fields: set[str] = set()

    def replace(match: re.Match) -> str:
        key = match.group("key")
        if not _is_sensitive_audit_key(key):
            return match.group(0)
        normalized = _normalize_audit_key(key)
        if normalized not in seen_fields:
            seen_fields.add(normalized)
            redacted_fields.append(normalized)
        return f"{match.group('prefix')}[redacted]"

    redacted = _AUDIT_DETAIL_PAIR_RE.sub(replace, text)
    freeform_redacted = _redact_audit_freeform_text(redacted)
    if freeform_redacted != redacted and "freeform" not in seen_fields:
        redacted_fields.append("freeform")
    return freeform_redacted, redacted_fields


def _should_redact_keyless_audit_details(command: str, status: str, details: str) -> bool:
    if not str(details or "").strip():
        return False
    normalized_command = _normalize_audit_key(command)
    normalized_status = _normalize_audit_key(status)
    return (
        normalized_command in _AUDIT_KEYLESS_REDACT_COMMANDS
        or any(marker in normalized_status for marker in _AUDIT_KEYLESS_REDACT_STATUS_MARKERS)
    )


def _parse_audit_entry(line: str) -> dict | None:
    match = _AUDIT_ENTRY_RE.match(line.strip())
    if not match:
        return None
    command = match.group("command")
    status = match.group("status")
    raw_details = match.group("details") or ""
    if _should_redact_keyless_audit_details(command, status, raw_details):
        details = "[redacted]"
        redacted_fields = ["details"]
    else:
        details, redacted_fields = _redact_audit_details(raw_details)
    return {
        "timestamp": _clip_audit_field(match.group("timestamp"), 80),
        "command": _clip_audit_field(command, 120),
        "status": _clip_audit_field(status, 80),
        "details": _clip_audit_field(details, 500),
        "redacted": bool(redacted_fields),
        "redacted_fields": redacted_fields,
    }


def _is_low_signal_audit_entry(entry: dict) -> bool:
    command = str(entry.get("command") or "").lower()
    status = str(entry.get("status") or "").lower()
    details = str(entry.get("details") or "").strip()
    return command in _AUDIT_NOISE_COMMANDS and status == "executed" and details in ("", "params=[]")


def _read_audit_log_tail_lines() -> tuple[list[str], dict]:
    """Read a bounded tail window from audit.log for UI summaries."""
    size = AUDIT_LOG_PATH.stat().st_size
    start = max(0, size - _AUDIT_READ_MAX_BYTES)
    metadata = {
        "log_size_bytes": size,
        "read_window_bytes": size - start,
        "tail_limited": start > 0,
    }
    with open(AUDIT_LOG_PATH, "rb") as f:
        if start > 0:
            f.seek(start)
            f.readline()  # discard the partial line at the byte cut boundary
        return f.read().decode("utf-8", errors="replace").splitlines(), metadata


def read_recent_audit_entries(limit: int = 50, hide_noise: bool = False) -> dict:
    """Return recent audit-log entries in reverse chronological order.

    This is read-only and intentionally exposes the parsed command/status summary,
    not raw log lines, so UI surfaces stay bounded and easy to scan.
    """
    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        safe_limit = 50
    safe_limit = max(1, min(safe_limit, 200))
    entries: deque[dict] = deque(maxlen=safe_limit)
    skipped_noise = 0
    tail_metadata = {
        "log_size_bytes": 0,
        "read_window_bytes": 0,
        "tail_limited": False,
    }

    try:
        with _audit_lock:
            if not AUDIT_LOG_PATH.exists():
                return {
                    "ok": True,
                    "source": "audit.log",
                    "limit": safe_limit,
                    "count": 0,
                    "entries": [],
                    "hide_noise": bool(hide_noise),
                    "skipped_noise": 0,
                    **tail_metadata,
                }

            lines, tail_metadata = _read_audit_log_tail_lines()

        for line in lines:
            entry = _parse_audit_entry(line)
            if not entry:
                continue
            if hide_noise and _is_low_signal_audit_entry(entry):
                skipped_noise += 1
                continue
            entries.append(entry)

        recent = list(entries)
        recent.reverse()
        return {
            "ok": True,
            "source": "audit.log",
            "limit": safe_limit,
            "count": len(recent),
            "entries": recent,
            "hide_noise": bool(hide_noise),
            "skipped_noise": skipped_noise,
            **tail_metadata,
        }
    except Exception as e:
        logger.warning(f"Audit-Log konnte nicht gelesen werden: {e}")
        return {
            "ok": False,
            "source": "audit.log",
            "limit": safe_limit,
            "count": 0,
            "entries": [],
            "hide_noise": bool(hide_noise),
            "skipped_noise": skipped_noise,
            **tail_metadata,
            "error": "Audit log unavailable",
            "error_type": type(e).__name__,
        }


def get_rate_limit_info(endpoint_type: str = "default") -> dict:
    """Get current rate limit status for an endpoint type."""
    bucket = _RATE_LIMITS.get(endpoint_type, _RATE_LIMITS["default"])
    now = time.time()
    cutoff = now - 60
    with _rate_limit_lock:
        # Copy deque under lock to avoid mutation during iteration
        active = sum(1 for ts in bucket["timestamps"] if ts > cutoff)
    remaining = max(0, bucket["max"] - active)
    return {
        "limit": bucket["max"],
        "remaining": remaining,
        "reset_in_seconds": 60,
    }


def get_all_rate_limits() -> dict:
    """Get current rate limit status for all endpoint buckets.

    Returns a dict keyed by endpoint type, each containing
    limit, used, remaining, and reset_in_seconds.
    """
    now = time.time()
    cutoff = now - 60
    result = {}
    with _rate_limit_lock:
        for endpoint_type, bucket in _RATE_LIMITS.items():
            active = sum(1 for ts in bucket["timestamps"] if ts > cutoff)
            remaining = max(0, bucket["max"] - active)
            result[endpoint_type] = {
                "limit": bucket["max"],
                "used": active,
                "remaining": remaining,
                "reset_in_seconds": 60,
            }
    return result
