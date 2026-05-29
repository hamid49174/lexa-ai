"""Tests for explicit tool confirmation metadata."""


def test_tool_builder_records_confirmation_metadata():
    from backend import tool_registry

    dangerous = tool_registry._tool("unit_dangerous", "Dangerous test tool", confirmation_required=True)
    safe = tool_registry._tool("unit_safe", "Safe test tool", confirmation_required=False)

    assert dangerous["confirmation_required"] is True
    assert safe["confirmation_required"] is False
    assert "\u26a0" in dangerous["function"]["description"]


def test_confirmation_check_uses_metadata_not_description(monkeypatch):
    from backend import tool_registry

    confirmed_without_marker = tool_registry._tool(
        "unit_confirmed_without_marker",
        "Dangerous test tool",
        confirmation_required=True,
    )
    confirmed_without_marker["function"]["description"] = "Dangerous test tool"

    safe_with_marker = tool_registry._tool(
        "unit_safe_with_marker",
        "Safe test tool \u26a0\ufe0f marker in text only",
        confirmation_required=False,
    )

    monkeypatch.setitem(tool_registry._TOOL_MAP, "unit_confirmed_without_marker", confirmed_without_marker)
    monkeypatch.setitem(tool_registry._TOOL_MAP, "unit_safe_with_marker", safe_with_marker)

    assert tool_registry.is_confirmation_tool("unit_confirmed_without_marker") is True
    assert tool_registry.is_confirmation_tool("unit_safe_with_marker") is False


def test_registered_tools_have_explicit_confirmation_field():
    from backend import tool_registry

    tools = tool_registry.get_all_tools()

    assert tools
    assert all(isinstance(tool.get("confirmation_required"), bool) for tool in tools)
    assert tool_registry.get_tool("process_kill")["confirmation_required"] is True
    assert tool_registry.is_confirmation_tool("process_kill") is True
    assert tool_registry.get_tool("desktop_click")["confirmation_required"] is True
    assert tool_registry.get_tool("desktop_click_text")["confirmation_required"] is True
    assert tool_registry.get_tool("desktop_type")["confirmation_required"] is True
    assert tool_registry.get_tool("ui_click")["confirmation_required"] is True
    assert tool_registry.get_tool("system_info")["confirmation_required"] is False
    assert tool_registry.get_tool("desktop_position")["confirmation_required"] is False
    assert tool_registry.get_tool("ui_tree")["confirmation_required"] is False
    assert tool_registry.get_tool("ui_find")["confirmation_required"] is False
    assert tool_registry.is_confirmation_tool("system_info") is False
    assert tool_registry.is_confirmation_tool("unknown_test_tool") is True


def test_provider_tool_payload_strips_lexa_metadata():
    from backend import tool_registry
    from backend.ai_engine import _provider_tool_payload

    tool = tool_registry._tool(
        "unit_provider_payload",
        "Provider payload test",
        [tool_registry._param("path", "string", "Path", required=True)],
        confirmation_required=True,
    )

    payload = _provider_tool_payload([tool])

    assert tool["confirmation_required"] is True
    assert "confirmation_required" not in payload[0]
    assert payload[0]["type"] == "function"
    assert payload[0]["function"] == tool["function"]
