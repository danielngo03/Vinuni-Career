"""JD Writer AI service — generates draft job descriptions for partner review.

Advisory only: output is always surfaced as a DRAFT that the partner must review,
edit, and explicitly apply before it becomes the canonical description. The AI
never modifies a Job record directly.

Rules (docs/AI_PRODUCT_SPEC.md §JD writer; docs/SECURITY_PRIVACY.md):
- Partner permission required (org-scoped).
- No provider/model/token internals in the response.
- Output is plain text (not stored); no audit row needed for the generation
  call itself — only the partner's eventual description-update is audited by
  job_service.update_job.
- Input guard runs before the LLM call; output guard on the LLM response.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_note  # re-uses the same guard/log helper
from app.ai.prompts.jd_generation import v1 as jd_prompt
from app.ai.safety.bias_detection import BiasCheckResult, check_bias
from app.ai.safety.content_moderation import ContentCheckResult, check_content
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.opportunities.application.job_service import _load_owned_job
from app.shared.permissions import permission_checker

logger = logging.getLogger(__name__)

_RESOURCE = "jobs"
_TASK_TYPE = "jd_generation"
# JD draft can be longer than a CV note — allow up to ~800 tokens of prose.
_MAX_TOKENS = 900


async def draft_description_standalone(
    session: AsyncSession,
    *,
    principal,
    payload: dict,
    locale: str = "vi",
) -> dict:
    """Generate a JD draft without an existing job (for new-job creation flow)."""
    permission_checker.require(principal, _RESOURCE, "create")

    inputs = dict(payload)
    partner_instruction = inputs.get("partner_instruction") or ""
    if partner_instruction:
        clean, _ = sanitize_instruction(partner_instruction[:2000])
        inputs["partner_instruction"] = clean or ""

    system_prompt = jd_prompt.build_system_prompt(output_language=locale)
    user_message = jd_prompt.build_user_message(inputs)

    draft_text = await generate_note(
        task_type=_TASK_TYPE,
        system_prompt=system_prompt,
        user_content=user_message,
        temperature=0.4,
        max_tokens=_MAX_TOKENS,
    )

    return {
        "draft": draft_text,
        "prompt_version": jd_prompt.PROMPT_VERSION,
        "bias_check": check_bias(draft_text).as_dict(),
        "content_check": check_content(draft_text).as_dict(),
    }


async def _escalate_if_needed(
    session: AsyncSession,
    *,
    principal,
    job_id,
    bias: BiasCheckResult,
    content: ContentCheckResult,
) -> None:
    """Persist high-risk advisory findings to the human review queue (§9.3).

    Best-effort: escalation failure degrades to "advisory field only" and is
    logged — it never breaks the partner's draft response. Only real jobs are
    escalated (standalone drafts are ephemeral and unmoderatable).
    """
    if not (bias.requires_human_review or content.policy_violation):
        return
    try:
        from app.modules.moderation.application import review_queue_service

        findings: dict = {}
        if bias.requires_human_review:
            findings["bias_check"] = bias.as_dict()
        if content.policy_violation:
            findings["content_check"] = content.as_dict()
        source = (
            review_queue_service.SOURCE_CONTENT
            if content.policy_violation
            else review_queue_service.SOURCE_BIAS
        )
        await review_queue_service.enqueue(
            session,
            source=source,
            resource_type="job",
            resource_id=job_id,
            org_id=principal.org_id,
            severity="high",
            findings=findings,
        )
    except Exception:  # noqa: BLE001 — advisory escalation must never 500 the draft
        logger.warning("jd_ai.review_escalation_failed", exc_info=True)


async def draft_description(
    session: AsyncSession,
    *,
    principal,
    job_id,
    payload: dict,
    locale: str = "vi",
) -> dict:
    """Generate an AI draft description for a partner-owned job.

    ``payload`` keys (all optional beyond ``title``):
    - ``title``: str (falls back to the job's stored title if absent)
    - ``employment_type``: str
    - ``experience_level``: str
    - ``location``: str
    - ``required_skills``: str | list[str]
    - ``preferred_skills``: str | list[str]
    - ``responsibilities``: str
    - ``benefits``: str
    - ``partner_instruction``: str (max 2000 chars; run through input_guard)

    Returns ``{ "draft": "<ai text>", "prompt_version": 1 }`` — no stored row.
    """
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=principal.org_id)
    # Load job to confirm org ownership (raises ResourceNotFoundError on miss).
    job = await _load_owned_job(session, principal=principal, job_id=job_id)

    inputs = dict(payload)
    inputs.setdefault("title", job.title)

    partner_instruction = inputs.get("partner_instruction") or ""
    if partner_instruction:
        clean, _ = sanitize_instruction(partner_instruction[:2000])
        inputs["partner_instruction"] = clean or ""

    system_prompt = jd_prompt.build_system_prompt(output_language=locale)
    user_message = jd_prompt.build_user_message(inputs)

    draft_text = await generate_note(
        task_type=_TASK_TYPE,
        system_prompt=system_prompt,
        user_content=user_message,
        temperature=0.4,
        max_tokens=_MAX_TOKENS,
    )

    bias = check_bias(draft_text)
    content = check_content(draft_text)
    await _escalate_if_needed(
        session, principal=principal, job_id=job.id, bias=bias, content=content
    )
    return {
        "draft": draft_text,
        "prompt_version": jd_prompt.PROMPT_VERSION,
        "bias_check": bias.as_dict(),
        "content_check": content.as_dict(),
    }
