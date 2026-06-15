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


def test_is_coding_context():
    for m in ["commit meine änderungen", "refactor diese funktion", "fix den bug in chat.js",
              "git status", "implementier eine neue methode", "schreib einen unit test"]:
        assert bridge.is_coding_context(m), m
    for m in ["wie geht es dir", "was ist die hauptstadt von frankreich", "plan meinen tag", ""]:
        assert not bridge.is_coding_context(m), m


def test_coding_mcp_tools_only_in_coding_context(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    _mock_registry(monkeypatch)
    assert bridge.coding_mcp_tools("wie geht es dir") == []          # no coding ctx -> no tools
    assert len(bridge.coding_mcp_tools("git commit machen")) >= 1     # coding ctx -> tools


def test_ensure_skips_disabled_and_unconfigured(monkeypatch):
    monkeypatch.setattr(bridge, "MCP_ENABLED", True)
    reg = bridge.mcp_registry
    monkeypatch.setattr(reg, "get_server_configs", lambda: {
        "git": {"enabled": True}, "serena": {"enabled": False},
    })
    monkeypatch.setattr(reg, "get_server_status", lambda n: "disconnected")

    connected = []
    async def _connect(name):
        connected.append(name)
        return {}
    monkeypatch.setattr(reg, "connect", _connect)

    status = asyncio.run(bridge.ensure_coding_servers_connected(("git", "serena", "filesystem")))
    assert status["git"] == "connected"        # enabled -> connected
    assert status["serena"] == "disabled"      # disabled -> skipped (no retry noise)
    assert status["filesystem"] == "not_configured"
    assert connected == ["git"]                # only the enabled one was actually dialed


def test_validate_tool_arguments_mcp_bypass():
    from backend.tool_registry import validate_tool_arguments, ToolSchemaValidationError
    # mcp_* bypass static registry (dynamic server schema), accepts dict params:
    assert validate_tool_arguments("mcp_git_commit", {"message": "x", "all": True}) == {"message": "x", "all": True}
    # still rejects non-dict + dangerous keys:
    try:
        validate_tool_arguments("mcp_git_commit", "not a dict")
        assert False, "should reject non-dict"
    except ToolSchemaValidationError:
        pass


def test_execute_pending_confirmation_routes_mcp(monkeypatch):
    import backend.router_chat as rc
    called = {}
    async def _fake_exec(name, params):
        called["name"] = name
        called["params"] = params
        return {"success": True, "data": "done"}
    monkeypatch.setattr(bridge, "execute_mcp_action", _fake_exec)
    monkeypatch.setattr(bridge, "is_mcp_action", lambda n: str(n).startswith("mcp_"))

    reply = asyncio.run(rc._execute_pending_confirmation(
        {"action": "mcp_git_commit", "params": {"message": "hi"}}, "test"))
    assert called.get("name") == "mcp_git_commit"
    assert called.get("params") == {"message": "hi"}
    assert isinstance(reply, str) and reply
