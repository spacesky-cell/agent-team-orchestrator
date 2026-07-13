"""Process-recreation tests for durable LangGraph tool approvals."""

from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.types import Command

from ato_core.models.state import TeamState
from ato_core.orchestrator.base_orchestrator import BaseGraphOrchestrator
from ato_core.orchestrator.tool_audit import ToolAuditLogger
from ato_core.orchestrator.tool_enabled_orchestrator import ToolEnabledOrchestrator
from ato_core.runtime.approval import ApprovalStore, ToolPolicy
from ato_core.runtime.task_store import TaskStore


def subtask() -> dict[str, object]:
    return {
        "id": "mutate",
        "name": "mutate",
        "role": "architect",
        "dependencies": [],
        "expected_output": "write the marker",
        "status": "pending",
    }


class MarkerTool:
    name = "write_file"

    def __init__(self, marker: Path):
        self.marker = marker

    async def execute(self, **kwargs: object) -> str:
        del kwargs
        previous = self.marker.read_text(encoding="utf-8") if self.marker.exists() else ""
        self.marker.write_text(previous + "executed\n", encoding="utf-8")
        return "marker written"


class ApprovalGraph(ToolEnabledOrchestrator):
    """Minimal real LangGraph using the production approval execution boundary."""

    def __init__(self, store: TaskStore, marker: Path):
        BaseGraphOrchestrator.__init__(self, store.paths.checkpoints)
        self.project_root = store.read().project_root
        self._allowed_dirs = [self.project_root]
        self.tool_policy = ToolPolicy()
        self.approval_store = ApprovalStore(store)
        self.audit_logger = ToolAuditLogger(store.paths.audit)
        self.tool = MarkerTool(marker)

    def _execute_agent_state(self, state: TeamState) -> TeamState:
        current = state["current_subtasks"][0]
        item = next(value for value in state["subtasks"] if value["id"] == current)
        result = self._execute_tool_with_policy_and_audit(
            tool=self.tool,
            tool_args={"path": "marker.txt", "content": "executed"},
            state=state,
            subtask=item,
            role_name="Architect",
            policy=self.tool_policy,
            audit_logger=self.audit_logger,
            approval_key="tool-call-1",
        )
        state["artifacts"][current] = result
        self._update_status(
            state,
            current,
            "failed" if result.startswith(("Blocked:", "Error:")) else "completed",
        )
        state["messages"].append(AIMessage(content=result))
        return state


def running_store(tmp_path: Path, task_id: str) -> TaskStore:
    store = TaskStore.create(tmp_path / "output", task_id, tmp_path)
    store.transition("decomposing")
    store.transition("running")
    return store


def close(orchestrator: ApprovalGraph) -> None:
    if orchestrator._checkpointer is not None:
        orchestrator._checkpointer.conn.close()


def test_approval_resumes_after_process_recreation_and_executes_once(tmp_path: Path) -> None:
    store = running_store(tmp_path, "task-approved")
    marker = tmp_path / "approved.txt"
    config = {"configurable": {"thread_id": "task-approved"}}
    first = ApprovalGraph(store, marker)

    interrupted = first._get_graph().invoke(
        first.create_initial_state("task-approved", [subtask()]),
        config=config,
    )

    assert interrupted["__interrupt__"][0].value["request_id"]
    request = store.read().active_approval
    assert request is not None
    assert store.read().status == "waiting_approval"
    assert not marker.exists()
    close(first)

    decision = ApprovalStore(store).decide(request.request_id, approved=True)
    recreated = ApprovalGraph(store, marker)
    completed = recreated._get_graph().invoke(
        Command(resume=decision.model_dump(mode="json")),
        config=config,
    )

    assert completed["status"] == "completed"
    assert store.read().status == "running"
    assert marker.read_text(encoding="utf-8").splitlines() == ["executed"]
    close(recreated)


def test_rejection_resumes_to_blocked_without_tool_execution(tmp_path: Path) -> None:
    store = running_store(tmp_path, "task-rejected")
    marker = tmp_path / "rejected.txt"
    config = {"configurable": {"thread_id": "task-rejected"}}
    first = ApprovalGraph(store, marker)
    first._get_graph().invoke(
        first.create_initial_state("task-rejected", [subtask()]),
        config=config,
    )
    request = store.read().active_approval
    assert request is not None
    close(first)

    decision = ApprovalStore(store).decide(request.request_id, approved=False)
    recreated = ApprovalGraph(store, marker)
    result = recreated._get_graph().invoke(
        Command(resume=decision.model_dump(mode="json")),
        config=config,
    )

    assert result["status"] == "failed"
    assert store.read().status == "blocked"
    assert not marker.exists()
    close(recreated)
