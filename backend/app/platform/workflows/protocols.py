from __future__ import annotations

from typing import Protocol


class WorkflowDispatcher(Protocol):
    """Application-facing port for durable background workflow submission."""

    def dispatch_ai_run(self, run_id: str) -> None: ...
