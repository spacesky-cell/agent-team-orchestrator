"""Durable approval policy and decision tests."""

from pathlib import Path

import pytest


def running_store(tmp_path: Path):
    from ato_core.runtime.task_store import TaskStore

    store = TaskStore.create(tmp_path, "task-a", tmp_path)
    store.transition("decomposing")
    store.transition("running")
    return store


def test_policy_separates_classification_from_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from ato_core.runtime.approval import ToolPermission, ToolPolicy

    monkeypatch.delenv("ATO_AUTO_APPROVE_TOOLS", raising=False)
    policy = ToolPolicy()

    assert policy.classify("read_file") is ToolPermission.AUTO_ALLOW
    assert policy.classify("write_file") is ToolPermission.REQUIRE_APPROVAL
    assert policy.classify("unknown_tool") is ToolPermission.DENY


def test_request_and_approval_are_persisted(tmp_path: Path) -> None:
    from ato_core.runtime.approval import ApprovalStore

    store = running_store(tmp_path)
    approvals = ApprovalStore(store)
    request = approvals.request("subtask-a", "write_file", {"path": "a.txt", "content": "x"})

    waiting = store.read()
    assert waiting.status == "waiting_approval"
    assert waiting.active_approval == request

    decision = approvals.decide(request.request_id, approved=True)

    resumed = store.read()
    assert decision.approved is True
    assert resumed.status == "running"
    assert resumed.active_approval is None
    assert request.request_id in store.paths.approvals.read_text(encoding="utf-8")


def test_rejection_blocks_task_and_duplicate_decision_is_idempotent(tmp_path: Path) -> None:
    from ato_core.runtime.approval import ApprovalStore

    store = running_store(tmp_path)
    approvals = ApprovalStore(store)
    request = approvals.request("subtask-a", "execute_command", {"command": "echo ok"})

    first = approvals.decide(request.request_id, approved=False)
    second = approvals.decide(request.request_id, approved=False)

    assert first == second
    assert store.read().status == "blocked"


def test_stale_request_id_is_rejected(tmp_path: Path) -> None:
    from ato_core.runtime.approval import ApprovalError, ApprovalStore

    approvals = ApprovalStore(running_store(tmp_path))
    approvals.request("subtask-a", "write_file", {"path": "a.txt"})

    with pytest.raises(ApprovalError, match="APPROVAL_NOT_PENDING"):
        approvals.decide("stale-request", approved=True)


def test_sensitive_arguments_are_redacted(tmp_path: Path) -> None:
    from ato_core.runtime.approval import ApprovalStore

    approvals = ApprovalStore(running_store(tmp_path))
    request = approvals.request(
        "subtask-a",
        "execute_command",
        {"api_token": "secret", "command": "echo ok"},
    )

    assert request.args_summary == {"api_token": "[redacted]", "command": "echo ok"}
