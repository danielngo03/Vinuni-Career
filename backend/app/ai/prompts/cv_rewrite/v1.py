# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: rewrite_cv_section — polish an existing CV section without adding facts.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``rewrite_cv_section`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: REWRITE the CV section in CONTEXT to be clear, concise, and "
    "professional. Keep EVERY fact unchanged (organization names, titles, dates, "
    "numbers). Do not add new information. Only improve the wording."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
