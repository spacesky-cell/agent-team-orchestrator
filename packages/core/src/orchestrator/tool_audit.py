"""Tool execution policy and audit logging."""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ToolDecisionName = Literal["auto_allowed", "auto_approved_env", "requires_approval"]
ToolStatus = Literal["completed", "failed", "blocked"]


@dataclass
class ToolDecision:
    """Decision returned by the tool policy."""

    allowed: bool
    decision: ToolDecisionName
    reason: str | None = None


class ToolPolicy:
    """Minimal non-interactive policy for agent tool execution."""

    def __init__(
        self,
        auto_allowed_tools: set[str] | None = None,
        approval_required_tools: set[str] | None = None,
    ):
        self.auto_allowed_tools = auto_allowed_tools or {
            "read_file",
            "list_directory",
            "search_code",
            "analyze_file",
        }
        self.approval_required_tools = approval_required_tools or {
            "write_file",
            "delete_file",
            "execute_command",
            "run_tests",
            "git_commit",
        }

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> ToolDecision:
        """Return whether a tool call may execute in the current environment."""
        if os.getenv("ATO_AUTO_APPROVE_TOOLS") == "1":
            return ToolDecision(allowed=True, decision="auto_approved_env")

        if tool_name in self.auto_allowed_tools:
            return ToolDecision(allowed=True, decision="auto_allowed")

        reason = f"tool {tool_name} requires approval in non-interactive mode"
        return ToolDecision(allowed=False, decision="requires_approval", reason=reason)


class ToolAuditLogger:
    """Append-only JSONL audit log for tool execution."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        task_id: str,
        subtask_id: str,
        role: str,
        tool_name: str,
        args: dict[str, Any],
        decision: str,
        status: ToolStatus,
        duration_ms: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Record one tool audit event and return the written payload."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "subtask_id": subtask_id,
            "role": role,
            "tool_name": tool_name,
            "args_summary": self._summarize_args(args),
            "decision": decision,
            "status": status,
            "duration_ms": duration_ms,
        }
        if error:
            event["error"] = error

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        return event

    def _summarize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        summary = {}
        for key, value in args.items():
            lowered = key.lower()
            if any(secret in lowered for secret in ("key", "token", "secret", "password")):
                summary[key] = "[redacted]"
            elif isinstance(value, str) and len(value) > 300:
                summary[key] = value[:300] + "...[truncated]"
            else:
                summary[key] = value
        return summary
