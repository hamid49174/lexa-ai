import pytest

from backend.tool_registry import ToolSchemaValidationError, validate_tool_arguments


def test_valid_tool_arguments_pass_from_registry_schema():
    args = validate_tool_arguments("app_open", {"name": "notepad"})

    assert args == {"name": "notepad"}


def test_missing_required_tool_argument_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="required"):
        validate_tool_arguments("app_open", {})


def test_wrong_tool_argument_type_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="must be string"):
        validate_tool_arguments("app_open", {"name": 123})


def test_unknown_tool_argument_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="unknown parameter"):
        validate_tool_arguments("system_info", {"unexpected": "value"})


def test_malicious_extra_tool_argument_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="unknown parameter"):
        validate_tool_arguments(
            "app_open",
            {"name": "notepad", "__proto__": {"polluted": True}},
        )


def test_hallucinated_tool_name_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="unknown tool"):
        validate_tool_arguments("hallucinated_tool", {})


def test_enum_tool_argument_value_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="one of"):
        validate_tool_arguments(
            "image_convert",
            {"path": "image.png", "format": "exe"},
        )
