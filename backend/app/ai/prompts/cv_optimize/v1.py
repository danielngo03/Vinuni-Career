# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: optimize_cv_for_job — tailor a CV to a target job (truth-preserving).
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``optimize_cv_for_job`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: SUGGEST how to optimize the CV for the job posting in CONTEXT: re-order "
    "sections by relevance, improve the wording, and list TRUE information that is "
    "still missing so the user can add it themselves. Never fabricate experience, "
    "skills, or achievements to match the posting."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
