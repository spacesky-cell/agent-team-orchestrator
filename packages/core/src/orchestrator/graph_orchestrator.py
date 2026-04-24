"""LangGraph-based orchestrator for multi-agent collaboration."""

import copy
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from ..models.llm_provider import get_llm_provider
from ..models.role import RoleLoader
from ..models.state import SubtaskDef, TeamState

# Load environment variables
load_dotenv()


class SubtaskModel(BaseModel):
    """Pydantic model for subtask data."""

    id: str
    name: str
    role: str
    dependencies: list[str]
    expected_output: str
    status: str = "pending"


class GraphOrchestrator:
    """LangGraph-based orchestrator for parallel agent collaboration.

    This orchestrator uses a state graph with:
    - supervisor: Analyzes subtasks and schedules execution
    - execute_agent: Executes a single subtask
    - merge_results: Aggregates all results
    """

    def __init__(self):
        """Initialize the graph orchestrator."""
        self.role_loader = RoleLoader()
        self.llm_provider = get_llm_provider()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph.

        Returns:
            Compiled StateGraph ready for execution.
        """
        # Create state graph
        workflow = StateGraph(TeamState)

        # Add nodes
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("execute_agent", self._execute_agent_node)
        workflow.add_node("merge_results", self._merge_results_node)

        # Add conditional edges from supervisor
        workflow.add_conditional_edges(
            "supervisor",
            self._supervisor_router,
            {
                "execute": "execute_agent",
                "complete": "merge_results",
            },
        )

        # Add edge from execute_agent back to supervisor
        workflow.add_edge("execute_agent", "supervisor")

        # Add edge from merge_results to END
        workflow.add_edge("merge_results", END)

        # Set entry point
        workflow.set_entry_point("supervisor")

        return workflow.compile(checkpointer=self.checkpointer)

    def _supervisor_node(self, state: TeamState) -> TeamState:
        """Supervisor node analyzes state and determines next actions.

        Args:
            state: Current team state.

        Returns:
            Updated team state.
        """
        # Find subtasks that are ready to execute
        ready_subtasks = self._find_ready_subtasks(state)

        # Store ready subtask IDs in state for router
        state["current_subtasks"] = [st["id"] for st in ready_subtasks]

        # Update status based on completion
        completed_count = sum(1 for st in state["subtasks"] if st["status"] == "completed")
        if completed_count == len(state["subtasks"]):
            state["status"] = "completed"
        elif any(st["status"] == "failed" for st in state["subtasks"]):
            state["status"] = "failed"
        elif ready_subtasks:
            state["status"] = "running"
        else:
            state["status"] = "pending"  # Waiting for dependencies

        return state

    def _supervisor_router(self, state: TeamState) -> Literal["execute", "complete"]:
        """Router function that determines next node.

        Args:
            state: Current team state.

        Returns:
            "execute" if there are subtasks to run, "complete" if all done.
        """
        # Check if all subtasks are completed
        all_completed = all(st["status"] in ["completed", "failed"] for st in state["subtasks"])

        if all_completed:
            return "complete"
        return "execute"

    def _execute_agent_node(self, state: TeamState) -> TeamState:
        """Execute agent node runs a single subtask.

        Args:
            state: Current team state.

        Returns:
            Updated team state with artifacts.
        """
        # Get the first subtask ID from current_subtasks
        # In parallel mode, state will be modified by Send
        subtask_id = state.get("current_subtasks", [])[0] if state.get("current_subtasks") else None

        if not subtask_id:
            return state

        # Find the subtask
        subtask = next((st for st in state["subtasks"] if st["id"] == subtask_id), None)
        if not subtask:
            return state

        # Mark as running
        self._update_subtask_status(state, subtask_id, "running")

        try:
            # Load role
            role = self.role_loader.load(subtask["role"])

            # Get context from artifacts
            context = self._build_context(state, subtask)

            # Get LLM
            llm = self.llm_provider.get_llm()

            # Build messages
            system_prompt = role.render_prompt(context)
            user_prompt = f"""## Your Task

{subtask['expected_output']}

Please provide your output in the format specified in your deliverables.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # Execute
            response = llm.invoke(messages)

            # Store artifact
            state["artifacts"][subtask_id] = response.content

            # Add message to history
            state["messages"].append(
                AIMessage(
                    content=f"Agent {role.name} completed task '{subtask['name']}'",
                )
            )

            # Mark as completed
            self._update_subtask_status(state, subtask_id, "completed")

        except Exception as e:
            # Mark as failed and store error
            state["artifacts"][subtask_id] = f"Error: {str(e)}"
            self._update_subtask_status(state, subtask_id, "failed")
            state["messages"].append(
                AIMessage(
                    content=f"Agent failed on task '{subtask['name']}': {str(e)}",
                )
            )

        return state

    def _merge_results_node(self, state: TeamState) -> TeamState:
        """Merge results node aggregates all artifacts.

        Args:
            state: Current team state.

        Returns:
            Updated team state with merged results.
        """
        state["status"] = "completed"
        state["messages"].append(AIMessage(content="All tasks completed. Results merged."))
        return state

    def _find_ready_subtasks(self, state: TeamState) -> list[SubtaskDef]:
        """Find subtasks whose dependencies are all satisfied.

        Args:
            state: Current team state.

        Returns:
            List of subtask definitions ready to execute.
        """
        ready = []

        for subtask in state["subtasks"]:
            # Skip if already done
            if subtask["status"] in ["completed", "failed", "running"]:
                continue

            # Check if all dependencies are completed
            deps_satisfied = all(
                self._is_subtask_completed(state, dep_id) for dep_id in subtask["dependencies"]
            )

            if deps_satisfied:
                ready.append(subtask)

        return ready

    def _is_subtask_completed(self, state: TeamState, subtask_id: str) -> bool:
        """Check if a subtask is completed.

        Args:
            state: Current team state.
            subtask_id: ID of subtask to check.

        Returns:
            True if subtask is completed.
        """
        subtask = next((st for st in state["subtasks"] if st["id"] == subtask_id), None)
        return subtask is not None and subtask["status"] == "completed"

    def _update_subtask_status(self, state: TeamState, subtask_id: str, status: str) -> None:
        """Update status of a subtask in state.

        Args:
            state: Current team state.
            subtask_id: ID of subtask to update.
            status: New status.
        """
        for subtask in state["subtasks"]:
            if subtask["id"] == subtask_id:
                subtask["status"] = status
                break

    def _build_context(self, state: TeamState, subtask: SubtaskDef) -> str:
        """Build context string from dependent artifacts.

        Args:
            state: Current team state.
            subtask: Subtask being executed.

        Returns:
            Context string with outputs from dependencies.
        """
        if not subtask["dependencies"]:
            return ""

        lines = ["## Previous Work Outputs\n"]

        for dep_id in subtask["dependencies"]:
            if dep_id in state["artifacts"]:
                lines.append(f"\n### From {dep_id}")
                output = state["artifacts"][dep_id]
                snippet = str(output)[:1000] + "..." if len(str(output)) > 1000 else str(output)
                lines.append(f"```\n{snippet}\n```")

        return "\n".join(lines)

    def create_initial_state(self, task_id: str, subtasks: list[SubtaskDef]) -> TeamState:
        """Create initial state for the graph.

        Args:
            task_id: Unique task identifier.
            subtasks: List of subtask definitions.

        Returns:
            Initial team state.
        """
        return {
            "task_id": task_id,
            "subtasks": copy.deepcopy(subtasks),
            "artifacts": {},
            "messages": [HumanMessage(content=f"Starting task: {task_id}")],
            "status": "pending",
            "current_subtasks": [],
        }

    async def run(
        self,
        task_id: str,
        subtasks: list[SubtaskDef],
        thread_id: str | None = None,
    ) -> TeamState:
        """Run the graph orchestrator.

        Args:
            task_id: Unique task identifier.
            subtasks: List of subtask definitions.
            thread_id: Optional thread ID for checkpointing.

        Returns:
            Final team state.
        """
        initial_state = self.create_initial_state(task_id, subtasks)

        config = {"configurable": {"thread_id": thread_id or task_id}}

        final_state = await self.graph.ainvoke(initial_state, config=config)

        return final_state
