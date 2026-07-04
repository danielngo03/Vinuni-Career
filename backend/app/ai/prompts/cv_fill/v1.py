# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: fill_cv_template_from_sources — fill empty template sections from sources.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for ``fill_cv_template_from_sources`` (v1)."""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: FILL the empty CV sections using data from the SOURCES in CONTEXT "
    "(profile, extraction from an uploaded CV, another CV). Do not overwrite "
    "content that already exists. Only fill in information that genuinely appears "
    "in the sources."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
