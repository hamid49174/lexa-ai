import json


def test_mcp_registry_load_config_falls_back_to_project_config(monkeypatch, tmp_path):
    import backend.mcp_registry as mcp_registry

    data_dir = tmp_path / "data"
    project_dir = tmp_path / "project"
    data_dir.mkdir()
    project_dir.mkdir()
    project_config = project_dir / "mcp_servers.json"
    project_config.write_text(json.dumps({
        "servers": {
            "personal_os": {
                "command": "node",
                "args": ["dist/index.js"],
                "enabled": True,
            }
        }
    }), encoding="utf-8")

    monkeypatch.setattr(mcp_registry, "MCP_CONFIG_PATH", data_dir / "mcp_servers.json")
    monkeypatch.setattr(mcp_registry, "PROJECT_MCP_CONFIG_PATH", project_config)

    registry = mcp_registry.MCPRegistry()
    configs = registry.load_config()

    assert "personal_os" in configs
    assert configs["personal_os"]["command"] == "node"
