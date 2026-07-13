"""Tool execution policy and audit logging."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ..runtime.approval import ToolDecision, ToolPolicy

ToolStatus = Literal["requested", "approved", "rejected", "completed", "failed", "blocked"]

__all__ = ["ToolAuditLogger", "ToolDecision", "ToolPolicy", "ToolStatus"]


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
