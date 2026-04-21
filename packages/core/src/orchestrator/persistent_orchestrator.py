"""LangGraph orchestrator with SQLite checkpointing for persistence."""

from ..models.state import SubtaskDef, TeamState
from .base_orchestrator import BaseGraphOrchestrator


class PersistentGraphOrchestrator(BaseGraphOrchestrator):
    """LangGraph orchestrator with SQLite checkpointing for task persistence.

    Features:
    - SQLite-based checkpoint storage
    - Resume interrupted tasks
    - Parallel execution support

    Inherits all common graph logic from BaseGraphOrchestrator.
    """

    def run(
        self,
        task_id: str,
        subtasks: list[SubtaskDef],
        thread_id: str | None = None,
        resume: bool = True,
    ) -> TeamState:
        """Run the orchestrator with checkpointing.

        Args:
            task_id: Unique task identifier.
            subtasks: List of subtask definitions.
            thread_id: Optional thread ID for checkpointing.
            resume: Whether to resume from existing checkpoint if found.

        Returns:
            Final team state.
        """
        return super().run(task_id, subtasks, thread_id, resume)
