"""Simple sequential orchestrator for MVP."""

import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from rich.console import Console
from rich.panel import Panel

from ..models.llm_provider import LLMConfig, get_llm_provider
from ..models.role import RoleLoader
from ..models.task import Subtask, TaskDecomposition, TaskResult
from ..prompts.task_decompose import TaskDecomposer, TaskDecompositionResult

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Load environment variables
load_dotenv()

console = Console()


class SimpleOrchestrator:
    """Simple sequential orchestrator that executes subtasks in order.

    This is the MVP implementation for demonstration purposes.
    """

    def __init__(self, llm_config: LLMConfig | None = None):
        """Initialize the orchestrator.

        Args:
            llm_config: Optional LLM configuration. If None, uses environment variables.
        """
        self.llm_config = llm_config
        self.llm_provider = get_llm_provider(llm_config)
        self.role_loader = RoleLoader()

    def decompose_task(self, task_description: str) -> TaskDecomposition:
        """Decompose a task into subtasks using the supervisor agent.

        Args:
            task_description: Natural language description of the task.

        Returns:
            TaskDecomposition with task_id, summary, and subtasks.
        """
        console.print(Panel.fit("[bold cyan]Task Decomposition[/bold cyan]", style="cyan"))

        # Get LLM instance
        llm = self.llm_provider.get_llm()

        # Build prompts
        system_prompt = TaskDecomposer.build_system_prompt()
        user_prompt = TaskDecomposer.build_user_prompt(task_description)

        # Create messages
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # Parse output as JSON
        parser = JsonOutputParser(pydantic_object=TaskDecompositionResult)
        messages.append(parser.get_format_instructions())

        # Call LLM
        with console.status("[bold green]Thinking...[/bold green]"):
            response = llm.invoke(messages)
            result = parser.parse(response.content)

        # Convert to TaskDecomposition model
        decomposition = TaskDecomposition(
            task_id=result["task_id"],
            summary=result["summary"],
            subtasks=[Subtask(**st) for st in result["subtasks"]],
        )

        # Display result
        self._display_decomposition(decomposition)

        return decomposition

    def execute_task(self, decomposition: TaskDecomposition, context: str = "") -> TaskResult:
        """Execute all subtasks in the decomposition.

        Args:
            decomposition: Task decomposition from decompose_task.
            context: Additional context to inject into role prompts.

        Returns:
            TaskResult with status, artifacts, and any errors.
        """
        task_id = decomposition.task_id
        artifacts: dict[str, Any] = {}

        console.print()
        console.print(
            Panel.fit(
                f"[bold cyan]Executing Task:[/] {decomposition.summary}",
                style="cyan",
            )
        )

        try:
            for idx, subtask in enumerate(decomposition.subtasks, 1):
                console.print()
                console.print(
                    f"[bold]Subtask {idx}/{len(decomposition.subtasks)}:[/] "
                    f"[cyan]{subtask.name}[/] "
                    f"([yellow]{subtask.role}[/])"
                )

                # Check dependencies
                if subtask.dependencies:
                    console.print(f"  [dim]Dependencies:[/] {', '.join(subtask.dependencies)}")

                # Execute subtask
                output = self._execute_subtask(subtask, artifacts, context)
                artifacts[subtask.id] = output

                # Display snippet
                snippet = str(output)[:200] + "..." if len(str(output)) > 200 else str(output)
                console.print(f"  [dim]Output preview:[/] [green]{snippet}[/]")

            console.print()
            console.print("[bold green]✓[/] Task completed successfully!")

            return TaskResult(
                task_id=task_id,
                status="completed",
                artifacts=artifacts,
            )

        except Exception as e:
            console.print()
            console.print(f"[bold red]✗[/] Task failed: {e}")

            return TaskResult(
                task_id=task_id,
                status="failed",
                artifacts=artifacts,
                error=str(e),
            )

    def _execute_subtask(
        self, subtask: Subtask, artifacts: dict[str, Any], context: str
    ) -> Any:
        """Execute a single subtask.

        Args:
            subtask: Subtask to execute.
            artifacts: Dictionary of previous outputs (for dependency resolution).
            context: Additional context string.

        Returns:
            Output from the agent.
        """
        # Load role definition
        role = self.role_loader.load(subtask.role)

        # Get LLM instance (with role-specific preferences if any)
        llm = self.llm_provider.get_llm()

        # Build context from artifacts
        artifact_context = self._build_context_from_artifacts(subtask, artifacts)

        # Render system prompt with context
        full_context = f"{context}\n\n{artifact_context}" if artifact_context else context
        system_prompt = role.render_prompt(full_context)

        # Build user prompt
        user_prompt = f"""## Your Task

{subtask.expected_output}

Please provide your output in the format specified in the deliverables.
"""

        # Call LLM
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        with console.status("  [dim]Agent working...[/dim]"):
            response = llm.invoke(messages)

        return response.content

    def _build_context_from_artifacts(self, subtask: Subtask, artifacts: dict[str, Any]) -> str:
        """Build context string from dependent artifacts.

        Args:
            subtask: Current subtask.
            artifacts: All previous artifacts.

        Returns:
            Formatted context string.
        """
        if not subtask.dependencies:
            return ""

        lines = ["## Previous Work Outputs\n"]

        for dep_id in subtask.dependencies:
            if dep_id in artifacts:
                lines.append(f"\n### From {dep_id}")
                lines.append(f"```\n{artifacts[dep_id]}\n```")
            else:
                lines.append(f"\n### From {dep_id}")
                lines.append(f"[Output not found - this may be an error]")

        return "\n".join(lines)

    def _display_decomposition(self, decomposition: TaskDecomposition) -> None:
        """Display task decomposition to console.

        Args:
            decomposition: Task decomposition to display.
        """
        console.print()
        console.print(f"[bold]Task ID:[/] {decomposition.task_id}")
        console.print(f"[bold]Summary:[/] {decomposition.summary}")
        console.print()
        console.print(f"[bold]Subtasks ({len(decomposition.subtasks)}):[/]")

        for idx, subtask in enumerate(decomposition.subtasks, 1):
            deps = f" → {', '.join(subtask.dependencies)}" if subtask.dependencies else ""
            console.print(
                f"  {idx}. [cyan]{subtask.name}[/] ([yellow]{subtask.role}[/]){deps}"
            )

    def save_artifacts(self, artifacts: dict[str, Any], output_dir: Path | str) -> None:
        """Save task artifacts to disk.

        Args:
            artifacts: Dictionary of artifacts to save.
            output_dir: Directory to save to.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for subtask_id, content in artifacts.items():
            file_path = output_path / f"{subtask_id}.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(content))

        console.print()
        console.print(f"[bold]Artifacts saved to:[/] [cyan]{output_path.absolute()}[/]")
