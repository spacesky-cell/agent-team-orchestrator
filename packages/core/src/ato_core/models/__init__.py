"""Lazy public model exports for fast bridge startup."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "Role": (".role", "Role"),
    "Deliverable": (".role", "Deliverable"),
    "RoleLoader": (".role", "RoleLoader"),
    "Subtask": (".task", "Subtask"),
    "TaskDecomposition": (".task", "TaskDecomposition"),
    "TaskResult": (".task", "TaskResult"),
    "TeamState": (".state", "TeamState"),
    "SubtaskDef": (".state", "SubtaskDef"),
    "LLMConfig": (".llm_provider", "LLMConfig"),
    "get_llm_provider": (".llm_provider", "get_llm_provider"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    return getattr(import_module(module_name, __name__), attribute)
