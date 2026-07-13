"""Validate committed documentation examples against runtime models."""

import json
from pathlib import Path

from ato_core.runtime.models import TaskRecord


def test_demo_task_and_audit_are_valid_and_redacted() -> None:
    root = Path(__file__).parents[3]
    task = TaskRecord.model_validate_json(
        (root / "docs" / "demo" / "task.json").read_text(encoding="utf-8")
    )
    events = [
        json.loads(line)
        for line in (root / "docs" / "demo" / "tool-audit.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert task.status == "completed"
    assert task.completed_subtasks == task.total_subtasks == 2
    assert {event["status"] for event in events} >= {"requested", "approved", "completed"}
    assert not any("token" in json.dumps(event).lower() for event in events)
