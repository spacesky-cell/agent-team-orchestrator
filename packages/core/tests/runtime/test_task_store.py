"""Task-scoped persistence tests."""

from pathlib import Path

import pytest


def test_tasks_use_isolated_directories(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore

    first = TaskStore.create(tmp_path, "task-a", tmp_path)
    second = TaskStore.create(tmp_path, "task-b", tmp_path)

    assert first.paths.root != second.paths.root
    assert first.paths.state == tmp_path / "tasks" / "task-a" / "task.json"
    assert second.paths.audit == tmp_path / "tasks" / "task-b" / "tool-audit.jsonl"
    assert first.read().status == "queued"
    assert second.read().status == "queued"


def test_corrupt_state_is_not_reported_as_empty(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore, TaskStoreError

    store = TaskStore.create(tmp_path, "task-a", tmp_path)
    store.paths.state.write_text("{broken", encoding="utf-8")

    with pytest.raises(TaskStoreError, match="TASK_STATE_CORRUPT"):
        store.read()


def test_state_updates_are_atomic_and_leave_no_temp_files(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore

    store = TaskStore.create(tmp_path, "task-a", tmp_path)
    updated = store.transition("decomposing")

    assert updated.status == "decomposing"
    assert store.read().status == "decomposing"
    assert list(store.paths.root.glob("*.tmp")) == []


def test_invalid_state_transition_is_rejected(tmp_path: Path) -> None:
    from ato_core.runtime.task_store import TaskStore, TaskStoreError

    store = TaskStore.create(tmp_path, "task-a", tmp_path)

    with pytest.raises(TaskStoreError, match="INVALID_TASK_TRANSITION"):
        store.transition("completed")
