"""Lexa AI — Security Module
Input-Validierung, Rate Limiting, Command Whitelist, Audit Log, Path/URL Protection
"""

import os
import json
import sys
import time
import re
import logging
import threading
import unicodedata
import ipaddress
from pathlib import Path
from collections import deque
from datetime import datetime
from urllib.parse import urlparse

from backend.i18n import t

logger = logging.getLogger("lexa.security")

PROJECT_ROOT = Path(__file__).parent.parent
WHITELIST_PATH = PROJECT_ROOT / "command_whitelist.json"

_DATA_DIR = os.environ.get("LEXA_DATA_DIR", str(PROJECT_ROOT))
AUDIT_LOG_PATH = Path(_DATA_DIR) / "audit.log"

# Rate Limiting — per endpoint type, thread-safe with lock
_rate_limit_lock = threading.Lock()
_RATE_LIMITS: dict[str, dict] = {
    "chat":         {"max": 30,  "timestamps": deque()},
    "execute":      {"max": 20,  "timestamps": deque()},  # PC-Befehle strenger
    "voice":        {"max": 60,  "timestamps": deque()},  # Voice großzügiger
    "vision":       {"max": 15,  "timestamps": deque()},  # Vision-API (Screenshot + Analyse)
    "workflows":    {"max": 30,  "timestamps": deque()},  # Workflow-Operationen
    "stripe_read":  {"max": 10,  "timestamps": deque()},  # Stripe read endpoints (no auth)
    "audit_read":   {"max": 120, "timestamps": deque()},  # Read-only UI trust/history surfaces
    "default":      {"max": 30,  "timestamps": deque()},
}
# Legacy alias (backward-compat)
_command_timestamps = _RATE_LIMITS["default"]["timestamps"]
MAX_COMMANDS_PER_MINUTE = 30

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


_whitelist = load_whitelist()


def reload_whitelist():
    """Reload whitelist from file (hot-reload)."""
    global _whitelist
    _whitelist = load_whitelist()


def is_command_allowed(command: str) -> str:
    """Check if a command is allowed.
    Returns: 'allowed', 'confirmation_required', 'blocked', or 'unknown'
    """
    command = command.strip().lower()

    always_allowed = [c.strip().lower() for c in _whitelist["commands"]["always_allowed"]["list"]]
    confirmation_required = [c.strip().lower() for c in _whitelist["commands"]["confirmation_required"]["list"]]
    always_blocked = [c.strip().lower() for c in _whitelist["commands"]["always_blocked"]["list"]]

    if command in always_blocked:
        return "blocked"
    if command in always_allowed:
        return "allowed"
    if command in confirmation_required:
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


def sanitize_input(user_input: str) -> str:
    """Sanitize user input to prevent prompt injection.

    Applies:
    1. Unicode NFKC normalization (catches homoglyph attacks)
    2. Zero-width character stripping (catches invisible char smuggling)
    3. Injection pattern filtering (36 compiled regex patterns)
    4. Length truncation (max 2000 chars)
    """
    # Normalize unicode to catch homoglyph attacks (e.g. ｉｇｎｏｒｅ → ignore)
    sanitized = unicodedata.normalize("NFKC", user_input)

    # Strip zero-width characters that could be used to evade pattern matching
    sanitized = _ZERO_WIDTH_CHARS.sub("", sanitized)

    # Apply pre-compiled injection patterns
    for compiled in _COMPILED_PATTERNS:
        sanitized = compiled.sub("[FILTERED]", sanitized)

    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]
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
    """Validate and sanitize KI output before executing as command."""
    for cmd in DANGEROUS_COMMANDS:
        if cmd.lower() in output.lower():
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


def validate_path(path_str: str) -> str:
    """Validate a file/directory path is safe to access."""
    if not path_str:
        return path_str

    resolved = str(Path(path_str).resolve())

    for blocked in BLOCKED_PATHS:
        if resolved.lower().startswith(blocked.lower()):
            raise ValueError(t("security.blockedDir", dir=blocked))

    if ".." in path_str:
        raise ValueError("Pfad-Traversierung nicht erlaubt")

    return resolved


# ══════════════════════════════════════════════════
#  URL VALIDATION
# ══════════════════════════════════════════════════

# Cloud metadata endpoints — SSRF protection
_BLOCKED_HOSTS: frozenset[str] = frozenset({
    # AWS metadata
    "169.254.169.254",
    # Azure metadata
    "169.254.169.253",
    # GCP metadata
    "metadata.google.internal",
    "metadata.google",
    # Alibaba Cloud metadata
    "100.100.100.200",
    # DigitalOcean metadata
    "169.254.169.254",
    # Oracle Cloud metadata
    "169.254.169.254",
    # Generic link-local
    "169.254.0.1",
})

def _is_dangerous_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
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


def validate_url(url: str) -> str:
    """Validate a URL is safe to access (SSRF protection).

    Uses Python's ipaddress module to detect ALL private/loopback/link-local/reserved
    IPs regardless of notation (decimal, hex, octal, IPv6-mapped IPv4, etc.).
    """
    parsed = urlparse(url)

    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsicheres URL-Schema: {parsed.scheme}")

    hostname = parsed.hostname
    if hostname:
        hostname_lower = hostname.lower().strip("[]")

        # Check exact blocked hosts (cloud metadata endpoints, etc.)
        if hostname_lower in _BLOCKED_HOSTS:
            raise ValueError(t("security.blockedInternal", host=hostname))

        # Try to parse as IP address (handles all notations: dotted, hex, decimal, IPv6)
        try:
            addr = ipaddress.ip_address(hostname_lower)
            if _is_dangerous_ip(addr):
                raise ValueError(t("security.blockedPrivate", host=hostname))
        except ValueError as e:
            # Not a valid IP literal — it's a hostname, which is fine
            # (re-raise only our own SSRF errors, not ipaddress parse errors)
            if "blockiert" in str(e):
                raise

    if not parsed.scheme:
        url = "https://" + url

    return url


# ══════════════════════════════════════════════════
#  PARAM VALIDATION
# ══════════════════════════════════════════════════

PATH_PARAM_KEYS: frozenset[str] = frozenset({
    "path", "search_path", "folder", "input_path", "output_path",
    "video_path", "pdf_path", "downloads_path", "save_path",
})


def validate_params(command: str, params: dict, _depth: int = 0) -> dict:
    """Validate command parameters for safety. Recurses into nested dicts/lists (max depth 3)."""
    if _depth > 3:
        raise ValueError("Parameter-Verschachtelung zu tief (max 3 Ebenen).")
    clean = {}
    for key, value in params.items():
        if isinstance(value, str):
            if len(value) > 5000:
                value = value[:5000]
            if key in PATH_PARAM_KEYS:
                value = validate_path(value)
            if key == "url":
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
            if key in PATH_PARAM_KEYS:
                item = validate_path(item)
            if key == "url":
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


def audit_log(command: str, status: str, details: str = "") -> None:
    """Log every command execution to audit log (with rotation at 10 MB).

    Falls back to stderr if file writing fails.
    """
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] CMD={command} STATUS={status} {details}\n"
    try:
        with _audit_lock:
            _rotate_audit_log()
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(entry)
    except Exception as e:
        # Don't swallow errors — log to stderr as fallback
        print(f"[AUDIT FALLBACK] {entry.strip()} (write failed: {e})", file=sys.stderr)
    logger.info(entry.strip())


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

    return _AUDIT_DETAIL_PAIR_RE.sub(replace, text), redacted_fields


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
    details, redacted_fields = _redact_audit_details(match.group("details") or "")
    if not redacted_fields and _should_redact_keyless_audit_details(command, status, details):
        details = "[redacted]"
        redacted_fields = ["details"]
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
