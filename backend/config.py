"""Lexa AI — Central Configuration
All magic numbers and configurable values in one place.
"""
import os

# ── Server ────────────────────────────────────────
VERSION = "1.0.0"
BACKEND_PORT = int(os.environ.get("LEXA_PORT", "8000"))
BACKEND_HOST = "127.0.0.1"

# ── Chat & History ────────────────────────────────
MAX_HISTORY = 80
MAX_CHAT_MESSAGE_LENGTH = 4000
MAX_CONVERSATION_MESSAGES = 5000

# ── File Upload ───────────────────────────────────
MAX_FILE_SIZE = 2 * 1024 * 1024       # 2 MB
MAX_FILE_SIZE_MB = 2
MAX_TEXT_CHARS = 8000
MAX_BODY_SIZE = 1 * 1024 * 1024       # 1 MB for non-file endpoints

# ── Cache ─────────────────────────────────────────
CACHE_MAX_ENTRIES = 50
CACHE_HEALTH_TTL = 5.0
CACHE_MEMORY_STATS_TTL = 10.0

# ── Rate Limits (per minute) ─────────────────────
RATE_LIMIT_CHAT = 30
RATE_LIMIT_EXECUTE = 20
RATE_LIMIT_VOICE = 60

# ── Input Limits ──────────────────────────────────
MAX_NOTE_TITLE = 500
MAX_NOTE_CONTENT = 50000
MAX_NOTE_CATEGORY = 100
MAX_MEMORY_CONTENT = 2000
MAX_MEMORY_CATEGORY = 50
MAX_CONVERSATION_TITLE = 200
MAX_SNIPPET_NAME = 200
MAX_SNIPPET_TEXT = 20000
MAX_CLIPBOARD_TEXT = 50000
MAX_SEARCH_QUERY = 200
MAX_FTS_QUERY = 500
MAX_PROFILE_KEY = 100
MAX_PROFILE_VALUE = 1000

# ── Cleanup ───────────────────────────────────────
DEFAULT_CLEANUP_DAYS = 90
DEFAULT_CLEANUP_MAX_IMPORTANCE = 3
MIN_CLEANUP_DAYS = 7
MAX_CLEANUP_DAYS = 365

# ── Tool Use (Phase 40) ─────────────────────────
TOOL_USE_ENABLED = True   # Native function calling for Groq/OpenAI/Gemini
TOOL_USE_MAX_TOOLS = 40   # Max tools per API call (provider limits)

# ── Agent (Phase 46) ───────────────────────────
AGENT_MAX_STEPS = 10      # Max tool calls per agent turn
AGENT_STEP_TIMEOUT = 30   # Seconds per step execution
AGENT_CONFIRM_TIMEOUT = 300  # Seconds to wait for user confirmation

# ── MCP — Model Context Protocol (Phase 47) ───
MCP_ENABLED = True            # Enable MCP server integration
MCP_CONNECT_TIMEOUT = 10      # Seconds to wait for server handshake
MCP_CALL_TIMEOUT = 30         # Seconds to wait for tool call result

# ── Embeddings (Phase 42) ────────────────────────
EMBEDDING_ENABLED = True      # Enable semantic memory via embeddings
EMBEDDING_PROVIDER = "auto"   # "auto" (OpenAI → local), "openai", "local"
EMBEDDING_REINDEX_BATCH = 50  # Batch size for reindex operations

# ── Slow Request Logging ─────────────────────────
SLOW_REQUEST_THRESHOLD = 5.0  # seconds

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
WEATHER_CACHE_TTL = 600      # 10 minutes

# ── Reminders (Upgrade 3) ─────────────────────
REMINDER_CHECK_INTERVAL = 30  # seconds

# ── Email (Upgrade 4) ─────────────────────────
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25 MB

# ── Vision/OCR (Upgrade 6) ────────────────────
VISION_MAX_IMAGE_WIDTH = 1280  # Downscale before sending to API
VISION_JPEG_QUALITY = 85       # JPEG quality for API uploads
