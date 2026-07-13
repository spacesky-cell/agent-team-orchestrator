"""Project-root tool execution tests."""

import asyncio
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def initialize_repo(repo: Path) -> str:
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "ato-test@example.invalid")
    git(repo, "config", "user.name", "ATO Test")
    (repo / "baseline.txt").write_text("baseline", encoding="utf-8")
    git(repo, "add", "baseline.txt")
    git(repo, "commit", "-m", "baseline")
    return git(repo, "rev-parse", "HEAD")


def test_git_commit_changes_only_the_context_repository(tmp_path: Path) -> None:
    from ato_core.tools.base import ToolExecutionContext
    from ato_core.tools.code_ops import GitCommitTool

    first = tmp_path / "first"
    second = tmp_path / "second"
    first_head = initialize_repo(first)
    second_head = initialize_repo(second)
    (second / "change.txt").write_text("change", encoding="utf-8")
    git(second, "add", "change.txt")
    context = ToolExecutionContext(
        task_id="task-a",
        subtask_id="subtask-a",
        project_root=second,
        allowed_dirs=(second,),
    )

    output = asyncio.run(GitCommitTool().execute(context=context, message="target commit"))

    assert not output.startswith("Error:")
    assert git(first, "rev-parse", "HEAD") == first_head
    assert git(second, "rev-parse", "HEAD") != second_head
    assert git(second, "log", "-1", "--pretty=%s") == "target commit"


def test_command_safe_mode_is_not_model_controlled() -> None:
    from ato_core.tools.code_ops import ExecuteCommandTool

    assert "safe_mode" not in ExecuteCommandTool.parameters["properties"]
