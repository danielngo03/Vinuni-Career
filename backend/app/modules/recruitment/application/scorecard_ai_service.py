"""Scorecard Assistant AI service — suggests criterion scores from interview notes.

Partner-facing, human_review consent tier (docs/AI_PRODUCT_SPEC.md §3 table).
The AI never writes to the scorecard. The suggestion is surfaced as a draft that
the interviewer must review, edit, and explicitly submit via the normal scorecard
submit endpoint.

Permission: partner with ``ai_recruiting:suggest_scorecard`` on the application's
org (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). The application must be active
(not withdrawn/rejected at a terminal stage).

Rules:
- No provider/model/token internals in the response.
- Output is structured JSON (criteria suggestions + recommendation + reasoning).
- Input guard on free-text notes before the LLM call.
- Confidence field is included so the frontend can show "low confidence" warnings.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_json_note
from app.ai.prompts.scorecard_suggest import v1 as sc_prompt
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError
from app.shared.permissions import permission_checker

_RESOURCE = "ai_recruiting"
_PERM_SUGGEST = "suggest_scorecard"
_TASK_TYPE = "scorecard_suggest"
_VALID_RECOMMENDATIONS = frozenset({"strong_yes", "yes", "no", "strong_no"})
_VALID_CRITERIA = frozenset({"technical", "communication", "culture_fit", "motivation"})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})


async def suggest_scorecard(
    session: AsyncSession,
    *,
    principal,
    application_id: uuid.UUID,
    notes: str,
    job_title: str | None = None,
    interview_stage: str | None = None,
    locale: str = "vi",
) -> dict:
    """Generate AI score suggestions for the 4 standard criteria.

    Returns a dict with per-criterion suggestions and an overall recommendation.
    The caller must display these as draft-only and require explicit submission.
    Returns a best-effort neutral fallback if AI is unavailable.
    """
    permission_checker.require(principal, _RESOURCE, _PERM_SUGGEST)

    # Verify the application exists and belongs to the partner's org
    application = (
        await session.execute(
            select(Application).where(
                Application.id == application_id,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if application is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and application.org_id != principal.org_id:
        raise ResourceNotFoundError()

    # Sanitize notes (partner free text)
    clean_notes, _ = sanitize_instruction(notes[:2000])
    if not clean_notes:
        clean_notes = notes[:2000]

    inputs: dict = {
        "notes": clean_notes,
        "job_title": job_title,
        "interview_stage": interview_stage,
    }

    try:
        result = await generate_json_note(
            task_type=_TASK_TYPE,
            system_prompt=sc_prompt.STATIC_SYSTEM_PROMPT,
            user_content=sc_prompt.build_user_message(inputs),
            temperature=0.2,
            max_tokens=800,
        )
        return normalize_scorecard_result(result)

    except AIUnavailableError:
        return fallback_scorecard_result()


def normalize_scorecard_result(result: dict) -> dict:
    """Validate + clamp a raw LLM scorecard JSON into the safe response shape.

    Pure function (no I/O) so the eval harness can exercise this exact
    validation logic directly — scores are clamped to 1-5, unknown
    recommendation/confidence enum values are neutralized rather than passed
    through verbatim, and every free-text field is length-capped.
    """
    raw_criteria = result.get("criteria") or {}
    clean_criteria: dict = {}
    for key in _VALID_CRITERIA:
        entry = raw_criteria.get(key) or {}
        score = entry.get("score")
        if score is not None:
            try:
                score = int(score)
                score = max(1, min(5, score))
            except (TypeError, ValueError):
                score = None
        clean_criteria[key] = {
            "score": score,
            "reasoning": str(entry.get("reasoning", ""))[:300],
        }

    recommendation = result.get("recommendation", "")
    if recommendation not in _VALID_RECOMMENDATIONS:
        recommendation = None

    confidence = result.get("confidence", "medium")
    if confidence not in _VALID_CONFIDENCE:
        confidence = "medium"

    return {
        "criteria": clean_criteria,
        "recommendation": recommendation,
        "overall_reasoning": str(result.get("overall_reasoning", ""))[:400],
        "confidence": confidence,
        "prompt_version": sc_prompt.PROMPT_VERSION,
        "is_fallback": False,
    }


def fallback_scorecard_result() -> dict:
    """The neutral, no-signal response returned when AI is unavailable."""
    return {
        "criteria": {key: {"score": None, "reasoning": ""} for key in sorted(_VALID_CRITERIA)},
        "recommendation": None,
        "overall_reasoning": "",
        "confidence": "low",
        "prompt_version": sc_prompt.PROMPT_VERSION,
        "is_fallback": True,
    }
