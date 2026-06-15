"""Unit coverage for the generic MCP -> chat bridge (backend/mcp_chat_bridge.py).

Uses a mocked mcp_registry singleton — no real MCP subprocess needed.
"""
import asyncio

import backend.mcp_chat_bridge as bridge
from backend.mcp_registry import MCPError


def _mock_registry(monkeypatch, *, connected=True, tools=None, call_result="OK", call_raises=None):
    tools = tools if tools is not None else [
        {"name": "git_status", "description": "status", "inputSchema": {"type": "object"}},
        {"name": "commit", "description": "commit", "inputSchema": {"type": "object"}},
    ]
    reg = bridge.mcp_registry
    monkeypatch.setattr(reg, "list_servers", lambda: [
        {"name": "git", "status": "connected" if connected else "disconnected"},
    ])
    monkeypatch.setattr(reg, "get_server_tools", lambda name: tools if name == "git" else [])
    monkeypatch.setattr(reg, "get_all_mcp_tools", lambda: [
        {"type": "function", "function": {"name": f"mcp_git_{t['name']}", "description": "", "parameters": {}}}
        for t in tools
    ])

    async def _call(server, tool, args=None):
        if call_raises:
            raise call_raises
        return call_result
    monkeypatch.setattr(reg, "call_tool", _call)
    return reg


def test_is_mcp_action():
    assert bridge.is_mcp_action("mcp_git_git_status") is True
    assert bridge.is_mcp_action("mcp_filesystem_read_text_file") is True
    assert bridge.is_mcp_action("system_info") is False
    assert bridge.is_mcp_action("") is False
    assert bridge.is_mcp_action(None) is False


def test_all_mcp_actions_are_confirmation_gated():
    # Machine access -> never auto-run; always confirmation.
    assert bridge.mcp_action_requires_confirmation("mcp_git_commit") is True
    assert bridge.mcp_action_requires_confirmation("mcp_filesystem_write_file") is True


def test_resolve_maps_generated_name_to_server_and_tool(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch)
    assert bridge.resolve_mcp_action("mcp_git_git_status") == ("git", "git_status")
    assert bridge.resolve_mcp_action("mcp_git_commit") == ("git", "commit")
    assert bridge.resolve_mcp_action("mcp_git_unknown") is None
    assert bridge.resolve_mcp_action("mcp_nope_x") is None


def test_resolve_ignores_disconnected_servers(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch, connected=False)
    assert bridge.resolve_mcp_action("mcp_git_git_status") is None


def test_execute_success(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch, call_result={"branch": "main"})
    res = asyncio.run(bridge.execute_mcp_action("mcp_git_git_status", {}))
    assert res["success"] is True and res["data"] == {"branch": "main"}


def test_execute_unresolved_is_rejected(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch)
    res = asyncio.run(bridge.execute_mcp_action("mcp_git_does_not_exist", {}))
    assert res["success"] is False and "nicht verbunden" in res["error"]


def test_execute_redacts_errors(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch, call_raises=MCPError("boom at C:\\Users\\admin\\secret\\x.py"))
    res = asyncio.run(bridge.execute_mcp_action("mcp_git_git_status", {}))
    assert res["success"] is False
    assert "C:\\Users\\admin" not in res["error"]  # local path redacted


def test_disabled_mcp_returns_no_tools_and_blocks_execution(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", False)
    assert bridge.mcp_chat_tools() == []
    res = asyncio.run(bridge.execute_mcp_action("mcp_git_git_status", {}))
    assert res["success"] is False and "deaktiviert" in res["error"]


def test_chat_tools_passthrough_when_enabled(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch)
    tools = bridge.mcp_chat_tools()
    names = [t["function"]["name"] for t in tools]
    assert "mcp_git_git_status" in names and "mcp_git_commit" in names
