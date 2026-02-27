"""Lexa AI — Security Module
Input-Validierung, Rate Limiting, Command Whitelist, Audit Log, Path/URL Protection
"""

import json
import time
import re
import logging
from pathlib import Path
from collections import deque
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger("lexa.security")

PROJECT_ROOT = Path(__file__).parent.parent
WHITELIST_PATH = PROJECT_ROOT / "command_whitelist.json"
AUDIT_LOG_PATH = PROJECT_ROOT / "audit.log"

# Rate Limiting
MAX_COMMANDS_PER_MINUTE = 30
_command_timestamps: deque = deque()


def load_whitelist() -> dict:
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_whitelist = load_whitelist()


def reload_whitelist():
    """Reload whitelist from file (hot-reload)."""
    global _whitelist
    _whitelist = load_whitelist()


def is_command_allowed(command: str) -> str:
    """Check if a command is allowed.
    Returns: 'allowed', 'confirmation_required', 'blocked', or 'unknown'
    """
    always_allowed = _whitelist["commands"]["always_allowed"]["list"]
    confirmation_required = _whitelist["commands"]["confirmation_required"]["list"]
    always_blocked = _whitelist["commands"]["always_blocked"]["list"]

    if command in always_blocked:
        return "blocked"
    if command in always_allowed:
        return "allowed"
    if command in confirmation_required:
        return "confirmation_required"
    return "unknown"


def check_rate_limit() -> bool:
    """Returns True if within rate limit, False if exceeded."""
    now = time.time()
    while _command_timestamps and _command_timestamps[0] < now - 60:
        _command_timestamps.popleft()
    if len(_command_timestamps) >= MAX_COMMANDS_PER_MINUTE:
        return False
    _command_timestamps.append(now)
    return True


# ══════════════════════════════════════════════════
#  INPUT SANITIZATION
# ══════════════════════════════════════════════════

INJECTION_PATTERNS = [
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
]


def sanitize_input(user_input: str) -> str:
    """Sanitize user input to prevent prompt injection."""
    sanitized = user_input
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)
    if len(sanitized) > 2000:
        sanitized = sanitized[:2000]
    return sanitized


# ══════════════════════════════════════════════════
#  OUTPUT VALIDATION
# ══════════════════════════════════════════════════

DANGEROUS_COMMANDS = [
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

BLOCKED_PATHS = [
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64",
]


def validate_path(path_str: str) -> str:
    """Validate a file/directory path is safe to access."""
    if not path_str:
        return path_str

    resolved = str(Path(path_str).resolve())

    for blocked in BLOCKED_PATHS:
        if resolved.lower().startswith(blocked.lower()):
            raise ValueError(f"Zugriff auf geschütztes Verzeichnis blockiert: {blocked}")

    if ".." in path_str:
        raise ValueError("Pfad-Traversierung nicht erlaubt")

    return resolved


# ══════════════════════════════════════════════════
#  URL VALIDATION
# ══════════════════════════════════════════════════

def validate_url(url: str) -> str:
    """Validate a URL is safe to access."""
    parsed = urlparse(url)

    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsicheres URL-Schema: {parsed.scheme}")

    blocked_hosts = ["169.254.169.254", "metadata.google.internal"]
    if parsed.hostname and parsed.hostname.lower() in blocked_hosts:
        raise ValueError(f"Zugriff auf interne Adresse blockiert: {parsed.hostname}")

    if not parsed.scheme:
        url = "https://" + url

    return url


# ══════════════════════════════════════════════════
#  PARAM VALIDATION
# ══════════════════════════════════════════════════

PATH_PARAM_KEYS = frozenset({
    "path", "search_path", "folder", "input_path", "output_path",
    "video_path", "pdf_path", "downloads_path", "save_path",
})


def validate_params(command: str, params: dict) -> dict:
    """Validate command parameters for safety."""
    clean = {}
    for key, value in params.items():
        if isinstance(value, str):
            if len(value) > 5000:
                value = value[:5000]
            if key in PATH_PARAM_KEYS:
                value = validate_path(value)
            if key == "url":
                value = validate_url(value)
        clean[key] = value
    return clean


# ══════════════════════════════════════════════════
#  AUDIT LOG
# ══════════════════════════════════════════════════

def audit_log(command: str, status: str, details: str = ""):
    """Log every command execution to audit log."""
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] CMD={command} STATUS={status} {details}\n"
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass
    logger.info(entry.strip())
