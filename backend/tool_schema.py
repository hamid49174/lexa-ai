"""Typed builders for Lexa tool schemas.

The registry still exposes plain OpenAI-compatible dictionaries, but schema
construction goes through Pydantic models so malformed tool definitions fail
early while the app starts instead of surfacing later during a tool call.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonSchemaType = Literal["string", "integer", "number", "boolean", "array", "object"]


class JsonSchemaFragment(BaseModel):
    """JSON-Schema subset used by the tool registry."""

    model_config = ConfigDict(extra="forbid")

    type: JsonSchemaType
    description: str | None = None
    enum: list[Any] | None = None
    default: Any = None
    items: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_items(self) -> "JsonSchemaFragment":
        if self.type == "array":
            if self.items is None:
                return self
            item_type = self.items.get("type")
            valid_item_types = {"string", "integer", "number", "boolean", "array", "object"}
            if item_type not in valid_item_types:
                raise ValueError(f"array items must declare a supported type, got {item_type!r}")
        elif self.items is not None:
            raise ValueError("items is only valid for array schemas")
        return self

    def to_schema(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ToolParameter(BaseModel):
    """Intermediate representation for a single tool argument."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1)
    json_schema: JsonSchemaFragment = Field(alias="schema")
    required: bool = False

    def to_descriptor(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema": self.json_schema.to_schema(),
            "required": self.required,
        }


class ToolFunctionParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["object"] = "object"
    properties: dict[str, dict[str, Any]]
    required: list[str] | None = None

    @model_validator(mode="after")
    def _validate_required(self) -> "ToolFunctionParameters":
        if self.required:
            missing = [name for name in self.required if name not in self.properties]
            if missing:
                raise ValueError(f"required parameters missing from properties: {', '.join(missing)}")
        return self


class ToolFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters: ToolFunctionParameters


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = "function"
    confirmation_required: bool = False
    function: ToolFunction

    def to_openai_tool(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


def build_parameter_descriptor(
    name: str,
    type_: JsonSchemaType,
    description: str,
    *,
    required: bool = False,
    enum: list[str] | None = None,
    default: Any = None,
    items_type: JsonSchemaType | None = None,
) -> dict[str, Any]:
    """Build the registry's compact parameter descriptor."""
    schema_data: dict[str, Any] = {"type": type_, "description": description}
    if enum:
        schema_data["enum"] = enum
    if default is not None:
        schema_data["default"] = default
    if type_ == "array" and items_type:
        schema_data["items"] = {"type": items_type}
    parameter = ToolParameter(
        name=name,
        schema=JsonSchemaFragment(**schema_data),
        required=required,
    )
    return parameter.to_descriptor()


def build_tool_definition(
    name: str,
    description: str,
    params: list[dict[str, Any]] | None = None,
    *,
    confirmation_required: bool = False,
) -> dict[str, Any]:
    """Build a complete OpenAI-compatible function tool definition."""
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for raw_param in params or []:
        parameter = ToolParameter(**raw_param)
        descriptor = parameter.to_descriptor()
        properties[descriptor["name"]] = descriptor["schema"]
        if descriptor.get("required"):
            required.append(descriptor["name"])

    desc = description
    if confirmation_required:
        desc += " \u26a0\ufe0f Braucht User-Best\u00e4tigung."

    parameter_block = ToolFunctionParameters(
        properties=properties,
        required=required or None,
    )
    tool = ToolDefinition(
        confirmation_required=bool(confirmation_required),
        function=ToolFunction(
            name=name,
            description=desc,
            parameters=parameter_block,
        ),
    )
    return tool.to_openai_tool()
