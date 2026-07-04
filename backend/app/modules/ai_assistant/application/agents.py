"""Backward-compatible facade for AI assistant agentic orchestration."""

from __future__ import annotations

from app.modules.ai_assistant.application.agentic import (  # noqa: F401
    AgentPlan,
    build_agent_plan,
    format_tool_result,
    plan_for_text,
)
