# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: cv_fabrication_check — flag CV claims unsupported by evidence.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``cv_fabrication_check`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: CHECK the claims in the CV and flag any claim that is NOT supported by "
    "evidence in CONTEXT (profile, CV extraction). This is a safety check: only "
    "list claims that need confirmation; do not edit the CV yourself."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
