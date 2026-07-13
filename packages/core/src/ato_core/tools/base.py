"""Base tool interface for Agent Team Orchestrator."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict


@dataclass(frozen=True)
class ToolExecutionContext:
    """Immutable task and filesystem boundary supplied by the runtime."""

    task_id: str
    subtask_id: str
    project_root: Path
    allowed_dirs: tuple[Path, ...]


class BaseTool(ABC):
    """Abstract base class for all tools.

    All tools must inherit from this class and implement the execute method.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[Dict[str, Any]]  # JSON Schema format

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given arguments.

        Args:
            ****kwargs**: Tool arguments as defined in parameters schema.

        Returns:
            Tool output as string.
        """
        pass

    def _validate_args(self, **kwargs: Any) -> None:
        """Validate arguments against parameters schema.

        Override this method for custom validation logic.

        Args:
            **kwargs: Arguments to validate.

        Raises:
            ValueError: If arguments are invalid.
        """
        pass
