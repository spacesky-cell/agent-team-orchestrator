"""Structured tool-call protocol for the Claude Code CLI provider."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal


class ToolResponseParseError(ValueError):
    """Raised when a Claude CLI response does not match the tool protocol."""


@dataclass
class ClaudeCliToolResponse:
    """Parsed Claude CLI structured response."""

    type: Literal["tool_call", "final"]
    content: str | None = None
    name: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return stripped


def parse_claude_cli_tool_response(text: str) -> ClaudeCliToolResponse:
    """Parse a Claude CLI tool protocol response.

    The response must be either raw JSON or a fenced JSON block:
    {"type":"tool_call","name":"read_file","args":{"path":"README.md"}}
    {"type":"final","content":"..."}
    """
    payload = _extract_json_payload(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ToolResponseParseError(f"Claude CLI response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ToolResponseParseError("Claude CLI response must be a JSON object.")

    response_type = data.get("type")
    if response_type == "final":
        content = data.get("content")
        if not isinstance(content, str):
            raise ToolResponseParseError("Final response must include string field 'content'.")
        return ClaudeCliToolResponse(type="final", content=content)

    if response_type == "tool_call":
        name = data.get("name")
        args = data.get("args", {})
        if not isinstance(name, str) or not name:
            raise ToolResponseParseError("Tool call response must include string field 'name'.")
        if not isinstance(args, dict):
            raise ToolResponseParseError("Tool call response field 'args' must be an object.")
        return ClaudeCliToolResponse(type="tool_call", name=name, args=args)

    raise ToolResponseParseError("Claude CLI response type must be 'tool_call' or 'final'.")


def build_tool_protocol_prompt(tools: list[Any]) -> str:
    """Build the tool protocol instructions injected into Claude CLI prompts."""
    schemas = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in tools
    ]

    return (
        "## Tool Response Protocol\n\n"
        "Respond with exactly one JSON object and no extra prose.\n\n"
        "To call a tool:\n"
        '{"type":"tool_call","name":"read_file","args":{"path":"README.md"}}\n\n'
        "When the task is complete:\n"
        '{"type":"final","content":"your final deliverable"}\n\n'
        "If no tool is needed, return a final response immediately.\n\n"
        "Available tools:\n"
        f"{json.dumps(schemas, indent=2, ensure_ascii=False)}"
    )


def tool_protocol_json_schema(tools: list[Any]) -> dict[str, Any]:
    """Return JSON Schema for one Claude CLI tool protocol turn."""
    tool_names = [tool.name for tool in tools]
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["tool_call", "final"]},
            "name": {"type": "string", "enum": tool_names or ["__no_tools_available__"]},
            "args": {"type": "object", "additionalProperties": True},
            "content": {"type": "string"},
        },
        "required": ["type"],
        "additionalProperties": False,
    }
