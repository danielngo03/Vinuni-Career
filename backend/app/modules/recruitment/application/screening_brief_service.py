"""AI Screening Brief service — partner-only, advisory only.

Generates 3-4 bullet points summarising a candidate's CV relative to the
job requirements. The brief is privacy-safe (no PII in prompt) and
advisory only — the recruiter must make the final hire/reject decision.

Permission: partner with ``ai_recruiting:screen_candidate`` on the application's
org (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). Output guard scrubs any
provider/model/token leakage.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_json_note
from app.ai.energy import service as energy_service
from app.ai.observability.billable_usage import FEATURE_SCREENING_BRIEF
from app.ai.prompts.screening_brief import v1 as brief_prompt
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

logger = logging.getLogger(__name__)

_RESOURCE = "ai_recruiting"
_PERM_SCREEN = "screen_candidate"
_TASK_TYPE = "screening_brief"
_VALID_SUITABILITY = frozenset({"strong", "moderate", "weak"})


def _extract_skills_from_snapshot(snapshot_json: dict) -> list[str]:
    for section in (snapshot_json.get("sections") or []):
        title = (section.get("title") or "").lower()
        if "skill" in title:
            items = (section.get("content_json") or {}).get("items") or []
            return [
                str(item.get("name") or item.get("title") or item)
                for item in items
                if item
            ][:15]
    return []


def _extract_experience_titles(snapshot_json: dict) -> list[str]:
    for section in (snapshot_json.get("sections") or []):
        title = (section.get("title") or "").lower()
        if "experience" in title or "work" in title:
            items = (section.get("content_json") or {}).get("items") or []
            return [
                str(item.get("title") or item.get("role") or item.get("position") or "")
                for item in items
                if isinstance(item, dict)
            ][:5]
    return []


def _extract_education_summary(snapshot_json: dict) -> str:
    for section in (snapshot_json.get("sections") or []):
        title = (section.get("title") or "").lower()
        if "education" in title:
            items = (section.get("content_json") or {}).get("items") or []
            if items:
                first = items[0]
                if isinstance(first, dict):
                    degree = first.get("degree") or ""
                    school = first.get("institution") or first.get("school") or ""
                    parts = [p for p in [degree, school] if p]
                    return ", ".join(parts)[:100]
    return ""


async def generate_screening_brief(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
) -> dict:
    """Generate a 3-4 bullet AI screening brief for a partner reviewing an application.

    Returns a dict with `bullets` (list[str]), `suitability`, `is_fallback`, and
    `prompt_version`. Falls back to a neutral no-brief response if AI is unavailable.
    """
    permission_checker.require(principal, _RESOURCE, _PERM_SCREEN)

    app = (
        await session.execute(
            select(Application).where(
                Application.id == application_id,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if app is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and app.org_id != principal.org_id:
        raise ResourceNotFoundError()

    await energy_service.enforce_energy(session, principal=principal)

    # Load job for title + required skills
    title, skills = await job_read_facade.get_job_title_and_skills(session, app.job_id)
    job_title = title or "this role"
    required_skills: list[str] = skills[:12]

    # Load CV snapshot (privacy-safe: no contact/PII sections used)
    snapshot_json: dict = (
        await snapshot_service.get_snapshot_json_for_application(
            session, application_id=application_id
        )
        or {}
    )
    candidate_skills = _extract_skills_from_snapshot(snapshot_json)
    experience_titles = _extract_experience_titles(snapshot_json)
    education_summary = _extract_education_summary(snapshot_json)

    # Only include cover letter snippet if reveal is accepted (non-anonymous)
    cover_snippet: str | None = None
    if not app.is_anonymous or app.reveal_approved_at is not None:
        raw_cl = getattr(app, "cover_letter", None) or ""
        cover_snippet = raw_cl[:200].strip() if raw_cl else None

    try:
        user_msg = brief_prompt.build_user_message(
            job_title=job_title,
            required_skills=required_skills,
            candidate_skills=candidate_skills,
            experience_titles=experience_titles,
            education_summary=education_summary,
            cover_letter_snippet=cover_snippet,
        )
        usage_context = energy_service.build_usage_context(
            principal,
            feature_key=FEATURE_SCREENING_BRIEF,
            task_type=_TASK_TYPE,
            resource_type="application",
            resource_id=application_id,
        )
        result = await generate_json_note(
            task_type=_TASK_TYPE,
            system_prompt=brief_prompt.STATIC_SYSTEM_PROMPT,
            user_content=user_msg,
            temperature=0.2,
            max_tokens=512,
            db=session,
            user_id=principal.user_id,
            org_id=principal.org_id,
            usage_context=usage_context,
            charge_units=energy_service.charge_units(FEATURE_SCREENING_BRIEF),
        )
        return normalize_screening_brief_result(result)
    except AIUnavailableError:
        return fallback_screening_brief_result()
    except Exception as exc:  # noqa: BLE001
        # Distinct from AIUnavailableError on purpose: a bug in the extraction
        # helpers above (_extract_skills_from_snapshot etc.) or a malformed
        # model response must NOT be silently indistinguishable from a real
        # "AI is down" event in logs — the response shape is the same
        # (advisory-only, safe), but this path is logged as an unexpected
        # error so it gets triaged as a bug, not treated as normal AI
        # unavailability.
        logger.warning("screening_brief: unexpected error: %s", exc)
        return fallback_screening_brief_result()


def normalize_screening_brief_result(result: dict) -> dict:
    """Validate a raw LLM screening-brief JSON into the safe response shape.

    Pure function (no I/O) — bullets are capped at 4 items / 150 chars each
    and must be strings (a non-string bullet from a malformed model response
    is silently dropped, not stringified, so a hallucinated nested object
    can never be echoed back); an invalid ``suitability`` enum value is
    neutralized to ``"moderate"`` rather than passed through verbatim.
    """
    bullets = [
        str(b)[:150] for b in (result.get("bullets") or []) if isinstance(b, str)
    ][:4]
    suitability = result.get("suitability", "")
    if suitability not in _VALID_SUITABILITY:
        suitability = "moderate"
    return {
        "bullets": bullets,
        "suitability": suitability,
        "is_fallback": False,
        "prompt_version": brief_prompt.PROMPT_VERSION,
    }


def fallback_screening_brief_result() -> dict:
    """The neutral, no-signal response returned when AI is unavailable/errors."""
    return {
        "bullets": [],
        "suitability": None,
        "is_fallback": True,
        "prompt_version": brief_prompt.PROMPT_VERSION,
    }
