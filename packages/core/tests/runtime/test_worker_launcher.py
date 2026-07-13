"""Background task process boundary tests."""

from pathlib import Path


class FakeLauncher:
    def __init__(self, pid: int = 4321, error: Exception | None = None):
        self.pid = pid
        self.error = error
        self.started: list[Path] = []

    def start(self, task_root: Path, resume: dict[str, object] | None = None) -> int:
        self.started.append((task_root, resume))
        if self.error is not None:
            raise self.error
        return self.pid


def test_task_service_persists_task_before_worker_start(tmp_path: Path) -> None:
    from ato_core.runtime.task_service import TaskService

    launcher = FakeLauncher()
    service = TaskService(output_root=tmp_path, launcher=launcher)

    record = service.start("build a feature", tmp_path)

    assert record.status == "queued"
    assert record.worker_pid == 4321
    assert record.description == "build a feature"
    assert launcher.started == [(record.output_dir, None)]
    assert (record.output_dir / "task.json").is_file()


def test_worker_start_failure_is_persisted(tmp_path: Path) -> None:
    from ato_core.runtime.task_service import TaskService

    service = TaskService(output_root=tmp_path, launcher=FakeLauncher(error=OSError("no process")))

    record = service.start("build a feature", tmp_path)

    assert record.status == "failed"
    assert record.last_error is not None
    assert record.last_error.code == "WORKER_START_FAILED"


def test_worker_launcher_uses_argument_list_without_shell(monkeypatch, tmp_path: Path) -> None:
    from ato_core.runtime.worker_launcher import WorkerLauncher

    captured: dict[str, object] = {}

    class Process:
        pid = 9876

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr("ato_core.runtime.worker_launcher.subprocess.Popen", fake_popen)

    pid = WorkerLauncher().start(tmp_path)

    assert pid == 9876
    assert captured["args"][1:3] == ["-m", "ato_core.runtime.worker"]
    assert captured["kwargs"]["shell"] is False


def test_worker_launcher_passes_resume_as_json_argument(monkeypatch, tmp_path: Path) -> None:
    from ato_core.runtime.worker_launcher import WorkerLauncher

    captured: dict[str, object] = {}

    class Process:
        pid = 9876

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr("ato_core.runtime.worker_launcher.subprocess.Popen", fake_popen)
    WorkerLauncher().start(tmp_path, {"request_id": "approval-1", "approved": True})

    args = captured["args"]
    assert isinstance(args, list)
    assert args[-2] == "--resume-json"
    assert '"request_id":"approval-1"' in args[-1]


class FakeRuntime:
    def __init__(self, result: dict[str, object]):
        self.result = result
        self.status_during_execute: str | None = None
        self.resume: dict[str, object] | None = None

    def decompose(self, description: str) -> list[dict[str, object]]:
        assert description == "build a feature"
        return [
            {
                "id": "a",
                "name": "a",
                "role": "architect",
                "dependencies": [],
                "expected_output": "result",
                "status": "pending",
            }
        ]

    def execute(self, store, subtasks, resume=None):
        self.status_during_execute = store.read().status
        self.resume = resume
        assert len(subtasks) == 1
        return self.result


def test_worker_executes_task_and_persists_terminal_result(tmp_path: Path) -> None:
    import json

    from ato_core.runtime.task_store import TaskStore
    from ato_core.runtime.worker import TaskWorker

    store = TaskStore.create(tmp_path, "task-a", tmp_path, description="build a feature")
    runtime = FakeRuntime({"status": "completed", "artifacts": {"a": "done"}, "subtasks": []})

    record = TaskWorker(store, runtime=runtime).run()

    assert runtime.status_during_execute == "running"
    assert record.status == "completed"
    assert record.completed_subtasks == 1
    assert record.total_subtasks == 1
    assert record.worker_pid is None
    assert json.loads(store.paths.result.read_text(encoding="utf-8"))["artifacts"] == {"a": "done"}


def test_worker_resumes_approval_without_redecomposing(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore
    from ato_core.runtime.worker import TaskWorker

    store = TaskStore.create(tmp_path, "task-a", tmp_path, description="build a feature")
    store.transition("decomposing")
    store.update(status="running", total_subtasks=1)
    store.write_decomposition(
        [
            {
                "id": "a",
                "name": "a",
                "role": "architect",
                "dependencies": [],
                "expected_output": "result",
                "status": "pending",
            }
        ]
    )
    runtime = FakeRuntime({"status": "completed", "artifacts": {"a": "done"}})
    resume = {"request_id": "approval-1", "approved": True}

    record = TaskWorker(store, runtime=runtime).run(resume=resume)

    assert runtime.resume == resume
    assert record.status == "completed"


def test_status_marks_stale_dead_worker_failed(tmp_path: Path, monkeypatch) -> None:
    from datetime import timedelta

    from ato_core.runtime.models import utc_now
    from ato_core.runtime.task_service import TaskService
    from ato_core.runtime.task_store import TaskStore

    store = TaskStore.create(tmp_path, "task-a", tmp_path)
    store.transition("decomposing")
    store.update(
        status="running",
        worker_pid=999999,
        heartbeat_at=utc_now() - timedelta(minutes=2),
    )
    monkeypatch.setattr("ato_core.runtime.task_service.is_process_alive", lambda pid: False)

    record = TaskService(tmp_path).status("task-a")

    assert record.status == "failed"
    assert record.last_error is not None
    assert record.last_error.code == "WORKER_LOST"
