"""Task-scoped persistence with atomic state updates."""

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from .models import TaskRecord, TaskStatus, utc_now

_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    "queued": {"decomposing", "failed"},
    "decomposing": {"running", "failed"},
    "running": {"waiting_approval", "completed", "blocked", "failed"},
    "waiting_approval": {"running", "blocked", "failed"},
    "completed": set(),
    "blocked": set(),
    "failed": set(),
}


class TaskStoreError(RuntimeError):
    """Persistent task state could not be read or updated safely."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class TaskPaths:
    """All durable files owned by one task."""

    root: Path
    state: Path
    result: Path
    checkpoints: Path
    approvals: Path
    audit: Path


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class TaskStore:
    """Read and update one task directory."""

    def __init__(self, paths: TaskPaths):
        self.paths = paths
        self._append_lock = threading.Lock()

    @classmethod
    def create(cls, output_root: Path, task_id: str, project_root: Path) -> "TaskStore":
        root = output_root.resolve() / "tasks" / task_id
        paths = TaskPaths(
            root=root,
            state=root / "task.json",
            result=root / "result.json",
            checkpoints=root / "checkpoints.db",
            approvals=root / "approvals.jsonl",
            audit=root / "tool-audit.jsonl",
        )
        store = cls(paths)
        if paths.state.exists():
            raise TaskStoreError("TASK_ALREADY_EXISTS", f"task already exists: {task_id}")
        record = TaskRecord(
            task_id=task_id,
            status="queued",
            project_root=project_root.resolve(),
            output_dir=root,
        )
        store.write(record)
        return store

    @classmethod
    def open(cls, task_root: Path) -> "TaskStore":
        root = task_root.resolve()
        return cls(
            TaskPaths(
                root=root,
                state=root / "task.json",
                result=root / "result.json",
                checkpoints=root / "checkpoints.db",
                approvals=root / "approvals.jsonl",
                audit=root / "tool-audit.jsonl",
            )
        )

    def read(self) -> TaskRecord:
        if not self.paths.state.is_file():
            raise TaskStoreError("TASK_NOT_FOUND", f"missing state: {self.paths.state}")
        try:
            return TaskRecord.model_validate_json(self.paths.state.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise TaskStoreError("TASK_STATE_CORRUPT", str(exc)) from exc

    def write(self, record: TaskRecord) -> None:
        _write_json_atomic(self.paths.state, record.model_dump(mode="json"))

    def transition(self, status: TaskStatus) -> TaskRecord:
        return self.update(status=status)

    def update(self, *, status: TaskStatus | None = None, **changes: Any) -> TaskRecord:
        """Atomically update task fields and optionally validate a status transition."""
        record = self.read()
        if status is not None and status not in _TRANSITIONS[record.status]:
            raise TaskStoreError(
                "INVALID_TASK_TRANSITION",
                f"cannot transition {record.status} -> {status}",
            )
        updates = {**changes, "updated_at": utc_now()}
        if status is not None:
            updates["status"] = status
        updated = record.model_copy(update=updates)
        self.write(updated)
        return updated

    def write_result(self, payload: dict[str, Any]) -> None:
        record = self.read()
        if record.status not in {"completed", "blocked", "failed"}:
            raise TaskStoreError("TASK_NOT_TERMINAL", f"task status is {record.status}")
        _write_json_atomic(self.paths.result, payload)

    def append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._append_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line)
