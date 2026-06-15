"""Lexa AI - Central Configuration
All magic numbers and configurable values in one place.
"""
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_packaged_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "lexa-ai"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lexa-ai"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lexa-ai"


def _resolve_data_dir_with_source() -> tuple[Path, str]:
    raw = os.environ.get("LEXA_DATA_DIR")
    if raw:
        return Path(raw).expanduser(), "env"
    if getattr(sys, "frozen", False):
        return _default_packaged_data_dir(), "packaged_default"
    return _default_packaged_data_dir(), "user_data_default"


def resolve_data_dir() -> Path:
    data_dir, _source = _resolve_data_dir_with_source()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return data_dir


LEXA_DATA_DIR, LEXA_DATA_DIR_SOURCE = _resolve_data_dir_with_source()
try:
    LEXA_DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip() or default


# ── Server ────────────────────────────────────────
VERSION = "1.0.0"
BACKEND_PORT = _env_int("LEXA_PORT", 8000, minimum=1, maximum=65535)
BACKEND_HOST = _env_str("LEXA_HOST", "127.0.0.1")

# ── Chat & History ────────────────────────────────
MAX_HISTORY = _env_int("LEXA_MAX_HISTORY", 80, minimum=1, maximum=1000)
MAX_CHAT_MESSAGE_LENGTH = _env_int("LEXA_MAX_CHAT_MESSAGE_LENGTH", 4000, minimum=100, maximum=200000)
MAX_CONVERSATION_MESSAGES = _env_int("LEXA_MAX_CONVERSATION_MESSAGES", 5000, minimum=1, maximum=100000)

# ── File Upload ───────────────────────────────────
MAX_FILE_SIZE_MB = _env_int("LEXA_MAX_FILE_SIZE_MB", 2, minimum=1, maximum=100)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_TEXT_CHARS = _env_int("LEXA_MAX_TEXT_CHARS", 8000, minimum=100, maximum=500000)
MAX_BODY_SIZE = _env_int("LEXA_MAX_BODY_SIZE", 1 * 1024 * 1024, minimum=1024, maximum=50 * 1024 * 1024)

# ── Cache ─────────────────────────────────────────
CACHE_MAX_ENTRIES = _env_int("LEXA_CACHE_MAX_ENTRIES", 50, minimum=1, maximum=10000)
CACHE_HEALTH_TTL = _env_float("LEXA_CACHE_HEALTH_TTL", 5.0, minimum=0.0, maximum=3600.0)
CACHE_MEMORY_STATS_TTL = _env_float("LEXA_CACHE_MEMORY_STATS_TTL", 10.0, minimum=0.0, maximum=3600.0)

# ── Rate Limits (per minute) ─────────────────────
RATE_LIMIT_CHAT = _env_int("LEXA_RATE_LIMIT_CHAT", 30, minimum=1, maximum=10000)
RATE_LIMIT_EXECUTE = _env_int("LEXA_RATE_LIMIT_EXECUTE", 20, minimum=1, maximum=10000)
RATE_LIMIT_VOICE = _env_int("LEXA_RATE_LIMIT_VOICE", 60, minimum=1, maximum=10000)
RATE_LIMIT_VISION = _env_int("LEXA_RATE_LIMIT_VISION", 15, minimum=1, maximum=10000)
RATE_LIMIT_WORKFLOWS = _env_int("LEXA_RATE_LIMIT_WORKFLOWS", 30, minimum=1, maximum=10000)
RATE_LIMIT_STRIPE_READ = _env_int("LEXA_RATE_LIMIT_STRIPE_READ", 10, minimum=1, maximum=10000)
RATE_LIMIT_AUDIT_READ = _env_int("LEXA_RATE_LIMIT_AUDIT_READ", 120, minimum=1, maximum=10000)
RATE_LIMIT_DEFAULT = _env_int("LEXA_RATE_LIMIT_DEFAULT", 30, minimum=1, maximum=10000)

# ── Input Limits ──────────────────────────────────
MAX_NOTE_TITLE = _env_int("LEXA_MAX_NOTE_TITLE", 500, minimum=1, maximum=5000)
MAX_NOTE_CONTENT = _env_int("LEXA_MAX_NOTE_CONTENT", 50000, minimum=100, maximum=1000000)
MAX_NOTE_CATEGORY = _env_int("LEXA_MAX_NOTE_CATEGORY", 100, minimum=1, maximum=1000)
MAX_MEMORY_CONTENT = _env_int("LEXA_MAX_MEMORY_CONTENT", 2000, minimum=100, maximum=200000)
MAX_MEMORY_CATEGORY = _env_int("LEXA_MAX_MEMORY_CATEGORY", 50, minimum=1, maximum=500)
MAX_CONVERSATION_TITLE = _env_int("LEXA_MAX_CONVERSATION_TITLE", 200, minimum=1, maximum=2000)
MAX_SNIPPET_NAME = _env_int("LEXA_MAX_SNIPPET_NAME", 200, minimum=1, maximum=2000)
MAX_SNIPPET_TEXT = _env_int("LEXA_MAX_SNIPPET_TEXT", 20000, minimum=100, maximum=1000000)
MAX_CLIPBOARD_TEXT = _env_int("LEXA_MAX_CLIPBOARD_TEXT", 50000, minimum=100, maximum=1000000)
MAX_SEARCH_QUERY = _env_int("LEXA_MAX_SEARCH_QUERY", 200, minimum=1, maximum=5000)
MAX_FTS_QUERY = _env_int("LEXA_MAX_FTS_QUERY", 500, minimum=1, maximum=5000)
MAX_PROFILE_KEY = _env_int("LEXA_MAX_PROFILE_KEY", 100, minimum=1, maximum=1000)
MAX_PROFILE_VALUE = _env_int("LEXA_MAX_PROFILE_VALUE", 1000, minimum=1, maximum=100000)

# ── Cleanup ───────────────────────────────────────
DEFAULT_CLEANUP_DAYS = _env_int("LEXA_DEFAULT_CLEANUP_DAYS", 90, minimum=1, maximum=3650)
DEFAULT_CLEANUP_MAX_IMPORTANCE = _env_int("LEXA_DEFAULT_CLEANUP_MAX_IMPORTANCE", 3, minimum=1, maximum=5)
MIN_CLEANUP_DAYS = _env_int("LEXA_MIN_CLEANUP_DAYS", 7, minimum=1, maximum=3650)
MAX_CLEANUP_DAYS = _env_int("LEXA_MAX_CLEANUP_DAYS", 365, minimum=1, maximum=3650)

# ── Tool Use (Phase 40) ─────────────────────────
TOOL_USE_ENABLED = _env_bool("LEXA_TOOL_USE_ENABLED", True)   # Native function calling for Groq/OpenAI/Gemini
TOOL_USE_MAX_TOOLS = _env_int("LEXA_TOOL_USE_MAX_TOOLS", 40, minimum=1, maximum=128)   # Max tools per API call

# ── Agent (Phase 46) ───────────────────────────
AGENT_MAX_STEPS = _env_int("LEXA_AGENT_MAX_STEPS", 10, minimum=1, maximum=50)      # Max tool calls per agent turn
AGENT_STEP_TIMEOUT = _env_int("LEXA_AGENT_STEP_TIMEOUT", 30, minimum=1, maximum=600)   # Seconds per step execution
AGENT_CONFIRM_TIMEOUT = _env_int("LEXA_AGENT_CONFIRM_TIMEOUT", 300, minimum=1, maximum=3600)
# Multi-step server-side read-tool loop in /chat/stream (each hop is a full LLM roundtrip;
# kept low for free-API rate limits + latency). Lower than AGENT_MAX_STEPS by design.
AGENT_STREAM_MAX_HOPS = _env_int("LEXA_AGENT_STREAM_MAX_HOPS", 4, minimum=1, maximum=8)

# ── Orchestrator — Multi-Agenten (Phase 48) ───
# Claude-ultracode-artiges Orchestrator-Worker-System: Planner -> parallele read-only
# Sub-Agenten -> adversarische Verifikation -> Synthese. Provider-agnostisch (Gemini).
ORCHESTRATOR_ENABLED = _env_bool("LEXA_ORCHESTRATOR_ENABLED", True)
# Harte Caps gegen Kosten/Rate-Limit-Explosion (Multi-Agent ~15x Tokens eines Chats).
ORCHESTRATOR_MAX_SUBAGENTS = _env_int("LEXA_ORCHESTRATOR_MAX_SUBAGENTS", 4, minimum=1, maximum=12)
ORCHESTRATOR_MAX_CONCURRENCY = _env_int("LEXA_ORCHESTRATOR_MAX_CONCURRENCY", 3, minimum=1, maximum=8)
ORCHESTRATOR_SUBAGENT_MAX_STEPS = _env_int("LEXA_ORCHESTRATOR_SUBAGENT_MAX_STEPS", 6, minimum=1, maximum=20)
ORCHESTRATOR_STEP_TIMEOUT = _env_int("LEXA_ORCHESTRATOR_STEP_TIMEOUT", 45, minimum=5, maximum=600)
ORCHESTRATOR_RUN_TIMEOUT = _env_int("LEXA_ORCHESTRATOR_RUN_TIMEOUT", 600, minimum=30, maximum=3600)
# Browser-Agent (browser-use, optional+schwer): startet echten Chromium -> bewusst NICHT im
# autonomen Parallel-Orchestrator, sondern explizit opt-in. Default AUS (Ressourcen/Sicherheit).
ORCHESTRATOR_BROWSER_ENABLED = _env_bool("LEXA_ORCHESTRATOR_BROWSER_ENABLED", False)

# ── MCP — Model Context Protocol (Phase 47) ───
MCP_ENABLED = _env_bool("LEXA_MCP_ENABLED", True)            # Enable MCP server integration
MCP_CONNECT_TIMEOUT = _env_int("LEXA_MCP_CONNECT_TIMEOUT", 10, minimum=1, maximum=120)
MCP_CALL_TIMEOUT = _env_int("LEXA_MCP_CALL_TIMEOUT", 30, minimum=1, maximum=600)

# ── Embeddings (Phase 42) ────────────────────────
EMBEDDING_ENABLED = _env_bool("LEXA_EMBEDDING_ENABLED", True)
EMBEDDING_PROVIDER = _env_str("LEXA_EMBEDDING_PROVIDER", "auto")   # "auto", "openai", "local"
EMBEDDING_REINDEX_BATCH = _env_int("LEXA_EMBEDDING_REINDEX_BATCH", 50, minimum=1, maximum=10000)

# ── Slow Request Logging ─────────────────────────
SLOW_REQUEST_THRESHOLD = _env_float("LEXA_SLOW_REQUEST_THRESHOLD", 5.0, minimum=0.1, maximum=3600.0)

# ── Allowed File Extensions ──────────────────────
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".ts", ".jsx", ".tsx", ".css", ".html",
    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".log", ".sh", ".sql", ".env", ".gitignore",
    ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php", ".swift",
}

BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js", ".jar", ".msi", ".scr", ".pif"
}

# ── Weather (Upgrade 2) ───────────────────────
WEATHER_CACHE_TTL = _env_int("LEXA_WEATHER_CACHE_TTL", 600, minimum=0, maximum=86400)

# ── Reminders (Upgrade 3) ─────────────────────
REMINDER_CHECK_INTERVAL = _env_int("LEXA_REMINDER_CHECK_INTERVAL", 30, minimum=1, maximum=3600)

# ── Email (Upgrade 4) ─────────────────────────
MAX_ATTACHMENT_SIZE = _env_int("LEXA_MAX_ATTACHMENT_SIZE_MB", 25, minimum=1, maximum=500) * 1024 * 1024

# ── Vision/OCR (Upgrade 6) ────────────────────
VISION_MAX_IMAGE_WIDTH = _env_int("LEXA_VISION_MAX_IMAGE_WIDTH", 1280, minimum=64, maximum=8192)
VISION_JPEG_QUALITY = _env_int("LEXA_VISION_JPEG_QUALITY", 85, minimum=1, maximum=100)
