"""Typed one-shot bridge command handlers."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ato_core import __version__
from ato_core.models.role import RoleLoader
from ato_core.runtime.approval import ApprovalError
from ato_core.runtime.task_service import TaskService
from ato_core.runtime.task_store import TaskStore, TaskStoreError
from ato_core.runtime.worker import TaskWorker

from .protocol import BridgeCommandError


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectRequest(Request):
    project_root: Path = Path(".")


class OutputRequest(Request):
    output_root: Path


class TaskRequest(OutputRequest):
    task_id: str


class StartRequest(ProjectRequest):
    description: str = Field(min_length=1)
    output_root: Path | None = None


class ApproveRequest(TaskRequest):
    request_id: str
    approved: bool


class MemoryRequest(ProjectRequest):
    storage_dir: str = ".ato/memory"


class MemoryQueryRequest(MemoryRequest):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)


RequestT = TypeVar("RequestT", bound=Request)


def _request(model: type[RequestT], payload: dict[str, Any]) -> RequestT:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise BridgeCommandError(
            "INVALID_REQUEST",
            "Request validation failed",
            {"errors": exc.errors(include_url=False)},
        ) from exc


def _store(request: TaskRequest) -> TaskStore:
    return TaskStore.open(request.output_root.resolve() / "tasks" / request.task_id)


def _map_domain_error(exc: Exception) -> BridgeCommandError:
    return BridgeCommandError(getattr(exc, "code", "INTERNAL_ERROR"), str(exc))


def doctor(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(ProjectRequest, payload)
    project_root = request.project_root.resolve()
    return {
        "core_module": "ato_core",
        "core_version": __version__,
        "python": sys.executable,
        "project_root": str(project_root),
        "roles": RoleLoader().list_roles(),
        "llm_provider": os.getenv("LLM_PROVIDER", "claude-cli"),
        "claude_cli": shutil.which("claude") or "UNAVAILABLE",
        "auto_approve_tools": os.getenv("ATO_AUTO_APPROVE_TOOLS") == "1",
    }


def roles_list(payload: dict[str, Any]) -> dict[str, Any]:
    _request(Request, payload)
    loader = RoleLoader()
    return {
        "roles": [loader.load(role_id).model_dump(mode="json") for role_id in loader.list_roles()]
    }


def task_status(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(TaskRequest, payload)
    try:
        return TaskService(request.output_root).status(request.task_id).model_dump(mode="json")
    except TaskStoreError as exc:
        raise _map_domain_error(exc) from exc


def task_start(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(StartRequest, payload)
    project_root = request.project_root.resolve()
    output_root = (request.output_root or project_root / "ato-output").resolve()
    record = TaskService(output_root=output_root).start(request.description.strip(), project_root)
    if record.status == "failed" and record.last_error is not None:
        raise BridgeCommandError(
            record.last_error.code,
            record.last_error.message,
            record.last_error.details,
        )
    return record.model_dump(mode="json")


def task_run(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(StartRequest, payload)
    project_root = request.project_root.resolve()
    output_root = (request.output_root or project_root / "ato-output").resolve()
    service = TaskService(output_root=output_root)
    task_id = f"task-{__import__('uuid').uuid4().hex}"
    store = TaskStore.create(
        output_root,
        task_id,
        project_root,
        description=request.description.strip(),
    )
    del service
    return TaskWorker(store).run().model_dump(mode="json")


def task_approve(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(ApproveRequest, payload)
    try:
        record = TaskService(request.output_root).approve(
            request.task_id,
            request.request_id,
            request.approved,
        )
        return record.model_dump(mode="json")
    except (ApprovalError, TaskStoreError) as exc:
        raise _map_domain_error(exc) from exc


def task_audit(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(TaskRequest, payload)
    try:
        store = _store(request)
        store.read()
        events = []
        if store.paths.audit.is_file():
            events = [
                json.loads(line)
                for line in store.paths.audit.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return {"task_id": request.task_id, "events": events}
    except (OSError, ValueError, TaskStoreError) as exc:
        raise _map_domain_error(exc) from exc


def task_list(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(OutputRequest, payload)
    tasks_root = request.output_root.resolve() / "tasks"
    tasks = []
    if tasks_root.is_dir():
        for task_root in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
            try:
                tasks.append(TaskStore.open(task_root).read().model_dump(mode="json"))
            except TaskStoreError as exc:
                raise _map_domain_error(exc) from exc
    return {"tasks": tasks}


def memory_query(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(MemoryQueryRequest, payload)
    from ato_core.memory.team_memory import TeamMemory

    memory = TeamMemory(
        project_root=request.project_root.resolve(),
        storage_dir=request.storage_dir,
    )
    return {"context": memory.retrieve_relevant_context(request.query, top_k=request.top_k)}


def memory_summary(payload: dict[str, Any]) -> dict[str, Any]:
    request = _request(MemoryRequest, payload)
    from ato_core.memory.team_memory import TeamMemory

    memory = TeamMemory(
        project_root=request.project_root.resolve(),
        storage_dir=request.storage_dir,
    )
    return {"summary": memory.summary()}


COMMANDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "doctor": doctor,
    "roles-list": roles_list,
    "task-start": task_start,
    "task-run": task_run,
    "task-status": task_status,
    "task-approve": task_approve,
    "task-audit": task_audit,
    "task-list": task_list,
    "memory-query": memory_query,
    "memory-summary": memory_summary,
}


def dispatch(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    handler = COMMANDS.get(command)
    if handler is None:
        raise BridgeCommandError("UNKNOWN_COMMAND", f"Unknown bridge command: {command}")
    return handler(payload)
