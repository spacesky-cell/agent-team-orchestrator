"""Reducer-safe team state definitions for LangGraph."""

from typing import Annotated, Any, Literal, TypedDict


class SubtaskDef(TypedDict):
    """Subtask definition in team state."""

    id: str
    name: str
    role: str
    dependencies: list[str]
    expected_output: str
    status: str  # pending, running, completed, failed


class SubtaskExecutionResult(TypedDict):
    """One branch-local execution delta returned to the coordinator."""

    execution_id: str
    subtask_id: str
    status: Literal["completed", "failed"]
    artifact: Any
    messages: list[Any]


class ExecutionBranch(TypedDict):
    """Immutable input supplied to one parallel executor branch."""

    task_id: str
    subtask: SubtaskDef
    subtasks: list[SubtaskDef]
    artifacts: dict[str, Any]


def merge_execution_results(
    current: list[SubtaskExecutionResult],
    incoming: list[SubtaskExecutionResult],
) -> list[SubtaskExecutionResult]:
    """Merge branch deltas idempotently by execution ID."""
    merged = {item["execution_id"]: item for item in current}
    merged.update({item["execution_id"]: item for item in incoming})
    return list(merged.values())


class TeamState(TypedDict):
    """State shared across all nodes in the LangGraph."""

    task_id: str
    subtasks: list[SubtaskDef]
    artifacts: dict[str, Any]  # subtask_id -> output
    messages: list[Any]
    status: Literal["pending", "running", "completed", "failed"]
    current_subtasks: list[str]  # IDs of currently executing subtasks
    execution_results: Annotated[list[SubtaskExecutionResult], merge_execution_results]
    applied_execution_ids: list[str]
