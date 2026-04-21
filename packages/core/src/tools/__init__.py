"""Tools module for Agent Team Orchestrator."""

from .base import BaseTool
from .file_ops import (
    ReadFileTool,
    WriteFileTool,
    ListDirectoryTool,
    DeleteFileTool,
    get_file_tools,
)
from .code_ops import (
    SearchCodeTool,
    ExecuteCommandTool,
    AnalyzeFileTool,
    RunTestsTool,
    GitCommitTool,
    get_code_tools,
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
