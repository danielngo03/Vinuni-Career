"""AI cover letter draft service — generates a personalised draft for a student.

Student-facing, read-only advisory output. The draft is never stored and is
never forwarded to any partner — the student must explicitly copy/paste it into
their application. If AI is unavailable a deterministic template-based draft is
returned (is_fallback=True) so the UI degrades gracefully.

Permission: authenticated student. The target job must be publicly visible.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_note
from app.ai.energy import service as energy_service
from app.ai.observability.billable_usage import FEATURE_COVER_LETTER
from app.ai.prompts.cover_letter import v1 as cover_prompt
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.lifecycle import visible_levels_for
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError

_TASK_TYPE = "cover_letter"
_MAX_TOKENS = 700


def _static_draft(job_title: str, company_name: str, student_name: str) -> str:
    return (
        f"I am writing to express my strong interest in the {job_title} position "
        f"at {company_name}. As a student at VinUni, I have developed the skills "
        f"and work ethic that I believe align well with your team's needs.\n\n"
        f"During my studies and relevant experiences, I have had the opportunity "
        f"to work on projects that have strengthened my technical abilities and "
        f"collaborative mindset. I am eager to bring these skills to a "
        f"results-driven environment like {company_name}.\n\n"
        f"I am confident that my background and enthusiasm make me a strong "
        f"candidate for this role. I look forward to the opportunity to "
        f"contribute to your team."
    )


async def generate_cover_letter(
    session: AsyncSession,
    *,
    principal,
    job_id: uuid.UUID,
    student_note: str | None = None,
) -> dict:
    """Generate a cover letter draft for a student applying to a job.

    Returns:
        {
            "draft": str,            # Cover letter body text (advisory)
            "prompt_version": int,   # For rollback tracking
            "is_fallback": bool,     # True if AI was unavailable
        }
    """
    from app.modules.student_profiles.application.profile_service import get_my_profile

    # Load the publicly visible job.
    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    levels = visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    import datetime

    now = datetime.datetime.utcnow()
    # A publicly visible job is ACTIVE + moderation-APPROVED + published + within
    # deadline + a tier the persona may discover (mirrors ``apply_visible_filter``;
    # a job's published state is ``active``, never a ``"published"`` status).
    is_public = (
        job.status == lifecycle.ACTIVE
        and job.moderation_status == lifecycle.MOD_APPROVED
        and job.published_at is not None
        and job.published_at <= now
        and (job.application_deadline is None or job.application_deadline >= now)
        and job.visibility in levels
    )
    if not is_public and not principal.is_superadmin:
        raise ResourceNotFoundError()

    # Preflight AI-energy gate BEFORE spending a model call. No-op for guests;
    # raises 409 QUOTA_EXCEEDED only on genuine weekly exhaustion (after wallet).
    await energy_service.enforce_energy(session, principal=principal)

    org = await org_reporting_facade.summary_for(session, job.org_id)
    company_name = org.display_name if org else "the company"

    # The profile is identity-only (owner decision 2026-07-06): it supplies the
    # student's name only. Career content (major/skills/experience/education) lives
    # in the student's CVs and is intentionally not pulled into the cover-letter
    # prompt — the prompt already guards missing fields and never invents facts.
    try:
        profile = await get_my_profile(session, principal=principal)
    except Exception:
        profile = {}

    student_name = profile.get("display_name") or "the student"

    # Build AI input payload (name + job context only).
    inputs = {
        "title": job.title or "",
        "company_name": company_name,
        "description": job.description or "",
        "required_skills": job.required_skills or [],
        "student_name": student_name,
    }

    # Optionally append the student's own note to the AI context.
    if student_note and student_note.strip():
        safe_note, _flags = sanitize_instruction(student_note.strip()[:400])
        if safe_note:
            inputs["student_note"] = safe_note

    # Try AI generation; fall back to static template on failure. On success the
    # metered gateway debits the student's AI energy for one cover-letter credit
    # (charged ONLY on a successful, user-visible draft). No stable cv identity is
    # available on this endpoint (draft is job + name only) and drafts are freely
    # regenerable, so the charge is attributed to the job resource without an
    # idempotency key — each genuine regeneration is a real model call.
    usage_context = energy_service.build_usage_context(
        principal,
        feature_key=FEATURE_COVER_LETTER,
        task_type=_TASK_TYPE,
        resource_type="job",
        resource_id=job_id,
    )
    try:
        user_content = cover_prompt.build_user_message(inputs)
        draft = await generate_note(
            task_type=_TASK_TYPE,
            system_prompt=cover_prompt.STATIC_SYSTEM_PROMPT,
            user_content=user_content,
            temperature=0.35,
            max_tokens=_MAX_TOKENS,
            db=session,
            user_id=getattr(principal, "user_id", None),
            org_id=getattr(principal, "org_id", None),
            usage_context=usage_context,
            charge_units=energy_service.charge_units(FEATURE_COVER_LETTER),
        )
        return {
            "draft": draft.strip(),
            "prompt_version": cover_prompt.PROMPT_VERSION,
            "is_fallback": False,
        }
    except AIUnavailableError:
        return {
            "draft": _static_draft(job.title or "this position", company_name, student_name),
            "prompt_version": cover_prompt.PROMPT_VERSION,
            "is_fallback": True,
        }
