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

    endpoint_type: 'chat', 'execute', 'voice', or 'default'
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
_audit_lock = threading.Lock()


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
