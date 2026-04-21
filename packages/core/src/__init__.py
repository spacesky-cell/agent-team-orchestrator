"""Agent Team Orchestrator - Core Python package."""

__version__ = "0.1.0"

# Lazy imports - these are only loaded when actually used
# This prevents circular import issues and reduces initial load time

def _get_orchestrator_classes():
    """Lazy load orchestrator classes."""
    from .orchestrator import (
        BaseGraphOrchestrator,
        GraphOrchestrator,
        ParallelGraphOrchestrator,
        PersistentGraphOrchestrator,
        SimpleOrchestrator,
        ToolEnabledOrchestrator,
    )
    return {
        "BaseGraphOrchestrator": BaseGraphOrchestrator,
        "SimpleOrchestrator": SimpleOrchestrator,
        "GraphOrchestrator": GraphOrchestrator,
        "ParallelGraphOrchestrator": ParallelGraphOrchestrator,
        "PersistentGraphOrchestrator": PersistentGraphOrchestrator,
        "ToolEnabledOrchestrator": ToolEnabledOrchestrator,
    }

def _get_model_classes():
    """Lazy load model classes."""
    from .models import (
        Deliverable,
        LLMConfig,
        Role,
        RoleLoader,
        Subtask,
        SubtaskDef,
        TaskDecomposition,
        TaskResult,
        TeamState,
        get_llm_provider,
    )
    return {
        "Role": Role,
        "Deliverable": Deliverable,
        "RoleLoader": RoleLoader,
        "Subtask": Subtask,
        "TaskDecomposition": TaskDecomposition,
        "TaskResult": TaskResult,
        "TeamState": TeamState,
        "SubtaskDef": SubtaskDef,
        "LLMConfig": LLMConfig,
        "get_llm_provider": get_llm_provider,
    }

def _get_prompt_classes():
    """Lazy load prompt classes."""
    from .prompts import TaskDecomposer, TaskDecompositionResult
    return {
        "TaskDecomposer": TaskDecomposer,
        "TaskDecompositionResult": TaskDecompositionResult,
    }

def _get_visualization_classes():
    """Lazy load visualization classes."""
    from .visualization import MermaidVisualizer, generate_execution_report
    return {
        "MermaidVisualizer": MermaidVisualizer,
        "generate_execution_report": generate_execution_report,
    }

def _get_memory_classes():
    """Lazy load memory classes."""
    from .memory import CodeChange, DecisionRecord, TeamMemory
    return {
        "TeamMemory": TeamMemory,
        "DecisionRecord": DecisionRecord,
        "CodeChange": CodeChange,
    }

def _get_tool_functions():
    """Lazy load tool functions."""
    from .tools import get_all_tools, get_code_tools, get_file_tools
    return {
        "get_all_tools": get_all_tools,
        "get_file_tools": get_file_tools,
        "get_code_tools": get_code_tools,
    }

# Create a module-like accessor
class _LazyModule:
    """Lazy module accessor."""

    def __getattr__(self, name: str):
        # Try each category
        for getter in [_get_orchestrator_classes, _get_model_classes,
                      _get_prompt_classes, _get_visualization_classes,
                      _get_memory_classes, _get_tool_functions]:
            items = getter()
            if name in items:
                return items[name]
        raise AttributeError(f"module 'src' has no attribute '{name}'")

# Create the lazy accessor
_lazy = _LazyModule()

# Export everything through lazy accessor for package-level imports
__all__ = [
    # Models
    "Role",
    "Deliverable",
    "RoleLoader",
    "Subtask",
    "TaskDecomposition",
    "TaskResult",
    "TeamState",
    "SubtaskDef",
    "LLMConfig",
    "get_llm_provider",
    # Orchestrators
    "SimpleOrchestrator",
    "GraphOrchestrator",
    "ParallelGraphOrchestrator",
    "PersistentGraphOrchestrator",
    "ToolEnabledOrchestrator",
    # Prompts
    "TaskDecomposer",
    "TaskDecompositionResult",
    # Visualization
    "MermaidVisualizer",
    "generate_execution_report",
    # Memory
    "TeamMemory",
    "DecisionRecord",
    "CodeChange",
    # Tools
    "get_all_tools",
    "get_file_tools",
    "get_code_tools",
]
