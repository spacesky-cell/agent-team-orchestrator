"""Stable Python bridge command tests."""

import json
import os
import subprocess
import sys
from pathlib import Path


def invoke_bridge(
    command: str,
    payload: dict[str, object],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    return subprocess.run(
        [sys.executable, "-m", "ato_core.bridge", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=20,
    )


def test_doctor_returns_one_success_envelope(tmp_path: Path) -> None:
    result = invoke_bridge("doctor", {"project_root": str(tmp_path)}, tmp_path)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["core_module"] == "ato_core"
    assert "architect" in payload["data"]["roles"]
    assert result.stdout.count("\n") <= 1


def test_unknown_command_returns_structured_failure(tmp_path: Path) -> None:
    result = invoke_bridge("missing-command", {}, tmp_path)

    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "code": "UNKNOWN_COMMAND",
        "message": "Unknown bridge command: missing-command",
        "details": {},
    }


def test_invalid_json_never_writes_traceback_to_stdout(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "ato_core.bridge", "doctor"],
        input="{broken",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=20,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["code"] == "INVALID_REQUEST"
    assert "Traceback" not in result.stdout


def test_bridge_accepts_utf8_bom_from_windows_stdin(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        "PYTHONUTF8": "1",
    }
    result = subprocess.run(
        [sys.executable, "-m", "ato_core.bridge", "doctor"],
        input=b"\xef\xbb\xbf{}",
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=20,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout.decode("utf-8"))["ok"] is True


def test_task_status_is_scoped_by_task_id(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore

    TaskStore.create(tmp_path, "task-a", tmp_path)
    TaskStore.create(tmp_path, "task-b", tmp_path)

    result = invoke_bridge(
        "task-status",
        {"output_root": str(tmp_path), "task_id": "task-b"},
        tmp_path,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["task_id"] == "task-b"
    assert payload["data"]["output_dir"].endswith("tasks/task-b") or payload["data"][
        "output_dir"
    ].endswith("tasks\\task-b")


def test_task_start_returns_persisted_task_immediately(tmp_path: Path) -> None:
    result = invoke_bridge(
        "task-start",
        {
            "description": "build a feature",
            "project_root": str(tmp_path),
            "output_root": str(tmp_path / "output"),
        },
        tmp_path,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "queued"
    assert payload["data"]["description"] == "build a feature"
    assert Path(payload["data"]["output_dir"], "task.json").is_file()


def test_task_list_and_audit_are_task_scoped(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore

    output = tmp_path / "output"
    first = TaskStore.create(output, "task-a", tmp_path)
    TaskStore.create(output, "task-b", tmp_path)
    first.append_jsonl(first.paths.audit, {"type": "completed", "tool_name": "read_file"})

    listed = invoke_bridge("task-list", {"output_root": str(output)}, tmp_path)
    audited = invoke_bridge(
        "task-audit",
        {"output_root": str(output), "task_id": "task-a"},
        tmp_path,
    )

    assert [item["task_id"] for item in json.loads(listed.stdout)["data"]["tasks"]] == [
        "task-a",
        "task-b",
    ]
    assert json.loads(audited.stdout)["data"]["events"] == [
        {"type": "completed", "tool_name": "read_file"}
    ]


def test_task_approve_restarts_worker_with_exact_decision(tmp_path: Path, monkeypatch) -> None:
    from ato_core.runtime.approval import ApprovalStore
    from ato_core.runtime.task_store import TaskStore

    output = tmp_path / "output"
    store = TaskStore.create(output, "task-a", tmp_path)
    store.transition("decomposing")
    store.transition("running")
    request = ApprovalStore(store).request("a", "write_file", {"path": "a.txt"})
    captured: dict[str, object] = {}

    def fake_start(self, task_root, resume=None):
        captured["task_root"] = task_root
        captured["resume"] = resume
        return 4444

    monkeypatch.setattr("ato_core.runtime.worker_launcher.WorkerLauncher.start", fake_start)
    from ato_core.bridge.commands import task_approve

    payload = task_approve(
        {
            "output_root": str(output),
            "task_id": "task-a",
            "request_id": request.request_id,
            "approved": True,
        }
    )

    assert payload["worker_pid"] == 4444
    assert captured["task_root"] == store.paths.root
    assert captured["resume"] == {
        "request_id": request.request_id,
        "approved": True,
    }
