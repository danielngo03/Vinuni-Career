"""Build the grounding an interview session is anchored on.

Pure composition over PUBLIC read models (no LLM here):
- ``opportunities.job_fit_read.load_job_for_fit`` — JD requirements + 404 gate.
- ``documents.interview_grounding_service.build_interview_grounding`` — CV picker
  and the selected CV's real highlights + deterministic matched-skills / gaps.

CV and JD text is student/partner-authored, so every free-text field that lands
in the LLM system prompt is passed through ``input_guard.sanitize_instruction``
(defense-in-depth against prompt injection embedded in a CV or JD).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.mock_interview import v1 as prompts
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.documents.application.interview_grounding_service import (
    build_interview_grounding,
)
from app.modules.opportunities.application.job_fit_read import load_job_for_fit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal


def _clean(text: str | None) -> str:
    clean, _ = sanitize_instruction(text)
    return clean or ""


def _clean_list(items: list[str] | None, *, limit: int) -> list[str]:
    out: list[str] = []
    for it in (items or [])[:limit]:
        c = _clean(str(it))
        if c:
            out.append(c)
    return out


_TECH_HINTS = frozenset(
    {
        "python", "java", "javascript", "typescript", "react", "node", "sql",
        "api", "backend", "frontend", "fullstack", "docker", "kubernetes", "cloud",
        "aws", "gcp", "azure", "data", "ml", "machine learning", "ai", "algorithm",
        "c++", "golang", "rust", "devops", "engineer", "developer", "software",
        "database", "microservice", "system design", "security", "network",
    }
)


def _infer_focus(job: dict[str, Any]) -> str:
    """Deterministically infer interview focus from the JD (no manual picker)."""

    haystack = " ".join(
        [
            str(job.get("title") or ""),
            " ".join(str(s) for s in (job.get("required_skills") or [])),
            " ".join(str(s) for s in (job.get("preferred_skills") or [])),
        ]
    ).lower()
    hits = sum(1 for h in _TECH_HINTS if h in haystack)
    if hits >= 2:
        return "technical"
    if hits == 1:
        return "mixed"
    return "behavioral"


def _infer_difficulty(job: dict[str, Any]) -> str:
    """Calibrate difficulty from the JD's seniority signal."""

    level = str(job.get("seniority_level") or "").lower()
    if any(k in level for k in ("intern", "fresher", "entry", "junior", "trainee")):
        return "foundational"
    if any(k in level for k in ("senior", "lead", "principal", "staff", "manager", "head")):
        return "advanced"
    lo = job.get("experience_min_years")
    if isinstance(lo, int | float) and lo >= 4:
        return "advanced"
    if isinstance(lo, int | float) and lo <= 1:
        return "foundational"
    return "intermediate"


def _experience_str(job: dict[str, Any]) -> str | None:
    lo = job.get("experience_min_years")
    hi = job.get("experience_max_years")
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None:
        return f"{lo}-{hi} years"
    if lo is not None:
        return f"{lo}+ years"
    return f"up to {hi} years"


def _job_requirements(job: dict[str, Any]) -> list[str]:
    """Compose a short list of concrete JD requirement bullets."""

    bullets: list[str] = []
    req_text = job.get("requirements")
    if isinstance(req_text, str) and req_text.strip():
        for line in req_text.splitlines():
            piece = line.strip(" •-–\t")
            if len(piece) >= 8:
                bullets.append(piece)
    cand = job.get("candidate_requirements")
    if isinstance(cand, dict):
        for value in cand.values():
            if isinstance(value, str) and len(value.strip()) >= 8:
                bullets.append(value.strip())
    if job.get("degree_required"):
        bullets.append(f"Degree: {job.get('degree_required')}")
    exp = _experience_str(job)
    if exp:
        bullets.append(f"Experience: {exp}")
    return _clean_list(bullets, limit=8)


async def _load_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> dict[str, Any]:
    job = await load_job_for_fit(
        session, job_id=job_id, persona=principal.persona
    )
    if job is None:
        raise ResourceNotFoundError()
    return job


async def build_prep(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = "vi",
) -> dict[str, Any]:
    """Pre-session view: which CV to interview with, for a given job."""

    job = await _load_job(session, principal=principal, job_id=job_id)
    cvg = await build_interview_grounding(
        session, principal=principal, job_id=job_id, cv_id=None
    )
    company = job.get("company") or {}
    return {
        "job": {
            "id": str(job.get("id")),
            "title": job.get("title"),
            "company_name": company.get("display_name"),
        },
        "cvs": cvg.get("cvs") or [],
        "recommended_cv_id": cvg.get("recommended_cv_id"),
        "signal": cvg.get("signal"),
    }


async def build_grounding(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None,
    locale: str = "vi",
) -> dict[str, Any]:
    """Full grounding for a session. Raises on missing job / CV / no ready CV.

    Returns a dict: ``{"grounding": <prompt grounding>, "cv_id": str,
    "signal": str}``. ``grounding`` is the exact shape consumed by
    ``prompts.mock_interview.v1``.
    """

    job = await _load_job(session, principal=principal, job_id=job_id)
    cvg = await build_interview_grounding(
        session, principal=principal, job_id=job_id, cv_id=cv_id
    )
    if cvg.get("requested_missing"):
        # An explicitly chosen CV that the student does not own / is not ready.
        raise ResourceNotFoundError()
    selected = cvg.get("selected")
    if selected is None:
        # No ready CV to interview with — surface a user-safe, actionable error.
        raise ValidationFailedError(
            "Bạn cần một CV đã sẵn sàng để bắt đầu phỏng vấn thử.",
            details={"reason": "NO_READY_CV"},
        )

    company = job.get("company") or {}
    grounding = {
        "locale": locale or "vi",
        "grounding_version": prompts.PROMPT_VERSION,
        "focus": _infer_focus(job),
        "difficulty": _infer_difficulty(job),
        "job": {
            "title": _clean(job.get("title")),
            "company_name": company.get("display_name"),
            "description": _clean(job.get("description"))[:1200],
            "requirements": _job_requirements(job),
            "required_skills": _clean_list(job.get("required_skills"), limit=20),
            "preferred_skills": _clean_list(job.get("preferred_skills"), limit=12),
            "seniority_level": job.get("seniority_level"),
            "experience": _experience_str(job),
        },
        "cv": {
            "title": _clean(selected.get("title")),
            "language": selected.get("language") or "vi",
            "highlights": _clean_list(selected.get("highlights"), limit=10),
            "skills": _clean_list(selected.get("skills"), limit=25),
        },
        "matched_skills": _clean_list(selected.get("matched_skills"), limit=15),
        "gaps": _clean_list(selected.get("gaps"), limit=15),
        "fit": {"score": selected.get("score"), "signal": cvg.get("signal")},
    }
    # M5: a near-empty JD (no requirements, no required skills, tiny description)
    # yields generic questions. The interview still runs, but flag it so the UI
    # can set expectations honestly instead of pretending the grounding was rich.
    low_signal = (
        not _job_requirements(job)
        and not _clean_list(job.get("required_skills"), limit=20)
        and len(_clean(job.get("description"))) < 120
    )
    grounding["low_signal"] = low_signal
    return {
        "grounding": grounding,
        "cv_id": selected.get("cv_id"),
        "signal": "low_jd" if low_signal else (cvg.get("signal") or "ok"),
        "low_signal": low_signal,
    }
