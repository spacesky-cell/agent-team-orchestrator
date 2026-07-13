"""Public parallel orchestrator backed by the canonical coordinator."""

from .base_orchestrator import BaseGraphOrchestrator


class ParallelGraphOrchestrator(BaseGraphOrchestrator):
    """Canonical graph orchestrator whose ready tasks execute through Send branches."""
