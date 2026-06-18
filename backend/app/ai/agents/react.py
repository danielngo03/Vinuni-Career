from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.ai.agents.runtime import AgentExecutionError, AgentStep

Tool = Callable[[dict[str, Any]], dict[str, Any]]
Planner = Callable[[dict[str, Any], list[AgentStep]], str]


@dataclass(frozen=True)
class ReActResult:
    output: dict[str, Any]
    steps: list[AgentStep]


class BoundedReActRuntime:
    """Auditable action/observation loop with strict tool and step budgets.

    The trace stores concise operational summaries only. It deliberately does
    not persist hidden chain-of-thought or raw model reasoning.
    """

    def __init__(
        self,
        *,
        agent_name: str,
        tools: Mapping[str, Tool],
        planner: Planner,
        max_steps: int = 6,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.agent_name = agent_name
        self.tools = dict(tools)
        self.planner = planner
        self.max_steps = max_steps

    def run(self, payload: dict[str, Any]) -> ReActResult:
        state = dict(payload)
        steps: list[AgentStep] = []
        for sequence in range(1, self.max_steps + 1):
            action = self.planner(state, steps)
            if action == "finish":
                return ReActResult(output=state, steps=steps)
            tool = self.tools.get(action)
            if tool is None:
                raise AgentExecutionError(
                    f"{self.agent_name} selected an unregistered tool: {action}"
                )
            observation = tool(state)
            state.update(observation)
            steps.append(
                AgentStep(
                    sequence=sequence,
                    agent=self.agent_name,
                    action=action,
                    summary=_safe_summary(observation),
                    metadata={"keys": sorted(observation)},
                )
            )
        raise AgentExecutionError(
            f"{self.agent_name} exceeded its {self.max_steps}-step execution budget"
        )


def _safe_summary(observation: dict[str, Any]) -> str:
    summary = observation.get("summary") or observation.get("status")
    if summary:
        return str(summary)[:240]
    return f"Produced: {', '.join(sorted(observation))}"[:240]
