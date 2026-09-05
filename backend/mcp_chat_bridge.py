"""Lexa AI — Generic MCP -> Chat bridge.

Exposes the tools of ANY connected MCP server (git, filesystem, serena, github, ...)
to the chat model and routes the model's ``mcp_<server>_<tool>`` calls back to the
MCP registry. This generalizes what was previously hand-wired only for personal_os.

SECURITY (full, confirmation-gated by design):
- MCP tools touch the real machine (file writes, git, shell via Serena). Therefore
  EVERY mcp_* action is treated as confirmation-required: it never runs as an
  auto-executed read-only tool in the stream loop (it is NOT in _STREAM_AUTO_ALLOW),
  it surfaces on the visible confirmation card, and every execution is audit-logged.
- Tool-name resolution uses an exact index built from the *connected* servers'
  discovered tools (no fragile underscore parsing): unknown/disconnected names are
  rejected.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from backend.config import MCP_ENABLED
from backend.mcp_registry import mcp_registry, MCPError
from backend.security import audit_log, audit_safe_token

try:
    from backend.agent_protocol import redacted_summary as _redacted_summary
except Exception:  # pragma: no cover - fallback if helper unavailable
    def _redacted_summary(value: object, *, max_chars: int = 220) -> str:
        return str(value or "")[:max_chars]

logger = logging.getLogger("lexa.mcp_bridge")

# Lokale Pfade aus Fehlertexten entfernen (Laufwerk/UNC/WSL) — analog router_chat/security.
_LOCAL_PATH_RE = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>|]+|\\\\[^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc|mnt)/[^\s\"'<>|]+)"
)


def _redact(value: object, *, max_chars: int = 220) -> str:
    """Safe error text: summary + local-path redaction (no path/secret leak to chat)."""
    text = _redacted_summary(str(value or ""), max_chars=max_chars)
    return _LOCAL_PATH_RE.sub("[local-path-redacted]", text)


# Coding-MCP-Server, die bei Coding-Kontext lazy verbunden werden (sofern konfiguriert).
CODING_MCP_SERVERS = ("git", "filesystem", "serena")

_MCP_TOOL_PREFIX = "mcp_"


def is_mcp_action(name: str) -> bool:
    """True if the action name targets an MCP-bridged tool (mcp_<server>_<tool>)."""
    return isinstance(name, str) and name.startswith(_MCP_TOOL_PREFIX)


def mcp_action_requires_confirmation(_name: str) -> bool:
    """All MCP tools are confirmation-gated (machine access). Safe-by-default."""
    return True


def _tool_index() -> dict[str, tuple[str, str]]:
    """Map generated tool name -> (server, tool) for all CONNECTED servers.

    Mirrors mcp_registry.get_all_mcp_tools() naming (``mcp_{server}_{tool}``) so a
    name the model emits resolves back to exactly one (server, tool) pair without
    parsing ambiguous underscores.
    """
    index: dict[str, tuple[str, str]] = {}
    try:
        servers = mcp_registry.list_servers()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("MCP list_servers failed: %s", e)
        return index
    for entry in servers:
        if entry.get("status") != "connected":
            continue
        server = entry.get("name") or ""
        if not server:
            continue
        for tool in mcp_registry.get_server_tools(server):
            tool_name = tool.get("name") or ""
            if tool_name:
                index[f"{_MCP_TOOL_PREFIX}{server}_{tool_name}"] = (server, tool_name)
    return index


def resolve_mcp_action(name: str) -> tuple[str, str] | None:
    """Resolve a generated tool name to (server, tool), or None if not connected."""
    return _tool_index().get(name)


def mcp_chat_tools() -> list[dict]:
    """OpenAI-format tool defs for all connected MCP servers (for the chat tool list)."""
    if not MCP_ENABLED:
        return []
    try:
        return mcp_registry.get_all_mcp_tools()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("MCP get_all_mcp_tools failed: %s", e)
        return []


# Coding-Kontext: nur dann werden die (schwergewichtigen, maschinen-nahen) Coding-MCP-
# Server verbunden und ihre Tools dem Modell angeboten — sonst kein Tool-Bloat / kein
# unnötiger Subprozess-Start bei normalen Fragen.
_CODING_HINT_RE = re.compile(
    r"\b(?:code|coden|codest|coding|programmier|refactor|refaktor|debug|stacktrace|"
    r"git|commit|branch|merge|pull\s*request|\bpr\b|repo|repository|quellcode|sourcecode|"
    r"funktion|function|methode|method|klasse|\bclass\b|symbol|variable|import|"
    r"implementier|bugfix|unit\s*test|linter?|\.py\b|\.js\b|\.ts\b|\.json\b)",
    re.IGNORECASE,
)


def is_coding_context(message: str) -> bool:
    """Heuristic: does this message warrant connecting + offering the coding MCP tools?"""
    return bool(message) and bool(_CODING_HINT_RE.search(message))


def coding_mcp_tools(message: str) -> list[dict]:
    """MCP tool defs to add to the chat tool list — only in a coding context."""
    if not is_coding_context(message):
        return []
    return mcp_chat_tools()


async def ensure_coding_servers_connected(servers: tuple[str, ...] = CODING_MCP_SERVERS) -> dict[str, str]:
    """Lazily connect the configured coding MCP servers. Tolerates failures
    (e.g. missing uv/node) — returns {server: status}. Never raises."""
    status: dict[str, str] = {}
    if not MCP_ENABLED:
        return status
    try:
        configs = mcp_registry.get_server_configs()
    except Exception:
        configs = {}
    for name in servers:
        cfg = configs.get(name)
        if cfg is None:
            status[name] = "not_configured"
            continue
        if cfg.get("enabled", True) is False:
            status[name] = "disabled"
            continue
        if mcp_registry.get_server_status(name) == "connected":
            status[name] = "connected"
            continue
        try:
            await mcp_registry.connect(name)
            status[name] = "connected"
        except Exception as e:
            status[name] = "error"
            logger.info("MCP coding server '%s' connect failed: %s", name, e)
    return status


def _stringify_mcp_result(result: Any) -> Any:
    """Normalize an MCP tool result into something chat-friendly + bounded."""
    if isinstance(result, (dict, list)):
        return result
    text = str(result if result is not None else "")
    return text[:6000]


async def execute_mcp_action(name: str, params: dict | None = None) -> dict:
    """Execute an MCP-bridged tool call. Returns the Lexa result shape
    {success, data|error}. Errors are redacted (no local paths leak)."""
    if not MCP_ENABLED:
        return {"success": False, "error": "MCP ist deaktiviert."}
    resolved = resolve_mcp_action(name)
    if not resolved:
        audit_log(name, "mcp_unresolved", "")
        return {"success": False, "error": f"MCP-Tool '{name}' ist nicht verbunden oder unbekannt."}
    server, tool = resolved
    try:
        result = await mcp_registry.call_tool(server, tool, params or {})
        audit_log(name, "mcp_executed", f"server={audit_safe_token(server)} tool={audit_safe_token(tool)}")
        return {"success": True, "data": _stringify_mcp_result(result)}
    except MCPError as e:
        audit_log(name, "mcp_failed", "")
        return {"success": False, "error": _redact(str(e), max_chars=220) or "MCP-Aufruf fehlgeschlagen."}
    except Exception as e:
        logger.warning("MCP call %s failed: %s", name, e)
        audit_log(name, "mcp_failed", "")
        return {"success": False, "error": _redact(str(e), max_chars=220) or "MCP-Aufruf fehlgeschlagen."}
