"""In-process bridge tests used by coverage and adapter contracts."""

import io
import json
from pathlib import Path

import pytest


def test_direct_doctor_roles_status_list_and_audit(tmp_path: Path) -> None:
    from ato_core.bridge.commands import dispatch
    from ato_core.runtime.task_store import TaskStore

    output = tmp_path / "out"
    store = TaskStore.create(output, "task-a", tmp_path)
    store.append_jsonl(store.paths.audit, {"type": "completed"})

    assert dispatch("doctor", {"project_root": str(tmp_path)})["core_module"] == "ato_core"
    assert dispatch("roles-list", {})["roles"]
    assert (
        dispatch("task-status", {"output_root": str(output), "task_id": "task-a"})["status"]
        == "queued"
    )
    assert len(dispatch("task-list", {"output_root": str(output)})["tasks"]) == 1
    assert dispatch("task-audit", {"output_root": str(output), "task_id": "task-a"})["events"] == [
        {"type": "completed"}
    ]


def test_direct_start_run_and_memory_commands(tmp_path: Path, monkeypatch) -> None:
    from ato_core.bridge.commands import dispatch

    monkeypatch.setattr(
        "ato_core.runtime.worker_launcher.WorkerLauncher.start",
        lambda self, task_root, resume=None: 4321,
    )
    started = dispatch(
        "task-start",
        {
            "description": "build it",
            "project_root": str(tmp_path),
            "output_root": str(tmp_path / "out"),
        },
    )
    assert started["status"] == "queued"
    assert started["worker_pid"] == 4321

    monkeypatch.setattr(
        "ato_core.runtime.worker.TaskWorker.run",
        lambda self: self.store.read(),
    )
    foreground = dispatch(
        "task-run",
        {
            "description": "build it",
            "project_root": str(tmp_path),
            "output_root": str(tmp_path / "foreground"),
        },
    )
    assert foreground["status"] == "queued"
    assert (
        "Team Memory Summary"
        in dispatch("memory-summary", {"project_root": str(tmp_path)})["summary"]
    )
    assert "context" in dispatch(
        "memory-query", {"project_root": str(tmp_path), "query": "missing"}
    )


def test_bridge_main_writes_one_envelope(monkeypatch, tmp_path: Path) -> None:
    from ato_core.bridge import __main__ as bridge_main

    class Stdin:
        buffer = io.BytesIO(json.dumps({"project_root": str(tmp_path)}).encode("utf-8"))

    stdout = io.StringIO()
    monkeypatch.setattr(bridge_main.sys, "stdin", Stdin())
    monkeypatch.setattr(bridge_main.sys, "stdout", stdout)

    assert bridge_main.main(["doctor"]) == 0
    assert json.loads(stdout.getvalue())["ok"] is True


def test_bridge_validation_and_unknown_command_errors() -> None:
    from ato_core.bridge.commands import dispatch
    from ato_core.bridge.protocol import BridgeCommandError

    with pytest.raises(BridgeCommandError, match="INVALID_REQUEST"):
        dispatch("task-status", {})
    with pytest.raises(BridgeCommandError, match="UNKNOWN_COMMAND"):
        dispatch("missing", {})
