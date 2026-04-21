"""Task decomposition and result models."""

from typing import Optional

from pydantic import BaseModel, Field


class Subtask(BaseModel):
    """A subtask within a larger task."""

    id: str = Field(..., description="Unique subtask identifier")
    name: str = Field(..., description="Subtask name")
    role: str = Field(..., description="Role ID to execute this subtask")
    dependencies: list[str] = Field(default_factory=list, description="Dependent subtask IDs")
    expected_output: str = Field(..., description="Description of expected output")


class TaskDecomposition(BaseModel):
    """Result of task decomposition by supervisor agent."""

    task_id: str = Field(..., description="Unique task identifier")
    summary: str = Field(..., description="Task summary")
    subtasks: list[Subtask] = Field(default_factory=list, description="List of subtasks")


class TaskResult(BaseModel):
    """Result of a task execution."""

    task_id: str = Field(..., description="Task identifier")
    status: str = Field(..., description="Status: pending, running, completed, failed")
    current_subtask: Optional[Subtask] = Field(None, description="Currently executing subtask")
    artifacts: dict[str, object] = Field(default_factory=dict, description="Collected outputs")
    error: Optional[str] = Field(None, description="Error message if failed")
