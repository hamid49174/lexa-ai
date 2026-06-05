from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_mcp


def _client(monkeypatch, entries):
    app = FastAPI()
    app.include_router(router_mcp.router)
    monkeypatch.setattr(router_mcp, "MCP_ENABLED", True)
    monkeypatch.setattr(router_mcp, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_mcp, "audit_log", lambda *args, **_kwargs: entries.append(args))
    return TestClient(app)


def test_mcp_connect_error_redacts_client_and_audit(monkeypatch):
    entries = []

    async def fail_connect(_name):
        raise router_mcp.MCPError("failed C:\\Users\\admin\\secret.txt token=supersecretvalue")

    monkeypatch.setattr(router_mcp.mcp_registry, "connect", fail_connect)
    client = _client(monkeypatch, entries)

    response = client.post("/mcp/servers/local/connect")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "[local-path-redacted]" in detail
    assert "C:\\Users\\admin" not in detail
    assert "supersecretvalue" not in detail
    error_entry = next(entry for entry in entries if entry[:2] == ("mcp", "connect_error"))
    details = error_entry[2]
    assert "server=local" in details
    assert "errorType=MCPError" in details
    assert "errorChars=" in details
    assert "errorHash=" in details
    assert "C:\\Users\\admin" not in details
    assert "supersecretvalue" not in details
    assert "error=" not in details


def test_mcp_call_tool_error_redacts_client_and_audit(monkeypatch):
    entries = []

    async def fail_call(_server, _tool, _arguments):
        raise router_mcp.MCPError("tool failed C:\\Users\\admin\\secret.txt token=supersecretvalue")

    monkeypatch.setattr(router_mcp.mcp_registry, "call_tool", fail_call)
    client = _client(monkeypatch, entries)

    response = client.post(
        "/mcp/servers/local/call",
        json={"tool": "read_note", "arguments": {"path": "C:\\Users\\admin\\secret.txt"}},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "[local-path-redacted]" in detail
    assert "C:\\Users\\admin" not in detail
    assert "supersecretvalue" not in detail
    error_entry = next(entry for entry in entries if entry[:2] == ("mcp", "call_tool_error"))
    details = error_entry[2]
    assert "server=local" in details
    assert "tool=read_note" in details
    assert "errorType=MCPError" in details
    assert "errorChars=" in details
    assert "errorHash=" in details
    assert "C:\\Users\\admin" not in details
    assert "supersecretvalue" not in details
    assert "error=" not in details
