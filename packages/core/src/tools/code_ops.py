"""Code operation tools for agents to search and analyze code."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any, ClassVar, Dict, List

from .base import BaseTool


# Allowed directories for code operations
ALLOWED_DIRS = [Path.cwd()]


def _is_path_allowed(path: Path) -> bool:
    """Check if path is within allowed directories."""
    path = path.resolve()
    for allowed_dir in ALLOWED_DIRS:
        try:
            path.relative_to(allowed_dir)
            return True
        except ValueError:
            continue
    return False


class SearchCodeTool(BaseTool):
    """Search code tool using ripgrep or grep.

    Allows agents to search for patterns in codebase.
    """

    name: ClassVar[str] = "search_code"
    description: ClassVar[str] = (
        "Search for patterns in code files. "
        "Use this to find specific functions, classes, or code patterns."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "search_code",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (regex pattern)"
            },
            "path": {
                "type": "string",
                "default": ".",
                "description": "Directory to search in"
            },
            "file_pattern": {
                "type": "string",
                "default": "*",
                "description": "File pattern to search (e.g., '*.py', '*.ts')"
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False,
                "description": "Case-sensitive search"
            },
            "max_results": {
                "type": "integer",
                "default": 50,
                "description": "Maximum results to return"
            }
        },
        "required": ["query"]
    }

    async def execute(self, **kwargs) -> str:
        """Search for patterns in code.

        Args:
            query: Search pattern (regex supported).
            path: Directory to search in.
            file_pattern: File pattern filter.
            case_sensitive: Whether search is case-sensitive.
            max_results: Maximum number of results.

        Returns:
            Search results as formatted string.
        """
        query = kwargs.get("query", "")
        path = kwargs.get("path", ".")
        file_pattern = kwargs.get("file_pattern", "*")
        case_sensitive = kwargs.get("case_sensitive", False)
        max_results = kwargs.get("max_results", 50)

        search_path = Path(path).resolve()

        # Security check
        if not _is_path_allowed(search_path):
            return f"Error: Access denied - {search_path} is outside allowed directories"

        # Try ripgrep first (faster)
        try:
            return await self._search_with_ripgrep(
                query, search_path, file_pattern, case_sensitive, max_results
            )
        except FileNotFoundError:
            # Fallback to Python-based search
            return self._search_with_python(
                query, search_path, file_pattern, case_sensitive, max_results
            )

    async def _search_with_ripgrep(
        self,
        query: str,
        path: Path,
        file_pattern: str,
        case_sensitive: bool,
        max_results: int,
    ) -> str:
        """Search using ripgrep (rg)."""
        cmd = [
            "rg",
            "-n",  # Show line numbers
            "-C", "2",  # Show 2 lines of context
            "--color=never",  # No colors
        ]

        if not case_sensitive:
            cmd.append("-i")  # Case insensitive

        if file_pattern != "*":
            cmd.extend(["-g", file_pattern])

        cmd.extend([query, str(path)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return "Error: Search timed out after 30 seconds"

        if result.returncode not in (0, 1):
            return f"Error: ripgrep failed - {result.stderr}"

        if not result.stdout:
            return "No matches found."

        lines = result.stdout.strip().split("\n")
        if len(lines) > max_results:
            lines = lines[:max_results]
            lines.append(f"... (truncated, {len(result.stdout.splitlines())} total results)")

        return "\n".join(lines)

    def _search_with_python(
        self,
        query: str,
        path: Path,
        file_pattern: str,
        case_sensitive: bool,
        max_results: int,
    ) -> str:
        """Fallback Python-based search."""
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(query, flags)
        except re.error as e:
            return f"Error: Invalid regex pattern - {str(e)}"

        results = []
        glob_pattern = f"**/{file_pattern}"

        for file_path in path.glob(glob_pattern):
            if not file_path.is_file():
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        rel_path = file_path.relative_to(path)
                        results.append(f"{rel_path}:{line_num}: {line.strip()}")

                        if len(results) >= max_results:
                            break
            except Exception:
                continue

            if len(results) >= max_results:
                break

        if not results:
            return "No matches found."

        return "\n".join(results)


class ExecuteCommandTool(BaseTool):
    """Execute shell command tool with safety restrictions.

    WARNING: This tool has security implications. Use with caution.
    """

    name: ClassVar[str] = "execute_command"
    description: ClassVar[str] = (
        "Execute a shell command. "
        "WARNING: Use with caution. Some commands are blocked for safety."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Command to execute"
            },
            "cwd": {
                "type": "string",
                "default": ".",
                "description": "Working directory"
            },
            "timeout": {
                "type": "integer",
                "default": 60,
                "description": "Timeout in seconds"
            },
            "safe_mode": {
                "type": "boolean",
                "default": True,
                "description": "Enable safe mode (blocks dangerous commands)"
            }
        },
        "required": ["command"]
    }

    # Blocked commands for safety
    BLOCKED_PATTERNS: ClassVar[List[str]] = [
        r"rm\s+-rf\s+/",
        r"sudo\s+",
        r"chmod\s+777",
        r">\s*/dev/",
        r"mkfs",
        r"dd\s+if=",
        r":()\s*{\s*:\|:&\s*}",  # Fork bomb
        r"curl.*\|\s*bash",
        r"wget.*\|\s*bash",
    ]

    async def execute(self, **kwargs) -> str:
        """Execute a shell command.

        Args:
            command: Command to execute.
            cwd: Working directory.
            timeout: Timeout in seconds.
            safe_mode: Enable safety checks.

        Returns:
            Command output.
        """
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", ".")
        timeout = kwargs.get("timeout", 60)
        safe_mode = kwargs.get("safe_mode", True)

        # Safety check
        if safe_mode:
            for pattern in self.BLOCKED_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    return f"Error: Command blocked for safety - contains pattern '{pattern}'"

        work_dir = Path(cwd).resolve()

        # Security check
        if not _is_path_allowed(work_dir):
            return f"Error: Access denied - {work_dir} is outside allowed directories"

        try:
            # Run command in asyncio thread pool for non-blocking execution
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=work_dir,
                    timeout=timeout,
                )
            )

            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(f"[stderr]: {result.stderr}")

            output.append(f"[exit code: {result.returncode}]")

            return "\n".join(output)
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"


class AnalyzeFileTool(BaseTool):
    """Analyze file structure tool.

    Provides metadata about a file (size, lines, encoding, etc.).
    """

    name: ClassVar[str] = "analyze_file"
    description: ClassVar[str] = (
        "Analyze a file's structure and metadata. "
        "Returns size, line count, language, and other info."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to file to analyze"
            }
        },
        "required": ["path"]
    }

    async def execute(self, **kwargs) -> str:
        """Analyze a file.

        Args:
            path: Path to file.

        Returns:
            File analysis string.
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

        # Get basic stats
        stat = file_path.stat()
        size_kb = stat.st_size / 1024

        # Try to detect language from extension
        ext_to_lang = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".js": "JavaScript",
            ".tsx": "TypeScript React",
            ".jsx": "JavaScript React",
            ".go": "Go",
            ".java": "Java",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".php": "PHP",
            ".c": "C",
            ".cpp": "C++",
            ".h": "C/C++ Header",
            ".md": "Markdown",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".toml": "TOML",
            ".sql": "SQL",
            ".html": "HTML",
            ".css": "CSS",
            ".scss": "SCSS",
        }

        language = ext_to_lang.get(file_path.suffix.lower(), "Unknown")

        # Try to count count lines
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = len(content.splitlines())
            encoding = "utf-8"
        except Exception:
            lines = "Unknown"
            encoding = "Unknown"

        return (
            f"File: {file_path}\n"
            f"Language: {language}\n"
            f"Size: {size_kb:.2f} KB\n"
            f"Lines: {lines}\n"
            f"Encoding: {encoding}\n"
            f"Modified: {stat.st_mtime}"
        )


class RunTestsTool(BaseTool):
    """Run test suite tool.

    Automatically detects and runs appropriate test framework.
    """

    name: ClassVar[str] = "run_tests"
    description: ClassVar[str] = (
        "Run the project's test suite. "
        "Automatically detects pytest, unittest, or npm test."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": ".",
                "description": "Project directory to run tests in"
            },
            "test_path": {
                "type": "string",
                "description": "Specific test file or pattern to run"
            },
            "verbose": {
                "type": "boolean",
                "default": False,
                "description": "Enable verbose output"
            }
        },
        "required": []
    }

    async def execute(self, **kwargs) -> str:
        """Run test suite.

        Args:
            path: Project directory.
            test_path: Specific test to run.
            verbose: Enable verbose output.

        Returns:
            Test results.
        """
        path = kwargs.get("path", ".")
        test_path = kwargs.get("test_path")
        verbose = kwargs.get("verbose", False)

        work_dir = Path(path).resolve()

        # Security check
        if not _is_path_allowed(work_dir):
            return f"Error: Access denied - {work_dir} is outside allowed directories"

        # Detect test framework
        framework = self._detect_test_framework(work_dir)

        if not framework:
            return "No test framework detected. Looked for: pytest.ini, pyproject.toml (pytest), package.json (npm)"

        # Build command
        cmd = []
        if framework == "pytest":
            cmd = ["python", "-m", "pytest"]
            if verbose:
                cmd.append("-v")
            if test_path:
                cmd.append(test_path)
        elif framework == "unittest":
            cmd = ["python", "-m", "unittest"]
            if verbose:
                cmd.append("-v")
            if test_path:
                cmd.append(test_path)
        elif framework == "npm":
            cmd = ["npm", "test"]
            if test_path:
                cmd.append("--")
                cmd.append(test_path)

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=work_dir,
                    timeout=120,  # Longer timeout for tests
                )
            )

            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(f"[stderr:]\n{result.stderr}")

            output.append(f"\n[exit code: {result.returncode}]")

            return f"Running {framework}:\n" + "\n".join(output)
        except subprocess.TimeoutExpired:
            return f"Error: Tests timed out after 120 seconds"
        except Exception as e:
            return f"Error running tests: {str(e)}"

    def _detect_test_framework(self, path: Path) -> str | None:
        """Detect which test framework to use."""
        # Check for pytest
        if (path / "pytest.ini").exists():
            return "pytest"
        if (path / "pyproject.toml").exists():
            try:
                import tomli
                with open(path / "pyproject.toml", "rb") as f:
                    config = tomli.load(f)
                    if "tool" in config and "pytest" in config["tool"]:
                        return "pytest"
            except ImportError:
                # Can't parse toml, check via grep
                try:
                    content = (path / "pyproject.toml").read_text()
                    if "pytest" in content:
                        return "pytest"
                except Exception:
                    pass

        # Check for unittest (has test files with unittest imports)
        for test_file in path.rglob("test_*.py"):
            try:
                content = test_file.read_text()
                if "import unittest" in content or "from unittest" in content:
                    return "unittest"
            except Exception:
                pass

        # Check for npm tests
        if (path / "package.json").exists():
            try:
                import json
                with open(path / "package.json") as f:
                    pkg = json.load(f)
                    if "scripts" in pkg and "test" in pkg["scripts"]:
                        return "npm"
            except Exception:
                pass

        return None


class GitCommitTool(BaseTool):
    """Git commit tool.

    Creates a git commit with optional approval requirement.
    """

    name: ClassVar[str] = "git_commit"
    description: ClassVar[str] = (
        "Create a git commit with the current changes. "
        "Requires staging files before use."
    )
    parameters: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Commit message"
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "Only show what would be committed, don't actually commit"
            }
        },
        "required": ["message"]
    }

    async def execute(self, **kwargs) -> str:
        """Create a git commit.

        Args:
            message: Commit message.
            dry_run: Dry run mode.

        Returns:
            Commit result or dry run info.
        """
        message = kwargs.get("message", "")
        dry_run = kwargs.get("dry_run", False)

        # Check if we're in a git repo
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "Error: Not in a git repository"

        # Check if there are staged changes
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if not result.stdout.strip():
                return "Error: No staged changes. Use 'git add' to stage files first."
        except Exception as e:
            return f"Error checking staged changes: {str(e)}"

        if dry_run:
            # Show staged files
            try:
                result = subprocess.run(
                    ["git", "diff", "--cached", "--stat"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return f"[Dry run] Would commit with message:\n{message}\n\nStaged changes:\n{result.stdout}"
            except Exception as e:
                return f"Error in dry run: {str(e)}"

        # Create commit
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "commit", "-m", message],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            )

            if result.returncode == 0:
                # Get the commit hash
                hash_result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                commit_hash = hash_result.stdout.strip()

                return f"✓ Commit created: {commit_hash}\nMessage: {message}"
            else:
                return f"Error: Commit failed\n{result.stderr}"
        except Exception as e:
            return f"Error creating commit: {str(e)}"


# Factory function
def get_code_tools() -> list[BaseTool]:
    """Get all code operation tools.

    Returns:
        List of code tool instances.
    """
    return [
        SearchCodeTool(),
        ExecuteCommandTool(),
        AnalyzeFileTool(),
        RunTestsTool(),
        GitCommitTool(),
    ]
