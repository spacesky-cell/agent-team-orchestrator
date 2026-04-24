"""File operation tools for agents to interact with the filesystem."""

from pathlib import Path
from typing import Any, ClassVar, Dict

from .base import BaseTool

# Security: Limit operations to specific directories
ALLOWED_DIRS = [
    Path.cwd(),  # Current working directory
]

# Maximum file size to read (1MB)
MAX_FILE_SIZE = 1024 * 1024


def _is_path_allowed(path: Path) -> bool:
    """Check if a path is within allowed directories.

    Args:
        path: Path to check.

    Returns:
        True if path is within allowed directories.
    """
    path = path.resolve()
    for allowed_dir in ALLOWED_DIRS:
        try:
            path.relative_to(allowed_dir)
            return True
        except ValueError:
            continue
    return False


class ReadFileTool(BaseTool):
    """Read file content tool.

    Allows agents to read files within the project directory.
    Supports reading specific line ranges for large files.
    """

    name: ClassVar[str] = "read_file"
    description: ClassVar[str] = (
        "Read the contents of a file. Use this to examine existing code, config files, etc. "
        "Supports optional start_line and end_line parameters for reading specific ranges."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "encoding": {"type": "string", "default": "utf-8", "description": "File encoding"},
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed, optional)",
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (1-indexed, optional)",
            },
        },
        "required": ["path"],
    }

    async def execute(self, **kwargs) -> str:
        """Read file content.

        Args:
            path: Path to the file to read.
            encoding: File encoding (default utf-8).
            start_line: Optional starting line number (1-indexed).
            end_line: Optional ending line number (1-indexed).

        Returns:
            File contents.
        """
        path = kwargs.get("path")
        encoding = kwargs.get("encoding", "utf-8")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")

        file_path = Path(path).resolve()

        # Security check
        if not _is_path_allowed(file_path):
            return f"Error: Access denied - {file_path} is outside allowed directories"

        # Check existence
        if not file_path.exists():
            return f"Error: File not found - {file_path}"

        if not file_path.is_file():
            return f"Error: Not a file - {file_path}"

        # Check size
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return f"Error: File too large ({file_path.stat().st_size} bytes, max {MAX_FILE_SIZE})"

        # Read content
        try:
            with open(file_path, "r", encoding=encoding) as f:
                if start_line is not None or end_line is not None:
                    lines = f.readlines()
                    start = (start_line or 1) - 1  # Convert to 0-indexed
                    end = end_line or len(lines)
                    content = "".join(lines[start:end])
                else:
                    content = f.read()

            # Prepend line numbers
            lines = content.splitlines(keepends=True)
            numbered = ""
            for i, line in enumerate(lines, start=(start_line or 1)):
                numbered += f"{i:6d}\t{line}"

            return numbered if numbered else content
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(BaseTool):
    """Write file content tool.

    Allows agents to create or update files.
    """

    name: ClassVar[str] = "write_file"
    description: ClassVar[str] = (
        "Write content to a file. Use this to create new files or update existing ones. "
        "Automatically creates parent directories if they don't exist."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
            "encoding": {"type": "string", "default": "utf-8", "description": "File encoding"},
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "default": "write",
                "description": "Write mode: 'write' to overwrite, 'append' to add to end",
            },
        },
        "required": ["path", "content"],
    }

    async def execute(self, **kwargs) -> str:
        """Write content to file.

        Args:
            path: Path to the file to write.
            content: Content to write.
            encoding: File encoding (default utf-8).
            mode: Write mode - 'write' to overwrite, 'append' to add.

        Returns:
            Success message or error.
        """
        path = kwargs.get("path")
        content = kwargs.get("content", "")
        encoding = kwargs.get("encoding", "utf-8")
        mode = kwargs.get("mode", "write")

        file_path = Path(path).resolve()

        # Security check
        if not _is_path_allowed(file_path):
            return f"Error: Access denied - {file_path} is outside allowed directories"

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        try:
            write_mode = "a" if mode == "append" else "w"
            with open(file_path, write_mode, encoding=encoding) as f:
                f.write(content)

            action = "Appended to" if mode == "append" else "Wrote"
            return f"{action} {file_path} ({len(content)} characters)"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class ListDirectoryTool(BaseTool):
    """List directory contents tool.

    Allows agents to explore the file system structure.
    """

    name: ClassVar[str] = "list_directory"
    description: ClassVar[str] = (
        "List files and directories. Use this to explore the project structure. "
        "Supports recursive listing and pattern filtering."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": ".",
                "description": "Path to the directory to list",
            },
            "recursive": {"type": "boolean", "default": False, "description": "List recursively"},
            "pattern": {"type": "string", "description": "Filter by glob pattern (e.g., '*.py')"},
        },
        "required": [],
    }

    async def execute(self, **kwargs) -> str:
        """List directory contents.

        Args:
            path: Path to list.
            recursive: Whether to list recursively.
            pattern: Optional glob pattern to filter.

        Returns:
            Directory listing.
        """
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        pattern = kwargs.get("pattern")

        dir_path = Path(path).resolve()

        # Security check
        if not _is_path_allowed(dir_path):
            return f"Error: Access denied - {dir_path} is outside allowed directories"

        if not dir_path.exists():
            return f"Error: Directory not found - {dir_path}"

        if not dir_path.is_dir():
            return f"Error: Not a directory - {dir_path}"

        # Get files
        try:
            if recursive:
                glob_pattern = "**/*" if not pattern else f"**/{pattern}"
                files = sorted(dir_path.glob(glob_pattern))
            else:
                files = sorted(dir_path.iterdir())
                if pattern:
                    files = [f for f in files if f.match(pattern)]

            # Format output
            lines = []
            for f in files:
                if f.is_dir():
                    prefix = "📁 "
                else:
                    prefix = "📄 "
                relative_path = f.relative_to(dir_path)
                lines.append(f"{prefix}{relative_path}")

            return "\n".join(lines) if lines else "Directory is empty"
        except Exception as e:
            return f"Error listing directory: {str(e)}"


class DeleteFileTool(BaseTool):
    """Delete file tool.

    Allows agents to delete files with safety checks.
    """

    name: ClassVar[str] = "delete_file"
    description: ClassVar[str] = (
        "Delete a file. Use with caution - this operation cannot be undone."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to the file to delete"}},
        "required": ["path"],
    }

    async def execute(self, **kwargs) -> str:
        """Delete a file.

        Args:
            path: Path to the file to delete.

        Returns:
            Success message or error.
        """
        path = kwargs.get("path")
        file_path = Path(path).resolve()

        # Security check
        if not _is_path_allowed(file_path):
            return f"Error: Access denied - {file_path} is outside allowed directories"

        if not file_path.exists():
            return f"Error: File not found - {file_path}"

        if not file_path.is_file():
            return f"Error: Not a file - {file_path}"

        try:
            file_path.unlink()
            return f"Deleted: {file_path}"
        except Exception as e:
            return f"Error deleting file: {str(e)}"


# Factory function
def get_file_tools() -> list[BaseTool]:
    """Get all file operation tools.

    Returns:
        List of file tool instances.
    """
    return [
        ReadFileTool(),
        WriteFileTool(),
        ListDirectoryTool(),
        DeleteFileTool(),
    ]
