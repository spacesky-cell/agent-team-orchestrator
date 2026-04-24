"""LangGraph orchestrator with tool-calling support for real execution."""

import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ..memory.team_memory import TeamMemory
from ..models.state import SubtaskDef, TeamState
from ..tools import get_all_tools, get_tools_for_role
from .base_orchestrator import BaseGraphOrchestrator


class ToolEnabledOrchestrator(BaseGraphOrchestrator):
    """LangGraph orchestrator with tool-calling support.

    Agents can use tools to:
    - Read/write files
    - Execute commands
    - Run tests
    - Make git commits

    Inherits all common graph logic from BaseGraphOrchestrator,
    and overrides _execute_agent_node to add ReAct loop with tool calling.
    """

    def __init__(
        self,
        db_path: str | Path = "./ato-output/checkpoints.db",
        project_root: str | Path = ".",
        memory_dir: str = ".ato/memory",
    ):
        """Initialize the orchestrator.

        Args:
            db_path: Path to SQLite database for checkpoints.
            project_root: Root directory of the project.
            memory_dir: Directory for memory storage (relative to project_root).
        """
        super().__init__(db_path)
        self._tool_registry = {t.name: t for t in get_all_tools()}

        # Initialize team memory for context sharing
        self.memory = TeamMemory(
            project_root=project_root,
            storage_dir=memory_dir,
        )

    def _convert_to_langchain_tools(self, tools: list) -> list:
        """Convert our BaseTool instances to LangChain tools.

        Args:
            tools: List of our BaseTool instances.

        Returns:
            List of LangChain-compatible tools.
        """
        from langchain_core.tools import tool as langchain_tool
        from pydantic import create_model

        langchain_tools = []

        for tool in tools:
            properties = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])

            fields = {}
            for field_name, field_info in properties.items():
                field_type = str
                if field_info.get("type") == "integer":
                    field_type = int
                elif field_info.get("type") == "boolean":
                    field_type = bool
                elif field_info.get("type") == "number":
                    field_type = float

                if field_name not in required:
                    field_type = field_type | None

                fields[field_name] = (field_type, field_info.get("description", ""))

            args_model = create_model(
                f"{tool.name}Args", __config__=type("Config", (), {"extra": "forbid"}), **fields
            )

            @langchain_tool(args_schema=args_model)
            def tool_func(**kwargs):
                """Wrapper function."""
                return asyncio.run(tool.execute(**kwargs))

            tool_func.name = tool.name
            tool_func.description = tool.description

            langchain_tools.append(tool_func)

        return langchain_tools

    def run(
        self,
        task_id: str,
        subtasks: list[SubtaskDef],
        thread_id: str | None = None,
        resume: bool = True,
    ) -> TeamState:
        """Run the orchestrator with checkpointing.

        Overrides base to add memory context retrieval on fresh starts.

        Args:
            task_id: Unique task identifier.
            subtasks: List of subtask definitions.
            thread_id: Optional thread ID for checkpointing.
            resume: Whether to resume from existing checkpoint if found.

        Returns:
            Final team state.
        """
        thread_id = thread_id or task_id
        from rich.console import Console
        from rich.prompt import Confirm

        console = Console()
        config = {"configurable": {"thread_id": thread_id}}

        graph = self._get_graph()

        existing = self.check_existing_task(thread_id)

        if existing and resume:
            console.print(f"[yellow]Found existing checkpoint for task: {thread_id}[/]")
            should_resume = Confirm.ask(
                "Resume from checkpoint?",
                default=True,
            )

            if should_resume:
                console.print("[green]Resuming from checkpoint...[/]")
                final_state = graph.invoke(None, config=config)
            else:
                console.print("[yellow]Starting fresh...[/]")
                self._show_relevant_context_from_memory(task_id, subtasks)
                initial_state = self.create_initial_state(task_id, subtasks)
                final_state = graph.invoke(initial_state, config=config)
        else:
            self._show_relevant_context_from_memory(task_id, subtasks)
            initial_state = self.create_initial_state(task_id, subtasks)
            final_state = graph.invoke(initial_state, config=config)

        return final_state

    def _show_relevant_context_from_memory(self, task_id: str, subtasks: list[SubtaskDef]) -> None:
        """Show relevant context from team memory before starting task."""
        from rich.console import Console

        console = Console()

        query = f"Task: {task_id}\n"
        query += "\n".join(
            [
                f"- {st.get('name', st['id'])}: {st.get('expected_output', '')[:100]}"
                for st in subtasks[:3]
            ]
        )

        relevant = self.memory.retrieve_relevant_context(query, top_k=5)

        if relevant and "No previous context available" not in relevant:
            console.print("\n[cyan]📚 Relevant context from team memory:[/]")
            console.print(f"[dim]{relevant[:800]}{'...' if len(relevant) > 800 else ''}[/]\n")

    def _execute_agent_node(self, state: TeamState) -> TeamState:
        """Execute a single subtask with tool-calling support (ReAct loop).

        Overrides base to add ReAct loop with tool calls.
        """
        from rich.console import Console

        console = Console()

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

            # Get tools available for this role
            role_tools = get_tools_for_role(role.tools)
            langchain_tools = self._convert_to_langchain_tools(role_tools)

            # Bind tools to LLM
            llm_with_tools = llm.bind_tools(langchain_tools) if langchain_tools else llm

            user_prompt = f"""## Your Task

{subtask['expected_output']}

Please provide your output according to your deliverables.
You have access to tools - use them if needed to complete your task.
"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # ReAct loop
            max_iterations = 10
            iteration = 0
            final_content = None

            while iteration < max_iterations:
                iteration += 1

                response = llm_with_tools.invoke(messages)

                if hasattr(response, "tool_calls") and response.tool_calls:
                    messages.append(response)

                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call.get("args", {})

                        console.print(f"  [dim]Tool call: {tool_name}({tool_args})[/]")

                        tool = self._tool_registry.get(tool_name)
                        if tool:
                            try:
                                tool_result = asyncio.run(tool.execute(**tool_args))
                            except Exception as e:
                                tool_result = f"Error: {str(e)}"
                        else:
                            tool_result = f"Error: Unknown tool '{tool_name}'"

                        result_preview = (
                            f"{tool_result[:100]}..." if len(tool_result) > 100 else tool_result
                        )
                        console.print(f"  [dim]Result: {result_preview}[/]")

                        messages.append(
                            ToolMessage(
                                content=tool_result,
                                tool_call_id=tool_call.get("id", ""),
                            )
                        )
                else:
                    final_content = response.content
                    break

            if final_content is None:
                final_content = (
                    response.content if hasattr(response, "content") else "No output generated"
                )

            state["artifacts"][subtask_id] = final_content
            self._update_status(state, subtask_id, "completed")

            # Record to team memory for future context sharing
            self._record_to_memory(subtask, role, final_content)

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

    def _record_to_memory(self, subtask: SubtaskDef, role, output: str) -> None:
        """Record subtask output to team memory."""
        from rich.console import Console

        console = Console()

        try:
            if subtask.get("role") == "architect":
                self.memory.record_decision(
                    title=subtask.get("name", subtask.get("id")),
                    content=output[:500] + "..." if len(output) > 500 else output,
                    agent_role=role.name,
                    rationale=subtask.get("expected_output", ""),
                    consequences="",
                )
            elif subtask.get("role") in (
                "backend-developer",
                "frontend-developer",
                "fullstack-developer",
            ):
                import re

                file_paths = re.findall(r"[\w/\\]+(?:\.[a-z]{2,4})", output)
                for file_path in file_paths[:3]:
                    self.memory.record_code_change(
                        file_path=file_path,
                        change_type="modify",
                        description=subtask.get("name", ""),
                        agent_role=role.name,
                        snippet=output[:200] + "..." if len(output) > 200 else output,
                    )
            else:
                self.memory.set_context(
                    key=f"{subtask['id']}_output",
                    value=output[:1000] + "..." if len(output) > 1000 else output,
                )
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to record to memory: {e}[/]")

    def _build_context(self, state: TeamState, subtask: SubtaskDef) -> str:
        """Build context from dependencies and team memory.

        Overrides base to add memory retrieval.
        """
        lines = []

        # 1. Get relevant context from team memory using semantic search
        relevant_memory = self.memory.retrieve_relevant_context(
            query=subtask.get("expected_output", ""),
            role=subtask.get("role"),
            top_k=3,
        )
        if relevant_memory and "No previous context available" not in relevant_memory:
            lines.append("## Relevant Context from Team Memory\n")
            lines.append(relevant_memory)
            lines.append("")

        # 2. Add outputs from dependencies
        if subtask["dependencies"]:
            lines.append("## Previous Subtask Outputs\n")
            for dep_id in subtask["dependencies"]:
                if dep_id in state["artifacts"]:
                    output = str(state["artifacts"][dep_id])
                    snippet = output[:1000] + "..." if len(output) > 1000 else output
                    lines.append(f"\n### {dep_id}\n```\n{snippet}\n```")

        return "\n".join(lines)
