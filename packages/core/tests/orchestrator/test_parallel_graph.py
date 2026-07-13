"""Reducer-safe LangGraph parallel execution tests."""

from pathlib import Path

from langchain_core.messages import AIMessage

from ato_core.models.state import TeamState
from ato_core.orchestrator.base_orchestrator import BaseGraphOrchestrator
from ato_core.orchestrator.graph_orchestrator import GraphOrchestrator
from ato_core.orchestrator.parallel_orchestrator import ParallelGraphOrchestrator


def subtask(subtask_id: str, dependencies: list[str] | None = None) -> dict[str, object]:
    return {
        "id": subtask_id,
        "name": subtask_id,
        "role": "architect",
        "dependencies": dependencies or [],
        "expected_output": f"output for {subtask_id}",
        "status": "pending",
    }


class FakeGraphOrchestrator(BaseGraphOrchestrator):
    """Execute deterministic branch-local results without an LLM."""

    def __init__(self, db_path: Path, failing: set[str] | None = None):
        super().__init__(db_path)
        self.failing = failing or set()
        self.llm_provider = _FakeProvider()

    def _execute_agent_state(self, state: TeamState) -> TeamState:
        subtask_id = state["current_subtasks"][0]
        if subtask_id in self.failing:
            state["artifacts"][subtask_id] = f"Error: failed:{subtask_id}"
            self._update_status(state, subtask_id, "failed")
        else:
            state["artifacts"][subtask_id] = f"done:{subtask_id}"
            self._update_status(state, subtask_id, "completed")
        return state


class _FakeLlm:
    def invoke(self, messages: list[object]) -> AIMessage:
        return AIMessage(content="fake")


class _FakeProvider:
    def get_llm(self) -> _FakeLlm:
        return _FakeLlm()


def test_two_ready_subtasks_merge_without_concurrent_update(tmp_path: Path) -> None:
    orchestrator = FakeGraphOrchestrator(tmp_path / "parallel.db")

    result = orchestrator.run(
        task_id="task-parallel",
        subtasks=[subtask("a"), subtask("b")],
        resume=False,
    )

    assert result["status"] == "completed"
    assert result["artifacts"] == {"a": "done:a", "b": "done:b"}
    assert [(item["id"], item["status"]) for item in result["subtasks"]] == [
        ("a", "completed"),
        ("b", "completed"),
    ]


def test_dependency_fan_in_runs_after_both_dependencies(tmp_path: Path) -> None:
    orchestrator = FakeGraphOrchestrator(tmp_path / "fanin.db")

    result = orchestrator.run(
        task_id="task-fanin",
        subtasks=[
            subtask("a"),
            subtask("b"),
            subtask("merge", ["a", "b"]),
        ],
        resume=False,
    )

    assert result["status"] == "completed"
    assert result["artifacts"]["merge"] == "done:merge"


def test_failed_branch_blocks_its_dependents_without_false_completion(tmp_path: Path) -> None:
    orchestrator = FakeGraphOrchestrator(tmp_path / "failed.db", failing={"a"})

    result = orchestrator.run(
        task_id="task-failed",
        subtasks=[subtask("a"), subtask("b"), subtask("after-a", ["a"])],
        resume=False,
    )

    statuses = {item["id"]: item["status"] for item in result["subtasks"]}
    assert result["status"] == "failed"
    assert statuses == {"a": "failed", "b": "completed", "after-a": "failed"}
    assert result["artifacts"]["after-a"].startswith("Blocked:")


def test_public_graph_classes_use_the_canonical_graph_implementation() -> None:
    assert GraphOrchestrator._build_graph is BaseGraphOrchestrator._build_graph
    assert ParallelGraphOrchestrator._build_graph is BaseGraphOrchestrator._build_graph
