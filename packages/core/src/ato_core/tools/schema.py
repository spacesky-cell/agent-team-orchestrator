"""Convert the canonical tool JSON schemas into Pydantic models."""

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, create_model

_TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def pydantic_model_for_tool(schema: dict[str, Any], model_name: str) -> type[BaseModel]:
    """Build a strict argument model while preserving required fields and defaults."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, tuple[Any, Any]] = {}

    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type")
        if json_type not in _TYPE_MAP:
            raise ValueError(f"TOOL_SCHEMA_UNSUPPORTED: {field_name} uses {json_type!r}")
        field_type: Any = _TYPE_MAP[json_type]
        if "enum" in field_schema:
            field_type = Literal.__getitem__(tuple(field_schema["enum"]))

        if field_name in required:
            default: Any = ...
        elif "default" in field_schema:
            default = field_schema["default"]
        else:
            field_type = field_type | None
            default = None

        fields[field_name] = (
            field_type,
            Field(default=default, description=field_schema.get("description")),
        )

    return cast(
        type[BaseModel],
        create_model(  # type: ignore[call-overload]
            model_name,
            __config__=ConfigDict(extra="forbid"),
            **fields,
        ),
    )
