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


def test_mcp_registry_repairs_stale_personal_os_mcp_path(monkeypatch, tmp_path):
    import backend.mcp_registry as mcp_registry

    os_root = tmp_path / "OS"
    mcp_index = os_root / "11_Integrations" / "MCP" / "os-mcp-server" / "dist" / "index.js"
    mcp_index.parent.mkdir(parents=True)
    mcp_index.write_text("console.log('mcp')", encoding="utf-8")

    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(json.dumps({
        "servers": {
            "personal_os": {
                "command": "node",
                "args": ["C:\\Users\\admin\\OneDrive\\Desktop\\lexa\\lexa-ai\\personal_os\\11_Integrations\\MCP\\os-mcp-server\\dist\\index.js"],
                "enabled": True,
            }
        }
    }), encoding="utf-8")

    monkeypatch.setenv("PERSONAL_OS_ROOT", str(os_root))
    monkeypatch.setattr(mcp_registry, "MCP_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_registry, "PROJECT_MCP_CONFIG_PATH", config_path)

    registry = mcp_registry.MCPRegistry()
    configs = registry.load_config()

    assert configs["personal_os"]["args"][0] == str(mcp_index.resolve())
    assert configs["personal_os"]["env"]["PERSONAL_OS_ROOT"] == str(os_root.resolve())
    assert configs["personal_os"]["env"]["PERSONAL_OS_SDK_ROOT"] == str(os_root.resolve())
