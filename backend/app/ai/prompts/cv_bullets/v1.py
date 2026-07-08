# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: generate_cv_bullets — turn the student's raw notes into CV bullets.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``generate_cv_bullets`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: turn the user's RAW NOTES (in CONTEXT) into CV bullet points using an "
    "Action - Result structure. Use only the information present in the notes. Do "
    "not invent achievement figures or outcomes that were not stated."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
