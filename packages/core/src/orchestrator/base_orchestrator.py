"""Base class for LangGraph orchestrators with common functionality."""

import copy
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send
from rich.console import Console
from rich.prompt import Confirm

from ..models.llm_provider import get_llm_provider
from ..models.state import SubtaskDef, TeamState
from ..models.role import RoleLoader

# Load environment variables
load_dotenv()

console = Console()


class BaseGraphOrchestrator:
    """Base class for LangGraph-based orchestrators with common graph logic.

    Provides shared implementation for:
    - Graph building (supervisor -> execute_agent -> supervisor loop)
    - SQLite checkpoint management
    - Supervisor node and router
    - Dependency resolution
    - Initial state creation
    - Task status management
    """

    def __init__(self, db_path: str | Path = "./ato-output/checkpoints.db"):
        """Initialize the base orchestrator.

        Args:
            db_path: Path to SQLite database for checkpoints.
        """
        self.role_loader = RoleLoader()
        self.llm_provider = get_llm_provider()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer = None
        self._graph = None

    # ============ Graph Building ============

    def _get_checkpointer(self) -> SqliteSaver:
        """Get or create the SQLite checkpointer."""
        if self._checkpointer is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._checkpointer = SqliteSaver(conn)
        return self._checkpointer

    def _get_graph(self) -> StateGraph:
        """Get or create the compiled graph."""
        if self._graph is None:
            checkpointer = self._get_checkpointer()
            self._graph = self._build_graph(checkpointer)
        return self._graph

    def _build_graph(self, checkpointer: SqliteSaver) -> StateGraph:
        """Build the LangGraph state graph.

        Override this method to customize graph structure.

        Args:
            checkpointer: SQLite checkpointer instance.

        Returns:
            Compiled StateGraph.
        """
        workflow = StateGraph(TeamState)

        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("execute_agent", self._execute_agent_node)
        workflow.add_node("merge_results", self._merge_results_node)

        workflow.set_entry_point("supervisor")

        workflow.add_conditional_edges(
            "supervisor",
            self._supervisor_router,
            ["execute_agent", "merge_results"],
        )

        workflow.add_edge("execute_agent", "supervisor")
        workflow.add_edge("merge_results", END)

        return workflow.compile(checkpointer=checkpointer)

    # ============ Task Management ============

    def check_existing_task(self, thread_id: str) -> dict | None:
        """Check if a task checkpoint exists."""
        checkpointer = self._get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        state = checkpointer.get_tuple(config)
        return state if state else None

    def list_incomplete_tasks(self) -> list[str]:
        """List all tasks that have checkpoints but are not completed."""
        import json as _json

        incomplete = []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT thread_id, checkpoint FROM checkpoints")
            for row in cursor.fetchall():
                try:
                    state = _json.loads(row[1])
                    if state.get("status") not in ["completed"]:
                        incomplete.append(row[0])
                except (KeyError, TypeError, _json.JSONDecodeError):
                    incomplete.append(row[0])

            conn.close()
        except sqlite3.Error:
            pass

        return incomplete

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
        thread_id = thread_id or task_id
        config = {"configurable": {"thread_id": thread_id}}

        graph = self._get_graph()

        existing = self.check_existing_task(thread_id)

        if existing and resume:
            console.print(
                f"[yellow]Found existing checkpoint for task: {thread_id}[/]"
            )
            should_resume = Confirm.ask(
                "Resume from checkpoint?",
                default=True,
            )

            if should_resume:
                console.print("[green]Resuming from checkpoint...[/]")
                final_state = graph.invoke(None, config=config)
            else:
                console.print("[yellow]Starting fresh...[/]")
                initial_state = self.create_initial_state(task_id, subtasks)
                final_state = graph.invoke(initial_state, config=config)
        else:
            initial_state = self.create_initial_state(task_id, subtasks)
            final_state = graph.invoke(initial_state, config=config)

        return final_state

    # ============ Graph Nodes ============

    def _supervisor_node(self, state: TeamState) -> TeamState:
        """Supervisor node identifies ready subtasks."""
        ready = self._find_ready(state)
        state["current_subtasks"] = [st["id"] for st in ready]

        completed = sum(1 for st in state["subtasks"] if st["status"] == "completed")
        total = len(state["subtasks"])

        if completed == total:
            state["status"] = "completed"
        elif any(st["status"] == "failed" for st in state["subtasks"]):
            state["status"] = "failed"
        elif ready:
            state["status"] = "running"
        else:
            state["status"] = "pending"

        return state

    def _supervisor_router(self, state: TeamState) -> list[Send] | str:
        """Router for parallel execution."""
        all_done = all(
            st["status"] in ["completed", "failed"] for st in state["subtasks"]
        )

        if all_done:
            return "merge_results"

        ready = [
            st for st in state["subtasks"]
            if st["status"] == "pending" and self._deps_satisfied(state, st)
        ]

        if not ready:
            return "merge_results"

        sends = []
        for subtask in ready:
            self._update_status(state, subtask["id"], "running")
            sends.append(
                Send(
                    "execute_agent",
                    {**state, "current_subtasks": [subtask["id"]]},
                )
            )

        return sends

    def _execute_agent_node(self, state: TeamState) -> TeamState:
        """Execute a single subtask.

        Override this method to add tool-calling, memory integration, etc.
        """
        subtask_id = state["current_subtasks"][0] if state["current_subtasks"] else None
        if not subtask_id:
            return state

        subtask = next((st for st in state["subtasks"] if st["id"] == subtask_id), None)
        if not subtask:
            return state

        try:
            role = self.role_loader.load(subtask["role"])
            llm = self.llm_provider.get_llm()
            context = self._build_context(state, subtask)
            system_prompt = role.render_prompt(context)

            user_prompt = f"""## Your Task

{subtask['expected_output']}

Please provide your output according to your deliverables.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = llm.invoke(messages)
            state["artifacts"][subtask_id] = response.content
            self._update_status(state, subtask_id, "completed")

            state["messages"].append(
                AIMessage(content=f"✓ {role.name} completed: {subtask['name']}")
            )

        except Exception as e:
            state["artifacts"][subtask_id] = f"Error: {str(e)}"
            self._update_status(state, subtask_id, "failed")
            state["messages"].append(
                AIMessage(content=f"✗ Failed on '{subtask['name']}': {str(e)}")
            )

        return state

    def _merge_results_node(self, state: TeamState) -> TeamState:
        """Merge all results."""
        state["status"] = "completed"
        state["messages"].append(AIMessage(content="All tasks completed."))
        return state

    # ============ Helper Methods ============

    def _find_ready(self, state: TeamState) -> list[SubtaskDef]:
        """Find ready subtasks."""
        ready = []
        for st in state["subtasks"]:
            if st["status"] == "pending" and self._deps_satisfied(state, st):
                ready.append(st)
        return ready

    def _deps_satisfied(self, state: TeamState, subtask: SubtaskDef) -> bool:
        """Check if dependencies are satisfied."""
        for dep_id in subtask["dependencies"]:
            dep = next((st for st in state["subtasks"] if st["id"] == dep_id), None)
            if not dep or dep["status"] != "completed":
                return False
        return True

    def _update_status(self, state: TeamState, subtask_id: str, status: str) -> None:
        """Update subtask status."""
        for st in state["subtasks"]:
            if st["id"] == subtask_id:
                st["status"] = status
                break

    def _build_context(self, state: TeamState, subtask: SubtaskDef) -> str:
        """Build context from dependencies.

        Override this method to add memory integration, etc.
        """
        if not subtask["dependencies"]:
            return ""

        lines = ["## Previous Outputs\n"]
        for dep_id in subtask["dependencies"]:
            if dep_id in state["artifacts"]:
                output = str(state["artifacts"][dep_id])
                snippet = output[:1000] + "..." if len(output) > 1000 else output
                lines.append(f"\n### {dep_id}\n```\n{snippet}\n```")

        return "\n".join(lines)

    def create_initial_state(
        self, task_id: str, subtasks: list[SubtaskDef]
    ) -> TeamState:
        """Create initial state."""
        return {
            "task_id": task_id,
            "subtasks": copy.deepcopy(subtasks),
            "artifacts": {},
            "messages": [HumanMessage(content=f"Starting task: {task_id}")],
            "status": "pending",
            "current_subtasks": [],
        }
