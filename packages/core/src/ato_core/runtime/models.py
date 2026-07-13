"""Persistent task runtime models."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal[
    "queued",
    "decomposing",
    "running",
    "waiting_approval",
    "completed",
    "blocked",
    "failed",
]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


class BridgeError(BaseModel):
    """A stable user-safe task error."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """A durable tool approval request."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    task_id: str
    subtask_id: str
    tool_name: str
    args_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalDecision(BaseModel):
    """A durable response to one approval request."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    approved: bool
    decided_at: datetime = Field(default_factory=utc_now)


class TaskRecord(BaseModel):
    """Current persisted summary for one task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: TaskStatus
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    project_root: Path
    output_dir: Path
    completed_subtasks: int = 0
    total_subtasks: int = 0
    active_approval: ApprovalRequest | None = None
    last_error: BridgeError | None = None
    worker_pid: int | None = None
    heartbeat_at: datetime | None = None
