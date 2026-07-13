"""Tool permission classification and durable approval decisions."""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from .models import ApprovalDecision, ApprovalRequest
from .task_store import TaskStore

READ_ONLY_TOOLS = {"read_file", "list_directory", "search_code", "analyze_file"}
MUTATING_TOOLS = {"write_file", "delete_file", "execute_command", "run_tests", "git_commit"}


class ToolPermission(str, Enum):
    """Runtime permission classification for a tool."""

    AUTO_ALLOW = "auto_allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


ToolDecisionName = Literal["auto_allowed", "auto_approved_env", "requires_approval", "denied"]


@dataclass(frozen=True)
class ToolDecision:
    """Policy result without any user interaction."""

    allowed: bool
    decision: ToolDecisionName
    permission: ToolPermission
    reason: str | None = None


class ToolPolicy:
    """Classify tools without obtaining a user decision."""

    def __init__(
        self,
        auto_allowed_tools: set[str] | None = None,
        approval_required_tools: set[str] | None = None,
    ):
        self.auto_allowed_tools = auto_allowed_tools or set(READ_ONLY_TOOLS)
        self.approval_required_tools = approval_required_tools or set(MUTATING_TOOLS)

    def classify(self, tool_name: str) -> ToolPermission:
        if tool_name in self.auto_allowed_tools:
            return ToolPermission.AUTO_ALLOW
        if tool_name in self.approval_required_tools:
            return ToolPermission.REQUIRE_APPROVAL
        return ToolPermission.DENY

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> ToolDecision:
        """Evaluate static policy and the explicit development-only override."""
        del args
        permission = self.classify(tool_name)
        if os.getenv("ATO_AUTO_APPROVE_TOOLS") == "1":
            return ToolDecision(True, "auto_approved_env", permission)
        if permission is ToolPermission.AUTO_ALLOW:
            return ToolDecision(True, "auto_allowed", permission)
        if permission is ToolPermission.REQUIRE_APPROVAL:
            return ToolDecision(
                False,
                "requires_approval",
                permission,
                f"tool {tool_name} requires approval",
            )
        return ToolDecision(False, "denied", permission, f"tool {tool_name} is not permitted")


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
        *,
        request_key: str | None = None,
    ) -> ApprovalRequest:
        record = self.task_store.read()
        if request_key is not None:
            existing = self._find_request(request_key)
            if existing is not None:
                return existing
        if record.status != "running" or record.active_approval is not None:
            raise ApprovalError("APPROVAL_ALREADY_PENDING", "task cannot accept another request")
        request = ApprovalRequest(
            request_id=(
                f"approval-{uuid5(NAMESPACE_URL, f'{record.task_id}:{request_key}').hex}"
                if request_key is not None
                else f"approval-{uuid4().hex}"
            ),
            request_key=request_key,
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

    def validate_resume(
        self,
        request: ApprovalRequest,
        resume: dict[str, Any],
    ) -> ApprovalDecision:
        """Match a LangGraph resume payload to the durable decision."""
        try:
            request_id = str(resume["request_id"])
            approved = bool(resume["approved"])
        except (KeyError, TypeError) as exc:
            raise ApprovalError(
                "APPROVAL_RESUME_INVALID",
                "invalid approval resume payload",
            ) from exc
        if request_id != request.request_id:
            raise ApprovalError("APPROVAL_NOT_PENDING", f"request is not pending: {request_id}")
        decision = self._find_decision(request_id)
        if decision is None:
            raise ApprovalError("APPROVAL_DECISION_MISSING", "approval decision was not persisted")
        if decision.approved != approved:
            raise ApprovalError("APPROVAL_CONFLICT", "resume payload conflicts with decision")
        return decision

    def _find_request(self, request_key: str) -> ApprovalRequest | None:
        path = self.task_store.paths.approvals
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("type") == "request" and event.get("request_key") == request_key:
                return ApprovalRequest.model_validate(
                    {key: value for key, value in event.items() if key != "type"}
                )
        return None

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
