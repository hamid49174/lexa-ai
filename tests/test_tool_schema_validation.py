import pytest
from pydantic import ValidationError

from backend.tool_registry import ToolSchemaValidationError, get_tool, validate_tool_arguments
from backend.tool_schema import build_parameter_descriptor, build_tool_definition


def test_pydantic_tool_schema_builder_emits_openai_shape():
    parameter = build_parameter_descriptor(
        "name",
        "string",
        "Application name",
        required=True,
    )
    tool = build_tool_definition("app_open", "Open an app", [parameter])

    assert tool["type"] == "function"
    assert tool["function"]["parameters"]["type"] == "object"
    assert tool["function"]["parameters"]["required"] == ["name"]
    assert tool["function"]["parameters"]["properties"]["name"]["type"] == "string"


def test_pydantic_tool_schema_builder_rejects_invalid_array_items():
    with pytest.raises(ValidationError):
        build_parameter_descriptor(
            "items",
            "array",
            "Invalid array",
            items_type="unsupported",
        )


def test_registered_tools_keep_openai_schema_shape():
    tool = get_tool("file_write")
    parameters = tool["function"]["parameters"]

    assert parameters["type"] == "object"
    assert parameters["properties"]["path"]["type"] == "string"
    assert parameters["properties"]["content"]["type"] == "string"
    assert set(parameters["required"]) == {"path", "content"}


def test_valid_tool_arguments_pass_from_registry_schema():
    args = validate_tool_arguments("app_open", {"name": "notepad"})

    assert args == {"name": "notepad"}


def test_file_write_arguments_pass_from_registry_schema():
    args = validate_tool_arguments(
        "file_write",
        {"path": "example.py", "content": "print('hi')", "create_dirs": True},
    )

    assert args["path"] == "example.py"
    assert args["content"] == "print('hi')"
    assert args["create_dirs"] is True


def test_desktop_click_arguments_pass_from_registry_schema():
    args = validate_tool_arguments(
        "desktop_click",
        {"x": 10, "y": 20, "button": "left", "clicks": 1},
    )

    assert args == {"x": 10, "y": 20, "button": "left", "clicks": 1}


def test_desktop_click_rejects_unknown_button():
    with pytest.raises(ToolSchemaValidationError, match="one of"):
        validate_tool_arguments(
            "desktop_click",
            {"x": 10, "y": 20, "button": "side", "clicks": 1},
        )


def test_desktop_click_text_arguments_pass_from_registry_schema():
    args = validate_tool_arguments(
        "desktop_click_text",
        {"text": "Mikrofon", "button": "left", "occurrence": 1},
    )

    assert args == {"text": "Mikrofon", "button": "left", "occurrence": 1}


def test_ui_click_arguments_pass_from_registry_schema():
    args = validate_tool_arguments(
        "ui_click",
        {"text": "Mikrofon", "control_type": "Button", "button": "left", "fallback_ocr": True},
    )

    assert args == {
        "text": "Mikrofon",
        "control_type": "Button",
        "button": "left",
        "fallback_ocr": True,
    }


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
    with pytest.raises(ToolSchemaValidationError, match="not allowed"):
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


def test_enum_tool_argument_case_mismatch_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="one of"):
        validate_tool_arguments(
            "image_convert",
            {"path": "image.png", "format": "PNG"},
        )


def test_null_required_tool_argument_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="must be string"):
        validate_tool_arguments("app_open", {"name": None})


def test_numeric_string_for_integer_tool_argument_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="must be integer"):
        validate_tool_arguments("volume_set", {"level": "50"})


def test_array_with_wrong_item_type_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match=r"actions\[0\] must be object"):
        validate_tool_arguments(
            "routine_create",
            {
                "name": "morning",
                "description": "start",
                "schedule": "08:00",
                "actions": ["system_info"],
            },
        )


def test_nested_dangerous_argument_key_is_rejected():
    with pytest.raises(ToolSchemaValidationError, match="not allowed"):
        validate_tool_arguments(
            "routine_create",
            {
                "name": "morning",
                "description": "start",
                "schedule": "08:00",
                "actions": [{
                    "command": "system_info",
                    "params": {"constructor": {"prototype": {"polluted": True}}},
                }],
            },
        )
