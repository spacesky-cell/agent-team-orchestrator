"""Background task worker and production orchestration runtime."""

import argparse
import json
import os
from pathlib import Path
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from ato_core.models.state import SubtaskDef

from .decomposition import validate_decomposition
from .models import BridgeError, TaskRecord, TaskStatus, utc_now
from .task_store import TaskStore, TaskStoreError


class WorkerRuntime(Protocol):
    def decompose(self, description: str) -> list[SubtaskDef]: ...

    def execute(
        self,
        store: TaskStore,
        subtasks: list[SubtaskDef],
        resume: dict[str, object] | None = None,
    ) -> dict[str, Any]: ...


class DefaultWorkerRuntime:
    """Connect persisted tasks to the existing decomposition and graph engines."""

    def decompose(self, description: str) -> list[SubtaskDef]:
        from ato_core.models.role import RoleLoader
        from ato_core.orchestrator.simple_orchestrator import SimpleOrchestrator

        decomposition = SimpleOrchestrator().decompose_task(description)
        subtasks = [
            {**item.model_dump(mode="json"), "status": "pending"} for item in decomposition.subtasks
        ]
        return cast(
            list[SubtaskDef],
            validate_decomposition(
                subtasks,
                available_roles=set(RoleLoader().list_roles()),
            ),
        )

    def execute(
        self,
        store: TaskStore,
        subtasks: list[SubtaskDef],
        resume: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        from ato_core.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator

        record = store.read()
        orchestrator = ToolEnabledOrchestrator(
            db_path=store.paths.checkpoints,
            project_root=record.project_root,
            audit_path=store.paths.audit,
            task_store=store,
        )
        graph = orchestrator._get_graph()
        config: RunnableConfig = {"configurable": {"thread_id": record.task_id}}
        graph_input: Any = (
            Command(resume=resume)
            if resume is not None
            else orchestrator.create_initial_state(record.task_id, subtasks)
        )
        return graph.invoke(graph_input, config=config)


class TaskWorker:
    """Own task state transitions around one orchestration execution."""

    def __init__(self, store: TaskStore, runtime: WorkerRuntime | None = None):
        self.store = store
        self.runtime = runtime or DefaultWorkerRuntime()

    def run(self, resume: dict[str, object] | None = None) -> TaskRecord:
        try:
            record = self.store.read()
            self.store.update(heartbeat_at=utc_now(), worker_pid=os.getpid())
            if resume is None:
                if record.status != "queued":
                    raise TaskStoreError("TASK_NOT_RUNNABLE", f"task status is {record.status}")
                self.store.transition("decomposing")
                subtasks = self.runtime.decompose(record.description)
                self.store.write_decomposition(cast(list[dict[str, Any]], subtasks))
                self.store.update(status="running", total_subtasks=len(subtasks))
            else:
                if record.status not in {"running", "blocked"}:
                    raise TaskStoreError("TASK_NOT_RESUMABLE", f"task status is {record.status}")
                subtasks = cast(list[SubtaskDef], self.store.read_decomposition())

            result = self.runtime.execute(self.store, subtasks, resume=resume)
            current = self.store.read()
            if "__interrupt__" in result:
                return self.store.update(heartbeat_at=utc_now(), worker_pid=None)

            graph_status = str(result.get("status", "failed"))
            completed = sum(
                1 for item in result.get("subtasks", []) if item.get("status") == "completed"
            )
            if graph_status == "completed" and completed == 0:
                completed = len(result.get("artifacts", {}))

            if current.status == "blocked":
                terminal = self.store.update(
                    completed_subtasks=completed,
                    heartbeat_at=utc_now(),
                    worker_pid=None,
                )
            else:
                status: TaskStatus = "completed" if graph_status == "completed" else "failed"
                terminal = self.store.update(
                    status=status,
                    completed_subtasks=completed,
                    heartbeat_at=utc_now(),
                    worker_pid=None,
                )
            self.store.write_result(self._result_payload(result, terminal.status))
            return terminal
        except Exception as exc:
            return self._fail(exc)

    def _fail(self, exc: Exception) -> TaskRecord:
        record = self.store.read()
        error = BridgeError(
            code=getattr(exc, "code", "WORKER_FAILED"),
            message=str(exc),
        )
        if record.status in {"completed", "blocked", "failed"}:
            failed = self.store.update(last_error=error, worker_pid=None, heartbeat_at=utc_now())
        else:
            failed = self.store.update(
                status="failed",
                last_error=error,
                worker_pid=None,
                heartbeat_at=utc_now(),
            )
        self.store.write_result(
            {"task_id": failed.task_id, "status": failed.status, "error": error.model_dump()}
        )
        return failed

    def _result_payload(self, result: dict[str, Any], status: str) -> dict[str, Any]:
        record = self.store.read()
        return {
            "task_id": record.task_id,
            "status": status,
            "artifacts": result.get("artifacts", {}),
            "subtasks": result.get("subtasks", []),
        }


def _parse_resume(raw: str | None) -> dict[str, object] | None:
    if raw is None:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("resume payload must be an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument("--resume-json")
    args = parser.parse_args(argv)
    record = TaskWorker(TaskStore.open(args.task_dir)).run(resume=_parse_resume(args.resume_json))
    return 0 if record.status in {"completed", "waiting_approval", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
