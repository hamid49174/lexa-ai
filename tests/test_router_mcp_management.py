"""Tests fuer die MCP-Server-Verwaltung (Feature: Add/Update/Remove via API)."""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import router_mcp


def _run(coro):
    return asyncio.run(coro)


def _client(monkeypatch, entries=None):
    entries = entries if entries is not None else []
    app = FastAPI()
    app.include_router(router_mcp.router)
    monkeypatch.setattr(router_mcp, "MCP_ENABLED", True)
    monkeypatch.setattr(router_mcp, "check_rate_limit", lambda _bucket: True)
    monkeypatch.setattr(router_mcp, "audit_log", lambda *a, **k: entries.append(a))
    return TestClient(app)


# ── Registry-Ebene (Validierung + Persistenz) ──

def _fresh_registry(monkeypatch, tmp_path):
    import backend.mcp_registry as mr
    monkeypatch.setattr(mr, "MCP_CONFIG_PATH", tmp_path / "mcp_servers.json")
    reg = mr.MCPRegistry()
    reg._configs = {}
    reg._loaded = True
    return mr, reg


def test_registry_add_persists_and_rejects_duplicate(monkeypatch, tmp_path):
    mr, reg = _fresh_registry(monkeypatch, tmp_path)
    clean = reg.add_server("myserver", {"command": "node", "args": ["x.js"], "env": {"K": "v"}})
    assert clean["command"] == "node" and clean["enabled"] is True and clean["args"] == ["x.js"]

    target = mr.MCP_CONFIG_PATH
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["servers"]["myserver"]["command"] == "node"

    with pytest.raises(ValueError, match="existiert bereits"):
        reg.add_server("myserver", {"command": "node"})


def test_registry_update_and_unknown(monkeypatch, tmp_path):
    mr, reg = _fresh_registry(monkeypatch, tmp_path)
    reg.add_server("srv", {"command": "node"})
    reg.update_server("srv", {"command": "npx", "args": ["-y", "pkg"]})
    assert reg._configs["srv"]["command"] == "npx"
    with pytest.raises(ValueError, match="Unbekannt"):
        reg.update_server("ghost", {"command": "x"})


def test_registry_validation_rejects_bad_input(monkeypatch, tmp_path):
    mr, reg = _fresh_registry(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        reg.add_server("bad name!", {"command": "node"})       # ungueltiger Name
    with pytest.raises(ValueError):
        reg.add_server("ok", {"args": []})                      # command fehlt
    with pytest.raises(ValueError):
        reg.add_server("ok2", {"command": "node", "args": "nope"})  # args kein Array


def test_registry_remove_disconnects_and_persists(monkeypatch, tmp_path):
    mr, reg = _fresh_registry(monkeypatch, tmp_path)
    reg.add_server("srv", {"command": "node"})
    _run(reg.remove_server("srv"))
    assert "srv" not in reg._configs
    data = json.loads(mr.MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    assert "srv" not in data["servers"]
    with pytest.raises(ValueError, match="Unbekannt"):
        _run(reg.remove_server("srv"))


# ── Router-Ebene ──

def test_add_server_endpoint_hides_env(monkeypatch):
    monkeypatch.setattr(router_mcp.mcp_registry, "add_server",
                        lambda name, cfg: {"command": cfg["command"], "args": cfg.get("args", []),
                                            "env": {"SECRET": "x"}, "enabled": True})
    client = _client(monkeypatch)
    r = client.post("/mcp/servers/foo", json={"command": "node", "args": ["a.js"], "env": {"SECRET": "x"}})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "added" and body["server"] == "foo" and body["command"] == "node"
    assert "env" not in body  # Secrets nicht zurueckspiegeln


def test_add_server_duplicate_is_400(monkeypatch):
    def dup(name, cfg):
        raise ValueError("MCP-Server 'foo' existiert bereits.")
    monkeypatch.setattr(router_mcp.mcp_registry, "add_server", dup)
    client = _client(monkeypatch)
    r = client.post("/mcp/servers/foo", json={"command": "node"})
    assert r.status_code == 400


def test_update_unknown_is_404(monkeypatch):
    def unknown(name, cfg):
        raise ValueError("Unbekannter MCP-Server: 'ghost'.")
    monkeypatch.setattr(router_mcp.mcp_registry, "update_server", unknown)
    client = _client(monkeypatch)
    r = client.put("/mcp/servers/ghost", json={"command": "node"})
    assert r.status_code == 404


def test_remove_server_endpoint(monkeypatch):
    removed = {}

    async def fake_remove(name):
        removed["name"] = name

    monkeypatch.setattr(router_mcp.mcp_registry, "remove_server", fake_remove)
    client = _client(monkeypatch)
    r = client.delete("/mcp/servers/foo")
    assert r.status_code == 200 and r.json()["status"] == "removed"
    assert removed["name"] == "foo"


def test_remove_unknown_is_404(monkeypatch):
    async def fake_remove(name):
        raise ValueError("Unbekannter MCP-Server: 'ghost'.")
    monkeypatch.setattr(router_mcp.mcp_registry, "remove_server", fake_remove)
    client = _client(monkeypatch)
    r = client.delete("/mcp/servers/ghost")
    assert r.status_code == 404


def test_management_invalid_name_is_400(monkeypatch):
    client = _client(monkeypatch)
    assert client.post("/mcp/servers/bad%20name", json={"command": "node"}).status_code == 400


def test_management_disabled_returns_400(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(router_mcp, "MCP_ENABLED", False)
    assert client.post("/mcp/servers/foo", json={"command": "node"}).status_code == 400
    assert client.delete("/mcp/servers/foo").status_code == 400
