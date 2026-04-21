"""Mermaid diagram generation for task execution visualization."""

from typing import Literal


# Valid task statuses
TaskStatus = Literal["pending", "running", "completed", "failed"]


# Color mapping for statuses
STATUS_COLORS = {
    "pending": "#9CA3AF",    # Gray-purple
    "running": "#3B82F6",    # Blue
    "completed": "#10B981",   # Green
    "failed": "#EF4444",      # Red
}

# Node style mapping
STATUS_STYLES = {
    "pending": "fill:#9CA3AF,stroke:#6B7280,color:#000000",
    "running": "fill:#3B82F6,stroke:#1D4ED8,color:#FFFFFF",
    "completed": "fill:#10B981,stroke:#047857,color:#FFFFFF",
    "failed": "fill:#EF4444,stroke:#B91C1C,color:#FFFFFF",
}


def generate_mermaid_dag(
    subtasks: list[dict],
    layout: str = "TD",
    show_status: bool = False,
) -> str:
    """Generate Mermaid DAG diagram from subtask definitions.

    Args:
        subtasks: List of subtask dictionaries.
        layout: Graph layout direction (TD=top-down, LR=left-right, TB, BT, RL).
        show_status: Whether to show status in node labels.

    Returns:
        Mermaid diagram code as string.
    """
    lines = [f"graph {layout}"]

    # Define nodes
    for subtask in subtasks:
        node_id = subtask["id"]
        name = subtask["name"]
        status = subtask.get("status", "pending")
        role = subtask.get("role", "unknown")

        # Build node label
        if show_status:
            label = f"{name}\\n({role})\\n[{status}]"
        else:
            label = f"{name}\\n({role})"

        # Get style based on status
        style = STATUS_STYLES.get(status, STATUS_STYLES["pending"])

        # Format: node_id["label"]{style}
        lines.append(f'    {node_id}["{label}"]{{{style}}}')

    # Add blank line
    lines.append("")

    # Define edges (dependencies)
    for subtask in subtasks:
        node_id = subtask["id"]
        dependencies = subtask.get("dependencies", [])

        for dep_id in dependencies:
            # Edge: dep_id --> node_id
            lines.append(f"    {dep_id} --> {node_id}")

    return "\n".join(lines)


def generate_mermaid_timeline(
    subtasks: list[dict],
    task_name: str = "Task Execution",
) -> str:
    """Generate Mermaid timeline diagram from subtasks.

    Args:
        subtasks: List of subtask dictionaries with status.
        task_name: Name of the overall task.

    Returns:
        Mermaid timeline code as string.
    """
    lines = ["gantt"]
    lines.append(f"    title {task_name}")
    lines.append("    dateFormat  HH:mm:ss")

    # Group by role
    roles = {}
    for subtask in subtasks:
        role = subtask.get("role", "unknown")
        if role not in roles:
            roles[role] = []
        roles[role].append(subtask)

    # Add sections and tasks
    for role, tasks in roles.items():
        lines.append(f"    section {role.replace('-', ' ').title()}")
        for i, task in enumerate(tasks):
            name = task["name"]
            status = task.get("status", "pending")
            duration = "1s"  # Simplified for visualization

            # Status-based styling
            if status == "completed":
                task_line = f"    done  :{name}, {duration}"
            elif status == "failed":
                task_line = f"    crit  :{name}, {duration}"
            elif status == "running":
                task_line = f"    active  :{name}, {duration}"
            else:
                task_line = f"    {name}, {duration}"

            lines.append(task_line)

    return "\n".join(lines)


def generate_mermaid_state_diagram(
    task_id: str,
    status: str,
    current_subtasks: list[str],
    total_subtasks: int,
    completed_count: int,
) -> str:
    """Generate Mermaid state diagram for current execution state.

    Args:
        task_id: Task identifier.
        status: Current task status (pending, running, completed, failed).
        current_subtasks: List of currently executing subtask IDs.
        total_subtasks: Total number of subtasks.
        completed_count: Number of completed subtasks.

    Returns:
        Mermaid state diagram code.
    """
    lines = ["stateDiagram-v2"]
    lines.append(f"    [*] --> {status}")

    # Add status transitions
    if status == "pending":
        lines.append("    pending --> running")
        lines.append("    running --> completed")
        lines.append("    running --> failed")

    # Add progress note
    lines.append("")
    lines.append(f"    note right of {status}")
    lines.append(f"        Task: {task_id}")
    lines.append(f"        Progress: {completed_count}/{total_subtasks}")

    if current_subtasks:
        lines.append(f"        Running: {', '.join(current_subtasks)}")

    lines.append("    end note")

    return "\n".join(lines)


def generate_execution_report(
    task_id: str,
    subtasks: list[dict],
    artifacts: dict[str, object] | None = None,
) -> str:
    """Generate a Markdown execution report with visualizations.

    Args:
        task_id: Task identifier.
        subtasks: List of subtask definitions with status.
        artifacts: Dictionary of subtask outputs (optional).

    Returns:
        Markdown-formatted execution report.
    """
    lines = [
        f"# Task Execution Report: {task_id}",
        "",
        "## Task Flow",
        "",
        "```mermaid",
        generate_mermaid_dag(subtasks, show_status=True),
        "```",
        "",
        "## Timeline",
        "",
        "```mermaid",
        generate_mermaid_timeline(subtasks, task_id),
        "```",
        "",
        "## Subtask Details",
        "",
    ]

    # Add subtask details
    for i, subtask in enumerate(subtasks, 1):
        status = subtask.get("status", "pending")
        status_emoji = {
            "completed": "✓",
            "running": "▶",
            "failed": "✗",
            "pending": "○",
        }.get(status, "?")

        lines.append(f"### {i}. {status_emoji} {subtask['name']}")
        lines.append(f"- **Role:** {subtask.get('role', 'unknown')}")
        lines.append(f"- **Status:** {status}")

        if subtask.get("dependencies"):
            lines.append(f"- **Dependencies:** {', '.join(subtask['dependencies'])}")

        lines.append(f"- **Expected Output:** {subtask.get('expected_output', '')}")

        if artifacts and subtask['id'] in artifacts:
            output = str(artifacts[subtask['id']])
            preview = output[:200] + "..." if len(output) > 200 else output
            lines.append(f"- **Output Preview:**")
            lines.append("  ```")
            lines.append(f"  {preview}")
            lines.append("  ```")

        lines.append("")

    # Summary
    completed = sum(1 for st in subtasks if st.get("status") == "completed")
    failed = sum(1 for st in subtasks if st.get("status") == "failed")

    lines.append("## Summary")
    lines.append(f"- **Total Subtasks:** {len(subtasks)}")
    lines.append(f"- **Completed:** {completed}")
    lines.append(f"- **Failed:** {failed}")
    lines.append("- **Overall Status:** " + (
        "✓ Success"
        if failed == 0 and completed == len(subtasks)
        else "✗ Failed" if failed > 0 else "▶ In Progress"
    ))

    return "\n".join(lines)


class MermaidVisualizer:
    """Helper class for generating Mermaid diagrams."""

    @staticmethod
    def dag(subtasks: list[dict], **kwargs) -> str:
        """Generate DAG diagram."""
        return generate_mermaid_dag(subtasks, **kwargs)

    @staticmethod
    def timeline(subtasks: list[dict], task_name: str = "Task") -> str:
        """Generate timeline diagram."""
        return generate_mermaid_timeline(subtasks, task_name)

    @staticmethod
    def state_diagram(**kwargs) -> str:
        """Generate state diagram."""
        return generate_mermaid_state_diagram(**kwargs)

    @staticmethod
    def execution_report(task_id: str, subtasks: list[dict], **kwargs) -> str:
        """Generate full execution report."""
        return generate_execution_report(task_id, subtasks, **kwargs)
