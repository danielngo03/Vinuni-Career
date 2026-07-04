"""Shared models for AI assistant domain agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AgentAction = Literal["reply", "tool"]


@dataclass(frozen=True)
class AgentPlan:
    """A deterministic plan produced before the LLM fallback.

    The chat service executes the plan. Mutating tools are still guarded by
    the tool registry and require explicit user confirmation.
    """

    agent: str
    action: AgentAction
    status_code: str
    reply: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ConversationEntity:
    """A structured entity recovered from hidden tool-result memory."""

    kind: Literal["job", "company", "event", "cv"]
    id: str | None
    label: str
    url: str | None = None
    source_tool: str | None = None
    position: int = 1
