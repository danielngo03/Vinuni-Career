# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: ats_keyword_suggestions — keyword coverage advice (read-only).
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``ats_keyword_suggestions`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: compare the keywords in the job description against the CV content and "
    "SUGGEST important keywords that are missing. This is ADVISORY only: do not "
    "edit the CV and do not assert that the user has a skill they have not shown."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
