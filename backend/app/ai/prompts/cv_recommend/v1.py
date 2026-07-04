# Version: 1 | Date: 2026-06-28 | Author: ai-engineer
# Task: recommend_cv_for_job — short, advisory "why this CV / what to improve"
#       narrative for an ALREADY-COMPUTED deterministic fit score.
# Previous: v1 2026-06-27 (initial; Vietnamese task instruction).
# Change: task/system instruction translated to English; user-facing output
#         language now driven by the resolved output_language directive.
"""Prompt template for the optional ``recommend_cv_for_job`` explanation (v1).

The 0-100 score and the matched-skills / gaps lists are computed deterministically
BEFORE this prompt runs (``app.ai.cv.job_fit``). This model call only produces a
short, encouraging user-facing rationale grounded in those pre-computed signals —
it must not restate or invent a score, qualification, or outcome, and missing
skills are framed as "add evidence if true". The output guard scrubs any
provider/model/internal leakage from the returned text.
"""

from __future__ import annotations

from app.ai.prompts.cv_common import static_system_prompt

PROMPT_VERSION = 1

TASK_INSTRUCTION = (
    "Task: based on CONTEXT (the pre-computed fit score, the matched skills, and "
    "the gaps), write 1-2 SHORT sentences explaining why this CV fits the job and "
    "suggesting what to improve. Do NOT restate the numeric score. Do NOT "
    "fabricate skills, experience, qualifications, or outcomes. For each gap, "
    "phrase it as 'if true, add evidence'. Keep an encouraging, professional tone."
)

SYSTEM_PROMPT = static_system_prompt(TASK_INSTRUCTION)


def build_system_prompt(output_language: str | None = None) -> str:
    """System prompt with the resolved user-facing output language injected."""

    return static_system_prompt(TASK_INSTRUCTION, output_language=output_language)
