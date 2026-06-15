"""Lexa AI — MCP Router (Phase 47: Model Context Protocol)
API endpoints for managing MCP server connections and calling external tools.

Endpoints:
- GET  /mcp/servers          — List all configured servers with status
- POST /mcp/servers/{name}/connect    — Connect to a server
- POST /mcp/servers/{name}/disconnect — Disconnect from a server
- GET  /mcp/servers/{name}/tools      — List tools from a specific server
- POST /mcp/servers/{name}/call       — Call a tool on a server
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent_protocol import redacted_summary
from backend.config import MCP_ENABLED
from backend.security import audit_error_details, check_rate_limit, audit_log
from backend.mcp_registry import mcp_registry, MCPError

logger = logging.getLogger("lexa.router_mcp")

router = APIRouter(prefix="/mcp", tags=["mcp"])

# Allowed server name pattern (alphanumeric + hyphens + underscores)
_VALID_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
_LOCAL_PATH_RE = re.compile(
    r"(?:(?<![A-Za-z])[A-Za-z]:[\\/][^\s\"'<>|]+|\\\\[^\s\"'<>|]+|(?<!\S)/(?:Users|home|tmp|var|etc|mnt)/[^\s\"'<>|]+)"
)


def _client_safe_mcp_error(value: object, *, max_chars: int = 220) -> str:
    text = redacted_summary(str(value or ""), max_chars=max_chars)
    text = _LOCAL_PATH_RE.sub("[local-path-redacted]", text)
    return text or "MCP request failed"


def _validate_server_name(name: str) -> str:
    """Validate and return the server name. Raises HTTPException on invalid input."""
    if not name or len(name) > 64:
        raise HTTPException(status_code=400, detail="Invalid server name")
    if not all(c in _VALID_NAME_CHARS for c in name):
        raise HTTPException(status_code=400, detail="Server name contains invalid characters")
    return name


# ══════════════════════════════════════════════════
#  MODELS
# ══════════════════════════════════════════════════

class ToolCallRequest(BaseModel):
    tool: str = Field(..., min_length=1, max_length=200)
    arguments: dict = Field(default_factory=dict)


# ══════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════

@router.get("/servers")
async def list_servers():
    """List all configured MCP servers with their connection status."""
    if not MCP_ENABLED:
        return {"enabled": False, "servers": []}

    servers = await asyncio.to_thread(mcp_registry.list_servers)
    return {"enabled": True, "servers": servers}


@router.post("/servers/{name}/connect")
async def connect_server(name: str):
    """Connect to a configured MCP server and discover its tools."""
    if not MCP_ENABLED:
        raise HTTPException(status_code=400, detail="MCP integration is disabled")

    name = _validate_server_name(name)

    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    audit_log("mcp", "connect", f"server={name}")

    try:
        server_info = await mcp_registry.connect(name)
        tools = mcp_registry.get_server_tools(name)
        return {
            "status": "connected",
            "server": name,
            "server_info": server_info,
            "tools_count": len(tools),
        }
    except MCPError as e:
        logger.warning(f"MCP connect failed for '{name}': {e}")
        audit_log("mcp", "connect_error", f"server={name} {audit_error_details(e)}")
        raise HTTPException(status_code=502, detail=_client_safe_mcp_error(e))
    except Exception as e:
        logger.error(f"MCP connect unexpected error for '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="MCP connection failed")


@router.post("/servers/{name}/disconnect")
async def disconnect_server(name: str):
    """Disconnect from an MCP server."""
    if not MCP_ENABLED:
        raise HTTPException(status_code=400, detail="MCP integration is disabled")

    name = _validate_server_name(name)
    audit_log("mcp", "disconnect", f"server={name}")

    try:
        await mcp_registry.disconnect(name)
        return {"status": "disconnected", "server": name}
    except Exception as e:
        logger.error(f"MCP disconnect error for '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Disconnect failed")


@router.get("/servers/{name}/tools")
async def list_server_tools(name: str):
    """List all tools available on a connected MCP server."""
    if not MCP_ENABLED:
        raise HTTPException(status_code=400, detail="MCP integration is disabled")

    name = _validate_server_name(name)

    client = mcp_registry.get_client(name)
    if not client:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{name}' is not connected",
        )

    tools = client.tools
    return {
        "server": name,
        "tools": tools,
        "count": len(tools),
    }


@router.post("/servers/{name}/call")
async def call_server_tool(name: str, req: ToolCallRequest):
    """Call a tool on a connected MCP server.

    Request body:
        tool: Name of the tool to call
        arguments: Dict of tool arguments
    """
    if not MCP_ENABLED:
        raise HTTPException(status_code=400, detail="MCP integration is disabled")

    name = _validate_server_name(name)

    if not check_rate_limit("execute"):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen.")

    # Validate tool name characters
    if not all(c.isalnum() or c in "-_/" for c in req.tool):
        raise HTTPException(status_code=400, detail="Invalid tool name")

    audit_log("mcp", "call_tool", f"server={name} tool={req.tool}")

    try:
        # The MCP client enforces MCP_CALL_TIMEOUT internally (see
        # mcp_client._send_request) and cleans up its pending-request table on
        # timeout. We deliberately rely on that single timeout layer instead of
        # wrapping the call in a second asyncio.wait_for, which would race the
        # inner timer and could leave a stale entry in the client's _pending map.
        result = await mcp_registry.call_tool(name, req.tool, req.arguments)

        # Flatten content items for simpler response
        output_parts = []
        for item in (result if isinstance(result, list) else [result]):
            if isinstance(item, dict):
                if item.get("type") == "text":
                    output_parts.append(item.get("text", ""))
                else:
                    output_parts.append(item)
            else:
                output_parts.append(str(item))

        audit_log("mcp", "call_tool_ok", f"server={name} tool={req.tool}")
        return {
            "status": "ok",
            "server": name,
            "tool": req.tool,
            "result": output_parts,
        }

    except MCPError as e:
        logger.warning(f"MCP tool call failed: {name}/{req.tool}: {e}")
        audit_log("mcp", "call_tool_error", f"server={name} tool={req.tool} {audit_error_details(e)}")
        raise HTTPException(status_code=502, detail=_client_safe_mcp_error(e))
    except Exception as e:
        logger.error(f"MCP tool call error: {name}/{req.tool}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Tool call failed")
