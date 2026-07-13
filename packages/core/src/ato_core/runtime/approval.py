"""Tool permission classification and durable approval decisions."""

import json
from enum import Enum
from typing import Any
from uuid import uuid4

from .models import ApprovalDecision, ApprovalRequest
from .task_store import TaskStore

READ_ONLY_TOOLS = {"read_file", "list_directory", "search_code", "analyze_file"}
MUTATING_TOOLS = {"write_file", "delete_file", "execute_command", "run_tests", "git_commit"}


class ToolPermission(str, Enum):
    """Runtime permission classification for a tool."""

    AUTO_ALLOW = "auto_allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ToolPolicy:
    """Classify tools without obtaining a user decision."""

    def classify(self, tool_name: str) -> ToolPermission:
        if tool_name in READ_ONLY_TOOLS:
            return ToolPermission.AUTO_ALLOW
        if tool_name in MUTATING_TOOLS:
            return ToolPermission.REQUIRE_APPROVAL
        return ToolPermission.DENY


class ApprovalError(RuntimeError):
    """An approval request is missing, stale, or inconsistent."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def summarize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Redact secrets and bound long values before persistence."""
    summary: dict[str, Any] = {}
    for key, value in args.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("key", "token", "secret", "password")):
            summary[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > 300:
            summary[key] = value[:300] + "...[truncated]"
        else:
            summary[key] = value
    return summary


class ApprovalStore:
    """Persist approval requests and decisions for one task."""

    def __init__(self, task_store: TaskStore):
        self.task_store = task_store

    def request(
        self,
        subtask_id: str,
        tool_name: str,
        args: dict[str, Any],
    ) -> ApprovalRequest:
        record = self.task_store.read()
        if record.status != "running" or record.active_approval is not None:
            raise ApprovalError("APPROVAL_ALREADY_PENDING", "task cannot accept another request")
        request = ApprovalRequest(
            request_id=f"approval-{uuid4().hex}",
            task_id=record.task_id,
            subtask_id=subtask_id,
            tool_name=tool_name,
            args_summary=summarize_args(args),
        )
        self.task_store.append_jsonl(
            self.task_store.paths.approvals,
            {"type": "request", **request.model_dump(mode="json")},
        )
        self.task_store.update(status="waiting_approval", active_approval=request)
        return request

    def decide(self, request_id: str, *, approved: bool) -> ApprovalDecision:
        existing = self._find_decision(request_id)
        if existing is not None:
            if existing.approved != approved:
                raise ApprovalError("APPROVAL_CONFLICT", "request already has another decision")
            return existing

        record = self.task_store.read()
        request = record.active_approval
        if (
            record.status != "waiting_approval"
            or request is None
            or request.request_id != request_id
        ):
            raise ApprovalError("APPROVAL_NOT_PENDING", f"request is not pending: {request_id}")

        decision = ApprovalDecision(request_id=request_id, approved=approved)
        self.task_store.append_jsonl(
            self.task_store.paths.approvals,
            {"type": "decision", **decision.model_dump(mode="json")},
        )
        self.task_store.update(
            status="running" if approved else "blocked",
            active_approval=None,
        )
        return decision

    def _find_decision(self, request_id: str) -> ApprovalDecision | None:
        path = self.task_store.paths.approvals
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("type") == "decision" and event.get("request_id") == request_id:
                return ApprovalDecision.model_validate(
                    {key: value for key, value in event.items() if key != "type"}
                )
        return None
