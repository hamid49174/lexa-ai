from pathlib import Path


def test_mcp_client_raises_stdio_read_limit_for_large_personal_os_packets():
    source = Path("backend/mcp_client.py").read_text(encoding="utf-8")

    assert "MCP_STDIO_READ_LIMIT = 16 * 1024 * 1024" in source
    assert "limit=MCP_STDIO_READ_LIMIT" in source
    assert "64 KiB StreamReader line limit" in source

