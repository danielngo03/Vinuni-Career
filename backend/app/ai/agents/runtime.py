from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


class AgentExecutionError(RuntimeError):
    """Raised when an agent cannot safely complete its assigned task."""


@dataclass(frozen=True)
class AgentTask:
    task_type: str
    payload: dict[str, Any]
    run_id: str | None = None
    org_id: str | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class AgentStep:
    sequence: int
    agent: str
    action: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResult:
    agent: str
    status: str
    output: dict[str, Any]
    steps: list[AgentStep]
    confidence: float
    requires_human_review: bool = False
    policy_version: str = "ai-policy-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "output": self.output,
            "steps": [
                {
                    "sequence": step.sequence,
                    "agent": step.agent,
                    "action": step.action,
                    "summary": step.summary,
                    "metadata": step.metadata,
                }
                for step in self.steps
            ],
            "confidence": self.confidence,
            "requires_human_review": self.requires_human_review,
            "policy_version": self.policy_version,
        }


AgentHandler = Callable[[AgentTask], AgentResult]


class AgentRegistry:
    """Explicit specialist registry; unknown work is rejected, never guessed."""

    def __init__(self, handlers: Mapping[str, AgentHandler] | None = None) -> None:
        self._handlers = dict(handlers or {})

    def register(self, task_type: str, handler: AgentHandler) -> None:
        if task_type in self._handlers:
            raise ValueError(f"Agent already registered for task type: {task_type}")
        self._handlers[task_type] = handler

    def execute(self, task: AgentTask) -> AgentResult:
        handler = self._handlers.get(task.task_type)
        if handler is None:
            raise AgentExecutionError(f"No specialist agent for task type: {task.task_type}")
        return handler(task)

    @property
    def task_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
