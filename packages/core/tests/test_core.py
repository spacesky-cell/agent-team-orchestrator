"""Tests for Agent Team Orchestrator core package."""

import asyncio

import pytest


class TestRoleLoader:
    """Tests for Role model and loader."""

    @pytest.fixture(autouse=True)
    def _skip_without_langchain(self):
        """Skip tests if langchain is not installed."""
        pytest.importorskip("langchain_anthropic", reason="langchain-anthropic not installed")

    def test_list_roles(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        roles = loader.list_roles()
        assert isinstance(roles, list)
        assert len(roles) > 0
        assert "architect" in roles

    def test_load_architect_role(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        role = loader.load("architect")
        assert role.id == "architect"
        assert role.name != ""
        assert len(role.expertise) > 0
        assert len(role.tools) > 0

    def test_load_backend_developer_role(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        role = loader.load("backend-developer")
        assert role.id == "backend-developer"

    def test_load_nonexistent_role_raises(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent-role")

    def test_role_render_prompt(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        role = loader.load("architect")
        prompt = role.render_prompt("Test context")
        assert "Test context" in prompt

    def test_role_render_prompt_empty_context(self):
        from src.models.role import RoleLoader

        loader = RoleLoader()
        role = loader.load("architect")
        prompt = role.render_prompt("")
        assert "{{context}}" not in prompt


class TestModels:
    """Tests for data models."""

    @pytest.fixture(autouse=True)
    def _skip_without_langchain(self):
        pytest.importorskip("langchain_anthropic", reason="langchain-anthropic not installed")

    def test_subtask_model(self):
        from src.models.task import Subtask

        subtask = Subtask(
            id="st-1",
            name="Test Subtask",
            role="architect",
            expected_output="Some output",
        )
        assert subtask.id == "st-1"
        assert subtask.dependencies == []

    def test_task_decomposition_model(self):
        from src.models.task import Subtask, TaskDecomposition

        decomposition = TaskDecomposition(
            task_id="task-001",
            summary="Test task",
            subtasks=[
                Subtask(
                    id="st-1",
                    name="Sub 1",
                    role="architect",
                    expected_output="Output 1",
                )
            ],
        )
        assert decomposition.task_id == "task-001"
        assert len(decomposition.subtasks) == 1

    def test_task_result_model(self):
        from src.models.task import TaskResult

        result = TaskResult(
            task_id="task-001",
            status="completed",
            artifacts={"st-1": "output"},
        )
        assert result.status == "completed"
        assert result.error is None

    def test_team_state_typeddict(self):
        from src.models.state import TeamState

        state: TeamState = {
            "task_id": "task-001",
            "subtasks": [
                {
                    "id": "st-1",
                    "name": "Test",
                    "role": "architect",
                    "dependencies": [],
                    "expected_output": "Output",
                    "status": "pending",
                }
            ],
            "artifacts": {},
            "messages": [],
            "status": "pending",
            "current_subtasks": [],
        }
        assert state["task_id"] == "task-001"
        assert state["subtasks"][0]["status"] == "pending"

    def test_llm_config(self):
        from src.models.llm_provider import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4")
        assert config.provider == "openai"
        assert config.temperature == 0.7

    def test_llm_config_default_provider_uses_claude_cli(self):
        from src.models.llm_provider import LLMConfig

        assert LLMConfig().provider == "claude-cli"


class TestLLMProvider:
    """Tests for LLM provider selection and adapters."""

    def test_claude_cli_provider_selected_from_environment(self, monkeypatch):
        from src.models.llm_provider import ClaudeCliProvider, get_llm_provider

        monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        provider = get_llm_provider()

        assert isinstance(provider, ClaudeCliProvider)

    def test_claude_cli_chat_model_invokes_claude_print(self, monkeypatch):
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.models.llm_provider import ClaudeCliChatModel

        captured = {}

        class Result:
            returncode = 0
            stdout = "hello from claude\n"
            stderr = ""

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return Result()

        monkeypatch.setattr("src.models.llm_provider.shutil.which", lambda name: "claude")
        monkeypatch.setattr("src.models.llm_provider.subprocess.run", fake_run)

        llm = ClaudeCliChatModel(timeout=12)
        response = llm.invoke(
            [
                SystemMessage(content="system instructions"),
                HumanMessage(content="user task"),
                "format instructions",
            ]
        )

        assert response.content == "hello from claude"
        assert captured["args"] == ["claude", "-p", "--safe-mode", "--output-format", "text"]
        assert captured["kwargs"]["input"]
        assert "system instructions" in captured["kwargs"]["input"]
        assert "user task" in captured["kwargs"]["input"]
        assert "format instructions" in captured["kwargs"]["input"]
        assert captured["args"][4] == "text"
        assert captured["kwargs"]["timeout"] == 12
        assert llm.bind_tools([]) is llm


class TestTools:
    """Tests for tool definitions."""

    def test_get_all_tools(self):
        from src.tools import get_all_tools

        tools = get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_get_file_tools(self):
        from src.tools import get_file_tools

        tools = get_file_tools()
        assert len(tools) > 0
        names = [t.name for t in tools]
        assert "read_file" in names
        assert "write_file" in names

    def test_get_code_tools(self):
        from src.tools import get_code_tools

        tools = get_code_tools()
        assert len(tools) > 0
        names = [t.name for t in tools]
        assert "execute_command" in names

    def test_get_tools_for_role(self):
        from src.tools import get_tools_for_role

        tools = get_tools_for_role(["read_file", "write_file"])
        assert len(tools) == 2

    def test_get_tools_for_role_empty(self):
        from src.tools import get_tools_for_role

        tools = get_tools_for_role([])
        assert len(tools) == 0

    def test_get_tools_for_role_unknown(self):
        from src.tools import get_tools_for_role

        tools = get_tools_for_role(["nonexistent_tool"])
        assert len(tools) == 0

    def test_tool_has_required_attributes(self):
        from src.tools import get_all_tools

        for tool in get_all_tools():
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "parameters")
            assert hasattr(tool, "execute")

    def test_file_tools_respect_explicit_project_root(self, tmp_path):
        from src.tools.file_ops import ReadFileTool

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        allowed_file = allowed / "example.txt"
        allowed_file.write_text("hello", encoding="utf-8")

        denied = tmp_path / "denied"
        denied.mkdir()
        denied_file = denied / "secret.txt"
        denied_file.write_text("secret", encoding="utf-8")

        tool = ReadFileTool(allowed_dirs=[allowed])

        allowed_result = asyncio.run(tool.execute(path=str(allowed_file)))
        denied_result = asyncio.run(tool.execute(path=str(denied_file)))

        assert "hello" in allowed_result
        assert "Access denied" in denied_result

    def test_code_tools_respect_explicit_project_root(self, tmp_path):
        from src.tools.code_ops import ExecuteCommandTool

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        denied = tmp_path / "denied"
        denied.mkdir()

        tool = ExecuteCommandTool(allowed_dirs=[allowed])

        allowed_result = asyncio.run(
            tool.execute(command="python -c \"print('ok')\"", cwd=str(allowed))
        )
        denied_result = asyncio.run(
            tool.execute(command="python -c \"print('no')\"", cwd=str(denied))
        )

        assert "ok" in allowed_result
        assert "[exit code: 0]" in allowed_result
        assert "Access denied" in denied_result


class TestTaskDecomposer:
    """Tests for task decomposer prompts."""

    @pytest.fixture(autouse=True)
    def _skip_without_langchain(self):
        pytest.importorskip("langchain_anthropic", reason="langchain-anthropic not installed")

    def test_build_system_prompt(self):
        from src.prompts.task_decompose import TaskDecomposer

        prompt = TaskDecomposer.build_system_prompt()
        assert "architect" in prompt
        assert "backend-developer" in prompt
        assert "JSON" in prompt

    def test_build_user_prompt(self):
        from src.prompts.task_decompose import TaskDecomposer

        prompt = TaskDecomposer.build_user_prompt("Build a login system")
        assert "Build a login system" in prompt
        assert "Example 1" in prompt

    def test_task_decomposition_result(self):
        from src.prompts.task_decompose import TaskDecompositionResult

        result = TaskDecompositionResult(
            task_id="task-001",
            summary="Test summary",
            subtasks=[],
        )
        assert result.task_id == "task-001"

    def test_generate_task_id(self):
        from src.prompts.task_decompose import TaskDecompositionResult

        task_id = TaskDecompositionResult.generate_task_id()
        assert task_id.startswith("task-")


class TestGraphOrchestratorStatus:
    """Tests for shared graph state status transitions."""

    def test_merge_results_preserves_failed_subtask_status(self):
        from src.orchestrator.base_orchestrator import BaseGraphOrchestrator

        orchestrator = BaseGraphOrchestrator(db_path=":memory:")
        state = {
            "task_id": "task-001",
            "subtasks": [
                {
                    "id": "st-1",
                    "name": "Failed",
                    "role": "architect",
                    "dependencies": [],
                    "expected_output": "Output",
                    "status": "failed",
                }
            ],
            "artifacts": {"st-1": "Error"},
            "messages": [],
            "status": "failed",
            "current_subtasks": [],
        }

        final_state = orchestrator._merge_results_node(state)

        assert final_state["status"] == "failed"

    def test_supervisor_marks_blocked_pending_task_as_failed(self):
        from src.orchestrator.base_orchestrator import BaseGraphOrchestrator

        orchestrator = BaseGraphOrchestrator(db_path=":memory:")
        state = {
            "task_id": "task-001",
            "subtasks": [
                {
                    "id": "st-1",
                    "name": "Blocked",
                    "role": "architect",
                    "dependencies": ["missing"],
                    "expected_output": "Output",
                    "status": "pending",
                }
            ],
            "artifacts": {},
            "messages": [],
            "status": "pending",
            "current_subtasks": [],
        }

        next_node = orchestrator._supervisor_router(state)

        assert next_node == "merge_results"
        assert state["status"] == "failed"
        assert state["artifacts"]["st-1"].startswith("Blocked:")


class TestToolEnabledOrchestrator:
    """Tests for tool-enabled orchestration helpers."""

    def test_langchain_tool_wrappers_call_the_matching_base_tool(self, tmp_path):
        from src.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator
        from src.tools.base import BaseTool

        class EchoTool(BaseTool):
            def __init__(self, name):
                self.name = name
                self.description = f"{name} description"
                self.parameters = {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string", "description": "Value to echo"},
                    },
                    "required": ["value"],
                }

            async def execute(self, **kwargs):
                return f"{self.name}:{kwargs['value']}"

        orchestrator = ToolEnabledOrchestrator(
            db_path=tmp_path / "checkpoints.db",
            project_root=tmp_path,
            memory_dir=".memory",
        )

        wrappers = orchestrator._convert_to_langchain_tools(
            [EchoTool("first_tool"), EchoTool("second_tool")]
        )
        by_name = {wrapper.name: wrapper for wrapper in wrappers}

        assert by_name["first_tool"].invoke({"value": "a"}) == "first_tool:a"
        assert by_name["second_tool"].invoke({"value": "b"}) == "second_tool:b"


class TestTeamMemory:
    """Tests for team memory module."""

    def test_init_team_memory(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        assert memory.storage_path.exists()
        assert memory.db_path.exists()

    def test_set_and_get_context(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        memory.set_context("test_key", "test_value")
        value = memory.get_context("test_key")
        assert value == "test_value"

    def test_get_context_missing(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        value = memory.get_context("nonexistent")
        assert value is None

    def test_record_decision(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        decision = memory.record_decision(
            title="Test Decision",
            content="Chose PostgreSQL",
            agent_role="architect",
        )
        assert decision.id.startswith("dec-")
        assert decision.title == "Test Decision"

    def test_record_code_change(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        change = memory.record_code_change(
            file_path="src/main.py",
            change_type="modify",
            description="Add login endpoint",
            agent_role="backend-developer",
        )
        assert change.id.startswith("chg-")
        assert change.file_path == "src/main.py"

    def test_summary(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        summary = memory.summary()
        assert "Team Memory Summary" in summary

    def test_clear_memory(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        memory.set_context("key1", "value1")
        memory.clear()
        assert memory.get_context("key1") is None

    def test_get_decisions(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        memory.record_decision(
            title="Decision 1",
            content="Content 1",
            agent_role="architect",
        )
        memory.record_decision(
            title="Decision 2",
            content="Content 2",
            agent_role="architect",
        )
        decisions = memory.get_decisions()
        assert len(decisions) == 2

    def test_retrieve_relevant_context_fallback(self, tmp_path):
        from src.memory.team_memory import TeamMemory

        memory = TeamMemory(project_root=str(tmp_path))
        context = memory.retrieve_relevant_context("test query")
        # Without ChromaDB, should fall back to keyword matching
        assert isinstance(context, str)


class TestVisualization:
    """Tests for Mermaid visualization module."""

    def test_generate_mermaid_dag(self):
        from src.visualization.mermaid import generate_mermaid_dag

        subtasks = [
            {
                "id": "st-1",
                "name": "Task 1",
                "role": "architect",
                "dependencies": [],
                "status": "pending",
            },
            {
                "id": "st-2",
                "name": "Task 2",
                "role": "dev",
                "dependencies": ["st-1"],
                "status": "completed",
            },
        ]
        diagram = generate_mermaid_dag(subtasks)
        assert "graph TD" in diagram
        assert "st-1" in diagram
        assert "st-2" in diagram

    def test_generate_mermaid_dag_with_status(self):
        from src.visualization.mermaid import generate_mermaid_dag

        subtasks = [
            {
                "id": "st-1",
                "name": "Done",
                "role": "dev",
                "dependencies": [],
                "status": "completed",
            },
        ]
        diagram = generate_mermaid_dag(subtasks, show_status=True)
        assert "[completed]" in diagram

    def test_generate_mermaid_timeline(self):
        from src.visualization.mermaid import generate_mermaid_timeline

        subtasks = [
            {"id": "st-1", "name": "Task 1", "role": "dev", "status": "completed"},
            {"id": "st-2", "name": "Task 2", "role": "dev", "status": "running"},
        ]
        timeline = generate_mermaid_timeline(subtasks, "Test Task")
        assert "gantt" in timeline
        assert "Test Task" in timeline

    def test_generate_execution_report(self):
        from src.visualization.mermaid import generate_execution_report

        subtasks = [
            {
                "id": "st-1",
                "name": "Task 1",
                "role": "dev",
                "status": "completed",
                "dependencies": [],
                "expected_output": "output",
            },
        ]
        report = generate_execution_report("task-001", subtasks)
        assert "# Task Execution Report" in report
        assert "task-001" in report
        assert "Summary" in report

    def test_mermaid_visualizer(self):
        from src.visualization.mermaid import MermaidVisualizer

        subtasks = [
            {
                "id": "st-1",
                "name": "T1",
                "role": "dev",
                "dependencies": [],
                "status": "pending",
            }
        ]
        dag = MermaidVisualizer.dag(subtasks)
        assert "graph TD" in dag

        timeline = MermaidVisualizer.timeline(subtasks, "Test")
        assert "gantt" in timeline
