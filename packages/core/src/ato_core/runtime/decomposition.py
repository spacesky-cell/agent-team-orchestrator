"""Validation for LLM-produced task dependency graphs."""

from collections import Counter, deque
from typing import Any, Iterable


class InvalidDecompositionError(ValueError):
    """A decomposition cannot be executed safely."""

    code = "INVALID_DECOMPOSITION"


def _error(message: str) -> InvalidDecompositionError:
    return InvalidDecompositionError(f"INVALID_DECOMPOSITION: {message}")


def validate_decomposition(
    subtasks: list[dict[str, Any]],
    *,
    available_roles: set[str] | Iterable[str],
) -> list[dict[str, Any]]:
    """Validate identifiers, roles, dependencies, and acyclicity."""
    if not subtasks:
        raise _error("at least one subtask is required")

    ids = [str(item.get("id", "")).strip() for item in subtasks]
    if any(not subtask_id for subtask_id in ids):
        raise _error("subtask IDs must be non-empty")

    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise _error(f"duplicate subtask IDs: {', '.join(duplicates)}")

    role_set = set(available_roles)
    unknown_roles = sorted(
        {str(item.get("role", "")) for item in subtasks if item.get("role") not in role_set}
    )
    if unknown_roles:
        raise _error(f"unknown roles: {', '.join(unknown_roles)}")

    id_set = set(ids)
    dependencies: dict[str, list[str]] = {
        subtask_id: [str(value) for value in item.get("dependencies", [])]
        for subtask_id, item in zip(ids, subtasks)
    }
    unknown_dependencies = sorted(
        {
            dependency
            for values in dependencies.values()
            for dependency in values
            if dependency not in id_set
        }
    )
    if unknown_dependencies:
        raise _error(f"unknown dependencies: {', '.join(unknown_dependencies)}")

    self_dependencies = sorted(
        subtask_id for subtask_id, values in dependencies.items() if subtask_id in values
    )
    if self_dependencies:
        raise _error(f"self dependencies: {', '.join(self_dependencies)}")

    indegree = {subtask_id: len(values) for subtask_id, values in dependencies.items()}
    dependents: dict[str, list[str]] = {subtask_id: [] for subtask_id in ids}
    for subtask_id, values in dependencies.items():
        for dependency in values:
            dependents[dependency].append(subtask_id)

    ready = deque(subtask_id for subtask_id in ids if indegree[subtask_id] == 0)
    visited: list[str] = []
    while ready:
        current = ready.popleft()
        visited.append(current)
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if len(visited) != len(ids):
        cycle = sorted(subtask_id for subtask_id, degree in indegree.items() if degree > 0)
        raise _error(f"dependency cycle: {', '.join(cycle)}")

    return subtasks
