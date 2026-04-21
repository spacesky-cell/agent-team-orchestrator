"""Team state definition for LangGraph."""

from typing import Any, Literal, TypedDict


class SubtaskDef(TypedDict):
    """Subtask definition in team state."""

    id: str
    name: str
    role: str
    dependencies: list[str]
    expected_output: str
    status: str  # pending, running, completed, failed


class TeamState(TypedDict):
    """State shared across all nodes in the LangGraph."""

    task_id: str
    subtasks: list[SubtaskDef]
    artifacts: dict[str, Any]  # subtask_id -> output
    messages: list[Any]
    status: Literal["pending", "running", "completed", "failed"]
    current_subtasks: list[str]  # IDs of currently executing subtasks
