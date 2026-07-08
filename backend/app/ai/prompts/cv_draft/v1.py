# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: draft_cv_from_profile — first CV draft from the student's profile.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``draft_cv_from_profile`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: compose the first CV DRAFT using ONLY the profile data in CONTEXT "
    "(education, experience, skills, notes). Do not add any education, employer, "
    "award, or certification that is not present in the profile."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
