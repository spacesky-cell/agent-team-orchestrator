"""Application service for task lifecycle operations."""

from datetime import timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .approval import ApprovalStore
from .models import BridgeError, TaskRecord, utc_now
from .task_store import TaskStore
from .worker_launcher import WorkerLauncher, is_process_alive

HEARTBEAT_TIMEOUT = timedelta(seconds=30)


class Launcher(Protocol):
    def start(self, task_root: Path, resume: dict[str, object] | None = None) -> int: ...


class TaskService:
    """Own task creation and worker startup semantics."""

    def __init__(self, output_root: Path, launcher: Launcher | None = None):
        self.output_root = output_root.resolve()
        self.launcher = launcher or WorkerLauncher()

    def start(self, description: str, project_root: Path) -> TaskRecord:
        task_id = f"task-{uuid4().hex}"
        store = TaskStore.create(
            self.output_root,
            task_id,
            project_root,
            description=description,
        )
        try:
            pid = self.launcher.start(store.paths.root, None)
        except Exception as exc:
            return store.update(
                status="failed",
                last_error=BridgeError(
                    code="WORKER_START_FAILED",
                    message=str(exc),
                ),
            )
        return store.update(worker_pid=pid)

    def approve(self, task_id: str, request_id: str, approved: bool) -> TaskRecord:
        store = TaskStore.open(self.output_root / "tasks" / task_id)
        decision = ApprovalStore(store).decide(request_id, approved=approved)
        resume: dict[str, object] = {
            "request_id": decision.request_id,
            "approved": decision.approved,
        }
        try:
            pid = self.launcher.start(store.paths.root, resume)
        except Exception as exc:
            record = store.read()
            error = BridgeError(code="WORKER_START_FAILED", message=str(exc))
            if record.status in {"running", "waiting_approval"}:
                return store.update(status="failed", last_error=error, worker_pid=None)
            return store.update(last_error=error, worker_pid=None)
        return store.update(worker_pid=pid)

    def status(self, task_id: str) -> TaskRecord:
        store = TaskStore.open(self.output_root / "tasks" / task_id)
        record = store.read()
        heartbeat = record.heartbeat_at or record.updated_at
        is_stale = utc_now() - heartbeat > HEARTBEAT_TIMEOUT
        if (
            record.status in {"queued", "decomposing", "running"}
            and record.worker_pid is not None
            and is_stale
            and not is_process_alive(record.worker_pid)
        ):
            return store.update(
                status="failed",
                worker_pid=None,
                last_error=BridgeError(
                    code="WORKER_LOST",
                    message="worker heartbeat is stale and the process is not running",
                ),
            )
        return record
