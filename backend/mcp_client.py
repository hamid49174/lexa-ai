"""Lexa AI — MCP Client (Phase 47: Model Context Protocol)
Lightweight JSON-RPC 2.0 client for MCP servers.
Supports stdio transport (subprocess) and SSE transport (HTTP).

MCP Protocol:
- initialize: handshake with server capabilities
- tools/list: discover available tools
- tools/call: execute a tool with arguments
- Communication: newline-delimited JSON-RPC 2.0
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from backend.config import LEXA_DATA_DIR, MCP_CONNECT_TIMEOUT, MCP_CALL_TIMEOUT

logger = logging.getLogger("lexa.mcp_client")

# JSON-RPC 2.0 protocol version
JSONRPC_VERSION = "2.0"

# MCP protocol version we support
MCP_PROTOCOL_VERSION = "2024-11-05"

# Some Personal OS review packets and context maps exceed asyncio's default
# 64 KiB StreamReader line limit because MCP stdio frames are newline-delimited
# JSON. Keep this comfortably above expected local Markdown payloads.
MCP_STDIO_READ_LIMIT = 16 * 1024 * 1024

# Client info sent during initialization
CLIENT_INFO = {
    "name": "lexa-ai",
    "version": "1.0.0",
}


class MCPError(Exception):
    """Error from MCP server or protocol violation."""

    def __init__(self, message: str, code: int = -1, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPClient:
    """JSON-RPC 2.0 client for a single MCP server.

    Manages the subprocess lifecycle and provides async methods
    for the MCP protocol operations (initialize, list_tools, call_tool).
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._server_info: dict = {}
        self._server_capabilities: dict = {}
        self._lock = asyncio.Lock()
        self._tools: list[dict] = []
        self._connected_at: float = 0.0

    @property
    def is_connected(self) -> bool:
        """Check if the subprocess is running and initialized."""
        return (
            self._process is not None
            and self._process.returncode is None
            and self._initialized
        )

    @property
    def server_info(self) -> dict:
        return self._server_info

    @property
    def tools(self) -> list[dict]:
        return self._tools

    @property
    def uptime_seconds(self) -> int:
        if not self._connected_at:
            return 0
        return int(time.time() - self._connected_at)

    # ── Lifecycle ─────────────────────────────────

    async def connect(self) -> dict:
        """Start the MCP server subprocess and perform initialization handshake.

        Returns server info dict on success.
        Raises MCPError on failure or timeout.
        """
        async with self._lock:
            if self.is_connected:
                return self._server_info

            logger.info(f"MCP [{self.name}] Starting: {self.command} {' '.join(self.args)}")

            try:
                # Pin the working directory to a defined, writable location
                # (LEXA_DATA_DIR) instead of inheriting the backend's cwd, which
                # in packaged builds can be an OneDrive/PyInstaller path. This
                # makes the behaviour of MCP servers that use relative paths
                # deterministic regardless of how the backend was started.
                self._process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        self.command,
                        *self.args,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=self.env,
                        cwd=str(LEXA_DATA_DIR),
                        limit=MCP_STDIO_READ_LIMIT,
                    ),
                    timeout=MCP_CONNECT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise MCPError(f"Timeout starting MCP server '{self.name}'")
            except FileNotFoundError:
                raise MCPError(f"Command not found: {self.command}")
            except Exception as e:
                raise MCPError(f"Failed to start MCP server '{self.name}': {e}")

            # Start background reader for stdout
            self._reader_task = asyncio.create_task(self._read_loop())
            # Drain stderr continuously so the OS pipe buffer can never fill up.
            # Many MCP servers (e.g. Node-based ones) log heavily to stderr; if
            # it is never read, the child blocks on write and stops answering on
            # stdout, deadlocking every JSON-RPC call.
            if self._process.stderr is not None:
                self._stderr_task = asyncio.create_task(self._drain_stderr())

            # Perform MCP initialize handshake
            try:
                result = await self._send_request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": CLIENT_INFO,
                    },
                    timeout=MCP_CONNECT_TIMEOUT,
                )
            except Exception as e:
                await self._kill_process()
                raise MCPError(f"MCP initialize handshake failed for '{self.name}': {e}")

            self._server_info = result.get("serverInfo", {})
            self._server_capabilities = result.get("capabilities", {})
            self._initialized = True
            self._connected_at = time.time()

            # Send initialized notification (no response expected)
            await self._send_notification("notifications/initialized", {})

            logger.info(
                f"MCP [{self.name}] Connected — server: "
                f"{self._server_info.get('name', '?')} v{self._server_info.get('version', '?')}"
            )
            return self._server_info

    async def disconnect(self) -> None:
        """Stop the MCP server subprocess gracefully."""
        async with self._lock:
            await self._kill_process()
            self._initialized = False
            self._tools = []
            self._server_info = {}
            self._server_capabilities = {}
            self._connected_at = 0.0
            logger.info(f"MCP [{self.name}] Disconnected")

    async def _kill_process(self) -> None:
        """Terminate the subprocess and cancel reader/stderr tasks."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None

        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stderr_task = None

        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        # Reject all pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPError("Connection closed"))
        self._pending.clear()

    # ── MCP Protocol Methods ─────────────────────

    async def list_tools(self) -> list[dict]:
        """Request the list of available tools from the server.

        Returns a list of tool definitions (name, description, inputSchema).
        """
        if not self.is_connected:
            raise MCPError(f"MCP server '{self.name}' is not connected")

        result = await self._send_request("tools/list", {}, timeout=MCP_CALL_TIMEOUT)
        self._tools = result.get("tools", [])
        logger.info(f"MCP [{self.name}] Discovered {len(self._tools)} tools")
        return self._tools

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> Any:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool arguments as a dict.

        Returns:
            The tool result (content array from MCP spec).
        """
        if not self.is_connected:
            raise MCPError(f"MCP server '{self.name}' is not connected")

        # Validate tool name exists
        known_names = {t.get("name") for t in self._tools}
        if known_names and tool_name not in known_names:
            raise MCPError(
                f"Unknown tool '{tool_name}' on server '{self.name}'. "
                f"Known tools: {', '.join(sorted(known_names))}"
            )

        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            timeout=MCP_CALL_TIMEOUT,
        )

        # MCP returns { content: [...], isError?: bool }
        is_error = result.get("isError", False)
        content = result.get("content", [])

        if is_error:
            # Extract text from error content
            error_text = ""
            for item in content:
                if item.get("type") == "text":
                    error_text += item.get("text", "")
            raise MCPError(f"Tool '{tool_name}' returned error: {error_text or 'unknown'}")

        return content

    async def health_check(self) -> dict:
        """Check if the server process is still running.

        Returns a status dict with connection info.
        """
        if not self._process or self._process.returncode is not None:
            return {"status": "disconnected", "name": self.name}

        if not self._initialized:
            return {"status": "connecting", "name": self.name}

        return {
            "status": "connected",
            "name": self.name,
            "server_info": self._server_info,
            "tools_count": len(self._tools),
            "uptime_seconds": self.uptime_seconds,
        }

    # ── JSON-RPC Transport ───────────────────────

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            raise MCPError("No active connection")

        req_id = self._next_id()
        message = {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        line = json.dumps(message, ensure_ascii=False) + "\n"
        try:
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception as e:
            self._pending.pop(req_id, None)
            raise MCPError(f"Failed to send request: {e}")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise MCPError(f"Timeout waiting for response to '{method}' (id={req_id})")

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        message = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
            "params": params,
        }

        line = json.dumps(message, ensure_ascii=False) + "\n"
        try:
            self._process.stdin.write(line.encode("utf-8"))
            await self._process.stdin.drain()
        except Exception as e:
            logger.warning(f"MCP [{self.name}] Failed to send notification '{method}': {e}")

    async def _read_loop(self) -> None:
        """Background task that reads JSON-RPC messages from stdout."""
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    # EOF — process exited
                    logger.warning(f"MCP [{self.name}] Server process ended (EOF)")
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug(f"MCP [{self.name}] Non-JSON output: {line_str[:200]}")
                    continue

                # Handle JSON-RPC response (has "id" field)
                msg_id = msg.get("id")
                # JSON-RPC 2.0 allows the id to be a string OR a number. We
                # always send integer ids, but some servers echo them back as a
                # numeric string ("id": "1"). Normalise such ids back to int so
                # the lookup against our int-keyed _pending dict still matches.
                if isinstance(msg_id, str) and msg_id.lstrip("-").isdigit():
                    msg_id = int(msg_id)
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if future.done():
                        continue

                    error = msg.get("error")
                    if error:
                        future.set_exception(
                            MCPError(
                                error.get("message", "Unknown error"),
                                code=error.get("code", -1),
                                data=error.get("data"),
                            )
                        )
                    else:
                        future.set_result(msg.get("result", {}))

                # Notifications from server (no id) — log them
                elif msg_id is None and "method" in msg:
                    logger.debug(
                        f"MCP [{self.name}] Server notification: {msg.get('method')}"
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"MCP [{self.name}] Reader loop error: {e}", exc_info=True)
        finally:
            # Mark connection as broken — reject pending futures
            self._initialized = False
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(MCPError("Connection lost"))
            self._pending.clear()

    async def _drain_stderr(self) -> None:
        """Background task that continuously reads the subprocess stderr.

        Keeps the OS stderr pipe buffer empty (otherwise a chatty server would
        block on write and deadlock its stdout responses). Lines are forwarded
        to the log for diagnostics — including handshake failures, whose root
        cause typically only appears on stderr.
        """
        stderr = self._process.stderr if self._process else None
        if stderr is None:
            return
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break  # EOF — process exited
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.debug(f"MCP [{self.name}] stderr: {text[:500]}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"MCP [{self.name}] stderr drain error: {e}")
