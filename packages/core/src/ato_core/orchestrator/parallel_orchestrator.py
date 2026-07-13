"""LangGraph-based orchestrator with parallel execution support."""

import copy

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from ..models.llm_provider import get_llm_provider
from ..models.role import RoleLoader
from ..models.state import SubtaskDef, TeamState

# Load environment variables
load_dotenv()


class ParallelGraphOrchestrator:
    """LangGraph orchestrator with parallel subtask execution using Send API.

    This orchestrator supports:
    - Parallel execution of independent subtasks
    - Dependency-aware scheduling
    - Checkpointing for resilience
    """

    def __init__(self):
        """Initialize the parallel graph orchestrator."""
        self.role_loader = RoleLoader()
        self.llm_provider = get_llm_provider()
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph with parallel execution.

        The graph structure:
        1. supervisor: Analyzes state, identifies ready subtasks
        2. execute_agent: Runs a single subtask (can be invoked in parallel via Send)
        3. merge_results: Aggregates all outputs when complete

        Returns:
            Compiled StateGraph ready for execution.
        """
        workflow = StateGraph(TeamState)

        # Add nodes
        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("execute_agent", self._execute_agent_node)
        workflow.add_node("merge_results", self._merge_results_node)

        # Set entry point
        workflow.set_entry_point("supervisor")

        # Add conditional edges from supervisor
        # This returns a list of Send objects for parallel execution
        workflow.add_conditional_edges(
            "supervisor",
            self._supervisor_router,
            ["execute_agent", "merge_results"],
        )

        # Add edge from execute_agent back to supervisor
        workflow.add_edge("execute_agent", "supervisor")

        # Add edge from merge_results to END
        workflow.add_edge("merge_results", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _supervisor_node(self, state: TeamState) -> TeamState:
        """Supervisor node identifies ready subtasks and updates status.

        Args:
            state: Current team state.

        Returns:
            Updated team state.
        """
        # Find subtasks ready to execute
        ready_subtasks = self._find_ready_subtasks(state)
        state["current_subtasks"] = [st["id"] for st in ready_subtasks]

        # Determine overall status
        completed = sum(1 for st in state["subtasks"] if st["status"] == "completed")
        total = len(state["subtasks"])

        if completed == total:
            state["status"] = "completed"
        elif any(st["status"] == "failed" for st in state["subtasks"]):
            state["status"] = "failed"
        elif ready_subtasks:
            state["status"] = "running"
        else:
            state["status"] = "pending"

        return state

    def _supervisor_router(self, state: TeamState) -> list[Send] | str:
        """Router that creates parallel execution branches using Send.

        This is the key method for parallel execution:
        - Returns a list of Send objects for each ready subtask
        - Each Send invokes execute_agent with the subtask context
        - Returns "merge_results" when all subtasks are done

        Args:
            state: Current team state.

        Returns:
            List of Send objects for parallel execution, or "merge_results".
        """
        # Check if all subtasks are completed or failed
        all_done = all(st["status"] in ["completed", "failed"] for st in state["subtasks"])

        if all_done:
            return "merge_results"

        # Find ready subtasks (not running yet)
        ready_subtasks = [
            st
            for st in state["subtasks"]
            if st["status"] == "pending" and self._deps_satisfied(state, st)
        ]

        if not ready_subtasks:
            # No ready subtasks, wait (this shouldn't happen in a well-formed DAG)
            return "merge_results"

        # Create Send objects for parallel execution
        # Each Send will invoke execute_agent with a specific subtask
        sends = []
        for subtask in ready_subtasks:
            # Mark as running before dispatch
            self._update_status(state, subtask["id"], "running")
            sends.append(
                Send(
                    "execute_agent",
                    {
                        **state,
                        "current_subtasks": [subtask["id"]],
                    },
                )
            )

        return sends

    def _execute_agent_node(self, state: TeamState) -> TeamState:
        """Execute a single subtask.

        This node is invoked in parallel for different subtasks via Send.

        Args:
            state: Current team state (modified by Send to include specific subtask).

        Returns:
            Updated team state with artifact stored.
        """
        subtask_id = state["current_subtasks"][0] if state["current_subtasks"] else None
        if not subtask_id:
            return state

        subtask = next((st for st in state["subtasks"] if st["id"] == subtask_id), None)
        if not subtask:
            return state

        try:
            # Load role
            role = self.role_loader.load(subtask["role"])

            # Get LLM
            llm = self.llm_provider.get_llm()

            # Build context from dependencies
            context = self._build_context(state, subtask)

            # Render system prompt
            system_prompt = role.render_prompt(context)

            # Build user prompt
            user_prompt = f"""## Your Task

{subtask['expected_output']}

Please provide your output according to your deliverables.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # Execute LLM call
            response = llm.invoke(messages)

            # Store artifact
            state["artifacts"][subtask_id] = response.content

            # Update status
            self._update_status(state, subtask_id, "completed")

            # Add completion message
            state["messages"].append(
                AIMessage(content=f"✓ Agent '{role.name}' completed: {subtask['name']}")
            )

        except Exception as e:
            # Handle failure
            state["artifacts"][subtask_id] = f"Error: {str(e)}"
            self._update_status(state, subtask_id, "failed")
            state["messages"].append(
                AIMessage(content=f"✗ Agent failed on '{subtask['name']}': {str(e)}")
            )

        return state

    def _merge_results_node(self, state: TeamState) -> TeamState:
        """Merge all results and finalize.

        Args:
            state: Current team state.

        Returns:
            Final team state.
        """
        state["status"] = "completed"
        state["messages"].append(AIMessage(content="All tasks completed successfully."))
        return state

    def _find_ready_subtasks(self, state: TeamState) -> list[SubtaskDef]:
        """Find all subtasks ready to execute.

        A subtask is ready if:
        - Status is "pending"
        - All dependencies are completed

        Args:
            state: Current team state.

        Returns:
            List of ready subtask definitions.
        """
        ready = []
        for subtask in state["subtasks"]:
            if subtask["status"] != "pending":
                continue
            if self._deps_satisfied(state, subtask):
                ready.append(subtask)
        return ready

    def _deps_satisfied(self, state: TeamState, subtask: SubtaskDef) -> bool:
        """Check if all dependencies of a subtask are completed.

        Args:
            state: Current team state.
            subtask: Subtask to check.

        Returns:
            True if all dependencies are satisfied.
        """
        for dep_id in subtask["dependencies"]:
            dep = next((st for st in state["subtasks"] if st["id"] == dep_id), None)
            if not dep or dep["status"] != "completed":
                return False
        return True

    def _update_status(self, state: TeamState, subtask_id: str, status: str) -> None:
        """Update the status of a subtask.

        Args:
            state: Current team state.
            subtask_id: ID of subtask to update.
            status: New status value.
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
                output = str(state["artifacts"][dep_id])
                snippet = output[:1000] + "..." if len(output) > 1000 else output
                lines.append(f"\n### From {dep_id}\n```\n{snippet}\n```")

        return "\n".join(lines)

    def create_initial_state(self, task_id: str, subtasks: list[SubtaskDef]) -> TeamState:
        """Create initial state for execution.

        Args:
            task_id: Unique task identifier.
            subtasks: List of subtask definitions.

        Returns:
            Initial team state dictionary.
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
        """Run the parallel orchestrator.

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
