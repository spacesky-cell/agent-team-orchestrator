"""Tests for Claude CLI structured tool calls and audit policy."""

import json

import pytest
from langchain_core.messages import AIMessage

from src.tools.base import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo a value"
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string", "description": "Value to echo"}},
        "required": ["value"],
    }

    async def execute(self, **kwargs):
        return f"echo:{kwargs['value']}"


class CommandTool(BaseTool):
    name = "execute_command"
    description = "Pretend to execute a command"
    parameters = {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "Command"}},
        "required": ["command"],
    }

    async def execute(self, **kwargs):
        return f"ran:{kwargs['command']}"


class FakeClaudeCliModel:
    is_claude_cli = True

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages)
        if not self.outputs:
            raise AssertionError("fake model invoked too many times")
        return AIMessage(content=self.outputs.pop(0))


def test_parse_structured_claude_cli_tool_call_from_fenced_json():
    from src.orchestrator.claude_cli_tools import parse_claude_cli_tool_response

    parsed = parse_claude_cli_tool_response(
        """
```json
{"type":"tool_call","name":"echo","args":{"value":"hello"}}
```
"""
    )

    assert parsed.type == "tool_call"
    assert parsed.name == "echo"
    assert parsed.args == {"value": "hello"}


def test_parse_structured_claude_cli_final_response_from_raw_json():
    from src.orchestrator.claude_cli_tools import parse_claude_cli_tool_response

    parsed = parse_claude_cli_tool_response('{"type":"final","content":"done"}')

    assert parsed.type == "final"
    assert parsed.content == "done"


def test_parse_structured_claude_cli_rejects_invalid_json():
    from src.orchestrator.claude_cli_tools import ToolResponseParseError
    from src.orchestrator.claude_cli_tools import parse_claude_cli_tool_response

    with pytest.raises(ToolResponseParseError):
        parse_claude_cli_tool_response("plain markdown answer")


def test_tool_protocol_schema_uses_claude_cli_compatible_flat_shape():
    from src.orchestrator.claude_cli_tools import tool_protocol_json_schema

    schema = tool_protocol_json_schema([EchoTool(), CommandTool()])

    assert "oneOf" not in schema
    assert schema["properties"]["type"]["enum"] == ["tool_call", "final"]
    assert schema["properties"]["name"]["enum"] == ["echo", "execute_command"]
    assert schema["required"] == ["type"]


def test_tool_policy_blocks_execute_command_by_default(tmp_path, monkeypatch):
    from src.orchestrator.tool_audit import ToolAuditLogger, ToolPolicy

    monkeypatch.delenv("ATO_AUTO_APPROVE_TOOLS", raising=False)
    policy = ToolPolicy()
    logger = ToolAuditLogger(tmp_path / "tool-audit.jsonl")

    allowed = policy.evaluate("search_code", {"query": "class"})
    blocked = policy.evaluate("execute_command", {"command": "pytest"})
    logger.record(
        task_id="task-1",
        subtask_id="st-1",
        role="tester",
        tool_name="execute_command",
        args={"command": "pytest"},
        decision=blocked.decision,
        status="blocked",
        duration_ms=0,
        error=blocked.reason,
    )

    events = [json.loads(line) for line in (tmp_path / "tool-audit.jsonl").read_text().splitlines()]
    assert allowed.allowed is True
    assert blocked.allowed is False
    assert blocked.decision == "requires_approval"
    assert events[0]["decision"] == "requires_approval"
    assert events[0]["status"] == "blocked"
    assert events[0]["tool_name"] == "execute_command"


def test_tool_policy_auto_approves_restricted_tools_with_env(monkeypatch):
    from src.orchestrator.tool_audit import ToolPolicy

    monkeypatch.setenv("ATO_AUTO_APPROVE_TOOLS", "1")

    result = ToolPolicy().evaluate("execute_command", {"command": "pytest"})

    assert result.allowed is True
    assert result.decision == "auto_approved_env"


def test_claude_cli_structured_loop_executes_tool_then_returns_final(tmp_path, monkeypatch):
    from src.orchestrator.tool_audit import ToolAuditLogger, ToolPolicy
    from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

    orchestrator = ToolEnabledOrchestrator(
        db_path=tmp_path / "checkpoints.db",
        project_root=tmp_path,
        memory_dir=".memory",
        audit_path=tmp_path / "tool-audit.jsonl",
    )
    model = FakeClaudeCliModel(
        [
            '{"type":"tool_call","name":"echo","args":{"value":"abc"}}',
            '{"type":"final","content":"final after echo"}',
        ]
    )

    result = orchestrator._run_claude_cli_tool_loop(
        llm=model,
        system_prompt="system",
        user_prompt="user",
        tools=[EchoTool()],
        state={"task_id": "task-1"},
        subtask={"id": "st-1", "role": "tester"},
        role_name="QA Engineer",
        policy=ToolPolicy(auto_allowed_tools={"echo"}),
        audit_logger=ToolAuditLogger(tmp_path / "tool-audit.jsonl"),
    )

    events = [json.loads(line) for line in (tmp_path / "tool-audit.jsonl").read_text().splitlines()]
    assert result == "final after echo"
    assert len(model.prompts) == 2
    assert events[0]["tool_name"] == "echo"
    assert events[0]["status"] == "completed"
    assert "echo:abc" in str(model.prompts[1])


def test_claude_cli_structured_loop_returns_blocked_for_approval_required_tool(tmp_path):
    from src.orchestrator.tool_audit import ToolAuditLogger, ToolPolicy
    from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

    orchestrator = ToolEnabledOrchestrator(
        db_path=tmp_path / "checkpoints.db",
        project_root=tmp_path,
        memory_dir=".memory",
        audit_path=tmp_path / "tool-audit.jsonl",
    )
    model = FakeClaudeCliModel(
        ['{"type":"tool_call","name":"execute_command","args":{"command":"pytest"}}']
    )

    result = orchestrator._run_claude_cli_tool_loop(
        llm=model,
        system_prompt="system",
        user_prompt="user",
        tools=[CommandTool()],
        state={"task_id": "task-1"},
        subtask={"id": "st-1", "role": "tester"},
        role_name="QA Engineer",
        policy=ToolPolicy(),
        audit_logger=ToolAuditLogger(tmp_path / "tool-audit.jsonl"),
    )

    events = [json.loads(line) for line in (tmp_path / "tool-audit.jsonl").read_text().splitlines()]
    assert result.startswith("Blocked: tool execute_command requires approval")
    assert events[0]["status"] == "blocked"
    assert events[0]["decision"] == "requires_approval"


def test_claude_cli_structured_loop_returns_error_for_unknown_tool(tmp_path):
    from src.orchestrator.tool_audit import ToolAuditLogger, ToolPolicy
    from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

    orchestrator = ToolEnabledOrchestrator(
        db_path=tmp_path / "checkpoints.db",
        project_root=tmp_path,
        memory_dir=".memory",
        audit_path=tmp_path / "tool-audit.jsonl",
    )
    model = FakeClaudeCliModel(['{"type":"tool_call","name":"missing","args":{}}'])

    result = orchestrator._run_claude_cli_tool_loop(
        llm=model,
        system_prompt="system",
        user_prompt="user",
        tools=[EchoTool()],
        state={"task_id": "task-1"},
        subtask={"id": "st-1", "role": "tester"},
        role_name="QA Engineer",
        policy=ToolPolicy(auto_allowed_tools={"echo"}),
        audit_logger=ToolAuditLogger(tmp_path / "tool-audit.jsonl"),
    )

    assert result == "Error: Unknown tool 'missing'"
