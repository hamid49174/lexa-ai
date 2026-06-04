"""Lexa AI — MCP Server Registry (Phase 47: Model Context Protocol)
Manages MCP server configurations, connections, and tool discovery.

Loads server configs from mcp_servers.json, tracks connection status,
and merges discovered MCP tools with the existing tool_registry for LLM calls.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from backend.config import LEXA_DATA_DIR, MCP_ENABLED
from backend.mcp_client import MCPClient, MCPError

logger = logging.getLogger("lexa.mcp_registry")

# Config file location - project root or LEXA_DATA_DIR
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = LEXA_DATA_DIR / "mcp_servers.json"
PROJECT_MCP_CONFIG_PATH = _PROJECT_ROOT / "mcp_servers.json"
_PERSONAL_OS_MCP_INDEX = Path("11_Integrations") / "MCP" / "os-mcp-server" / "dist" / "index.js"


def _mcp_config_candidates() -> list[Path]:
    paths = [MCP_CONFIG_PATH]
    if PROJECT_MCP_CONFIG_PATH != MCP_CONFIG_PATH:
        paths.append(PROJECT_MCP_CONFIG_PATH)
    return paths


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _personal_os_root_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("PERSONAL_OS_ROOT", "PERSONAL_OS_SDK_ROOT"):
        configured = os.environ.get(env_name)
        if configured:
            candidates.append(Path(configured))

    repo_parent = _PROJECT_ROOT.parent
    storage_parent = repo_parent.parent
    candidates.extend([
        _PROJECT_ROOT / "personal_os",
        repo_parent / "OS",
        storage_parent / "OS",
        storage_parent / "Desktop" / "OS",
        Path.home() / "OneDrive - Office" / "Desktop" / "OS",
        Path.home() / "OneDrive" / "Desktop" / "OS",
        Path.home() / "Desktop" / "OS",
    ])
    return _dedupe_paths(candidates)


def _find_personal_os_mcp_index() -> tuple[Path, Path] | None:
    for root in _personal_os_root_candidates():
        index = root / _PERSONAL_OS_MCP_INDEX
        if index.exists():
            return root.resolve(), index.resolve()
    return None


def _looks_like_personal_os_mcp_index(value: object) -> bool:
    normalized = str(value or "").replace("\\", "/").lower()
    return normalized.endswith("11_integrations/mcp/os-mcp-server/dist/index.js")


def _normalize_personal_os_config(cfg: dict) -> dict:
    normalized = dict(cfg)
    args = list(normalized.get("args") or [])
    current_index = Path(args[0]) if args and _looks_like_personal_os_mcp_index(args[0]) else None
    current_exists = bool(current_index and current_index.exists())
    found = _find_personal_os_mcp_index()

    if found:
        os_root, mcp_index = found
        if not current_exists:
            if args:
                args[0] = str(mcp_index)
            else:
                args = [str(mcp_index)]
            normalized["args"] = args

        env = dict(normalized.get("env") or {})
        env.setdefault("PERSONAL_OS_ROOT", str(os_root))
        env.setdefault("PERSONAL_OS_SDK_ROOT", str(os_root))
        normalized["env"] = env

    return normalized


class MCPRegistry:
    """Central registry for MCP server connections and tools.

    Responsibilities:
    - Load/save server configs from mcp_servers.json
    - Manage MCPClient instances per server
    - Track connection status (connected, disconnected, error)
    - Auto-discover tools from connected servers
    - Provide merged tool list for LLM integration
    """

    def __init__(self):
        self._configs: dict[str, dict] = {}
        self._clients: dict[str, MCPClient] = {}
        self._errors: dict[str, str] = {}  # server_name -> last error message
        self._loaded = False

    def load_config(self) -> dict[str, dict]:
        """Load MCP server configs from mcp_servers.json.

        Returns the loaded configs dict. Creates empty config if missing.
        """
        config_path = next((path for path in _mcp_config_candidates() if path.exists()), None)
        if config_path is None:
            logger.info("MCP config not found — no external servers configured")
            self._configs = {}
            self._loaded = True
            return self._configs

        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            servers = data.get("servers", {})

            # Validate each server config
            valid: dict[str, dict] = {}
            for name, cfg in servers.items():
                if not isinstance(cfg, dict):
                    logger.warning(f"MCP config: invalid entry '{name}' — skipping")
                    continue
                if "command" not in cfg:
                    logger.warning(f"MCP config: '{name}' missing 'command' — skipping")
                    continue
                # Sanitize name: alphanumeric + hyphens + underscores only
                if not all(c.isalnum() or c in "-_" for c in name):
                    logger.warning(f"MCP config: invalid server name '{name}' — skipping")
                    continue
                if name == "personal_os":
                    cfg = _normalize_personal_os_config(cfg)
                valid[name] = cfg

            self._configs = valid
            self._loaded = True
            logger.info(f"MCP config loaded: {len(valid)} servers from {config_path}")
            return self._configs

        except json.JSONDecodeError as e:
            logger.error(f"MCP config parse error: {e}")
            self._configs = {}
            self._loaded = True
            return self._configs
        except Exception as e:
            logger.error(f"MCP config load error: {e}", exc_info=True)
            self._configs = {}
            self._loaded = True
            return self._configs

    def get_server_configs(self) -> dict[str, dict]:
        """Get all configured servers."""
        if not self._loaded:
            self.load_config()
        return dict(self._configs)

    def get_server_status(self, name: str) -> str:
        """Get status string for a server: connected, disconnected, error, unknown."""
        if name in self._clients and self._clients[name].is_connected:
            return "connected"
        if name in self._errors:
            return "error"
        if name in self._configs:
            return "disconnected"
        return "unknown"

    def list_servers(self) -> list[dict]:
        """List all configured servers with their status.

        Returns a list of dicts with name, config, status, tools_count, error.
        """
        if not self._loaded:
            self.load_config()

        result = []
        for name, cfg in self._configs.items():
            client = self._clients.get(name)
            entry = {
                "name": name,
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "enabled": cfg.get("enabled", True),
                "status": self.get_server_status(name),
                "tools_count": len(client.tools) if client else 0,
                "error": self._errors.get(name),
            }
            if client and client.is_connected:
                entry["server_info"] = client.server_info
                entry["uptime_seconds"] = client.uptime_seconds
            result.append(entry)
        return result

    async def connect(self, name: str) -> dict:
        """Connect to a configured MCP server by name.

        Creates an MCPClient, performs initialization handshake,
        and discovers available tools.

        Returns server info dict.
        Raises MCPError on failure.
        """
        if not self._loaded:
            self.load_config()

        cfg = self._configs.get(name)
        if not cfg:
            raise MCPError(f"Unknown MCP server: '{name}'")

        if not cfg.get("enabled", True):
            raise MCPError(f"MCP server '{name}' is disabled in config")

        # Disconnect existing client if any
        if name in self._clients:
            try:
                await self._clients[name].disconnect()
            except Exception:
                pass

        self._errors.pop(name, None)

        # Build environment for subprocess
        env = dict(os.environ)
        if cfg.get("env"):
            env.update(cfg["env"])

        client = MCPClient(
            name=name,
            command=cfg["command"],
            args=cfg.get("args", []),
            env=env,
        )

        try:
            server_info = await client.connect()
            # Auto-discover tools after successful connection
            await client.list_tools()
            self._clients[name] = client
            logger.info(
                f"MCP [{name}] Ready — {len(client.tools)} tools available"
            )
            return server_info
        except MCPError as exc:
            self._errors[name] = str(exc)
            raise
        except Exception as e:
            self._errors[name] = str(e)
            raise MCPError(f"Connection to '{name}' failed: {e}")

    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        client = self._clients.pop(name, None)
        if client:
            await client.disconnect()
        self._errors.pop(name, None)
        logger.info(f"MCP [{name}] Disconnected")

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers. Called on shutdown."""
        names = list(self._clients.keys())
        for name in names:
            try:
                await self.disconnect(name)
            except Exception as e:
                logger.warning(f"MCP [{name}] Error during disconnect: {e}")

    def get_client(self, name: str) -> Optional[MCPClient]:
        """Get an active MCPClient by server name."""
        client = self._clients.get(name)
        if client and client.is_connected:
            return client
        return None

    def get_server_tools(self, name: str) -> list[dict]:
        """Get tools for a specific connected server."""
        client = self._clients.get(name)
        if not client or not client.is_connected:
            return []
        return client.tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict | None = None) -> Any:
        """Call a tool on a specific MCP server.

        Args:
            server_name: Name of the MCP server.
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns the tool result content.
        """
        client = self.get_client(server_name)
        if not client:
            raise MCPError(f"MCP server '{server_name}' is not connected")
        return await client.call_tool(tool_name, arguments)

    def get_all_mcp_tools(self) -> list[dict]:
        """Get all tools from all connected MCP servers.

        Returns tool definitions in OpenAI function-calling format,
        prefixed with the server name to avoid collisions.
        """
        all_tools: list[dict] = []
        for name, client in self._clients.items():
            if not client.is_connected:
                continue
            for tool in client.tools:
                # Convert MCP tool schema to OpenAI function-calling format
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": f"mcp_{name}_{tool.get('name', '')}",
                        "description": (
                            f"[MCP:{name}] {tool.get('description', 'No description')}"
                        ),
                        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                    },
                }
                all_tools.append(tool_def)
        return all_tools

    def get_merged_tool_definitions(self, existing_tools: list[dict]) -> list[dict]:
        """Merge existing tool_registry tools with MCP tools for LLM calls.

        Args:
            existing_tools: Tool definitions from tool_registry.py.

        Returns combined list (existing + MCP tools).
        """
        if not MCP_ENABLED:
            return existing_tools

        mcp_tools = self.get_all_mcp_tools()
        if not mcp_tools:
            return existing_tools

        logger.debug(f"Merging {len(existing_tools)} local + {len(mcp_tools)} MCP tools")
        return existing_tools + mcp_tools


# ── Singleton ─────────────────────────────────
mcp_registry = MCPRegistry()
