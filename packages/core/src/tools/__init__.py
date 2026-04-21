"""Tools module for Agent Team Orchestrator."""

from .base import BaseTool
from .code_ops import (
    AnalyzeFileTool,
    ExecuteCommandTool,
    GitCommitTool,
    RunTestsTool,
    SearchCodeTool,
    get_code_tools,
)
from .file_ops import (
    DeleteFileTool,
    ListDirectoryTool,
    ReadFileTool,
    WriteFileTool,
    get_file_tools,
)

__all__ = [
    "BaseTool",
    "ReadFileTool",
    "WriteFileTool",
    "ListDirectoryTool",
    "DeleteFileTool",
    "SearchCodeTool",
    "ExecuteCommandTool",
    "AnalyzeFileTool",
    "RunTestsTool",
    "GitCommitTool",
    "get_file_tools",
    "get_code_tools",
    "get_all_tools",
    "get_tools_for_role",
]


def get_all_tools() -> list[BaseTool]:
    """Get all available tools.

    Returns:
        List of all tool instances.
    """
    return get_file_tools() + get_code_tools()


def get_tools_for_role(role_tools: list[str]) -> list[BaseTool]:
    """Get tools available for a specific role.

    Args:
        role_tools: List of tool names the role has access to.

    Returns:
        List of tool instances available to the role.
    """
    all_tools = {t.name: t for t in get_all_tools()}
    return [all_tools[name] for name in role_tools if name in all_tools]
