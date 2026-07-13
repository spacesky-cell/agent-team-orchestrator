"""Behavior coverage for concrete filesystem and code tools."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_file_tool_lifecycle_and_error_paths(tmp_path: Path) -> None:
    from ato_core.tools.file_ops import (
        DeleteFileTool,
        ListDirectoryTool,
        ReadFileTool,
        WriteFileTool,
    )

    writer = WriteFileTool([tmp_path])
    reader = ReadFileTool([tmp_path])
    listing = ListDirectoryTool([tmp_path])
    deleter = DeleteFileTool([tmp_path])

    assert await writer.execute() == "Error: path is required"
    note = tmp_path / "note.txt"
    assert "Wrote" in await writer.execute(path=note, content="one\ntwo")
    assert "Appended" in await writer.execute(path=note, content="\nthree", mode="append")
    assert "1\tone" in await reader.execute(path=note, start_line=1, end_line=2)
    assert "note.txt" in await listing.execute(path=tmp_path)
    assert "note.txt" in await listing.execute(path=tmp_path, recursive=True, pattern="*.txt")
    assert "Deleted" in await deleter.execute(path=note)
    assert "File not found" in await reader.execute(path=note)
    assert "File not found" in await deleter.execute(path=note)


@pytest.mark.asyncio
async def test_file_tools_reject_wrong_kinds_and_large_files(tmp_path: Path) -> None:
    from ato_core.tools.file_ops import MAX_FILE_SIZE, ListDirectoryTool, ReadFileTool

    directory = tmp_path / "folder"
    directory.mkdir()
    large = tmp_path / "large.txt"
    large.write_bytes(b"x" * (MAX_FILE_SIZE + 1))

    assert "Not a file" in await ReadFileTool([tmp_path]).execute(path=directory)
    assert "File too large" in await ReadFileTool([tmp_path]).execute(path=large)
    assert "Not a directory" in await ListDirectoryTool([tmp_path]).execute(path=large)
    assert await ReadFileTool([tmp_path]).execute() == "Error: path is required"


@pytest.mark.asyncio
async def test_search_execute_analyze_and_test_tools(tmp_path: Path, monkeypatch) -> None:
    from ato_core.tools.code_ops import (
        AnalyzeFileTool,
        ExecuteCommandTool,
        RunTestsTool,
        SearchCodeTool,
    )

    source = tmp_path / "module.py"
    source.write_text("class Example:\n    pass\n", encoding="utf-8")
    search = SearchCodeTool([tmp_path])
    monkeypatch.setattr(
        "ato_core.tools.code_ops.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert "Example" in await search.execute(query="Example", path=tmp_path, file_pattern="*.py")
    assert "Invalid regex" in await search.execute(query="[", path=tmp_path)

    command = ExecuteCommandTool([tmp_path])
    assert "blocked for safety" in await command.execute(command="sudo echo no", cwd=tmp_path)

    completed = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
    monkeypatch.setattr("ato_core.tools.code_ops.subprocess.run", lambda *args, **kwargs: completed)
    assert "[exit code: 0]" in await command.execute(command="echo ok", cwd=tmp_path)

    analyzer = AnalyzeFileTool([tmp_path])
    assert await analyzer.execute() == "Error: path is required"
    analysis = await analyzer.execute(path=source)
    assert "Language: Python" in analysis
    assert "Lines: 2" in analysis
    assert "Not a file" in await analyzer.execute(path=tmp_path)

    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    runner = RunTestsTool([tmp_path])
    result = await runner.execute(path=tmp_path, test_path="tests", verbose=True)
    assert "Running pytest" in result
    assert "[exit code: 0]" in result


@pytest.mark.asyncio
async def test_run_tests_reports_missing_framework(tmp_path: Path) -> None:
    from ato_core.tools.code_ops import RunTestsTool

    result = await RunTestsTool([tmp_path]).execute(path=tmp_path)
    assert "No test framework detected" in result
