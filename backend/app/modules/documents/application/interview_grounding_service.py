"""CV grounding for the mock-interview feature (documents-owned public read).

The ``mock_interview`` module must not reach into CV internals directly (module
boundary). This service is the ONE public entry point it calls to obtain, for a
target job:

- the student's CV picker list (title + deterministic fit score + recommended
  flag), reusing the existing ``job_fit_for_job`` read model; and
- the SELECTED CV's real, structured highlights + skills + matched-skills + gaps,
  so the interviewer can probe genuine CV items against the JD.

Everything here is owner-scoped through ``job_fit_for_job`` (which enforces the
CV ``read`` permission and the job's public visibility). No provider/model/token
internals are ever returned; scores are the existing deterministic product score.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import grounding as _cv_grounding
from app.modules.documents.application.job_fit_service import (
    _build_cv_input,
    _load_active_cvs,
    job_fit_for_job,
)
from app.shared.permissions import Principal

# Synthetic sections injected upstream for matching — not real CV content.
_SKIP_SECTION_TYPES = frozenset({"skills_en", "translated_en"})
_SKILL_SECTION_HINTS = ("skill", "kỹ năng", "competenc")
_MAX_HIGHLIGHTS = 10
_MAX_HIGHLIGHT_LEN = 200
_MAX_SKILLS = 25


def _extract_skills(sections: list[dict[str, Any]]) -> list[str]:
    """Pull discrete skill terms from any skills-like section."""

    out: list[str] = []
    for sec in sections or []:
        stype = str(sec.get("section_type") or "").lower()
        if stype in _SKIP_SECTION_TYPES:
            continue
        if not any(h in stype for h in _SKILL_SECTION_HINTS):
            continue
        content = sec.get("content")
        items = content.get("items") if isinstance(content, dict) else None
        for item in items or []:
            if isinstance(item, dict):
                name = item.get("name") or item.get("label") or item.get("text")
            else:
                name = item
            if name:
                term = str(name).strip()[:60]
                if term and term not in out:
                    out.append(term)
    return out[:_MAX_SKILLS]


def _flatten_highlights(sections: list[dict[str, Any]]) -> list[str]:
    """Turn structured CV sections into short probe-able lines for the prompt."""

    lines: list[str] = []
    for sec in sections or []:
        stype = str(sec.get("section_type") or "").lower()
        if stype in _SKIP_SECTION_TYPES:
            continue
        text = _cv_grounding.content_to_text(sec.get("content"))
        if not text:
            continue
        label = stype.replace("_", " ").strip() or "detail"
        for raw in str(text).splitlines():
            piece = raw.strip(" •-–\t")
            if len(piece) < 8:
                continue
            lines.append(f"[{label}] {piece[:_MAX_HIGHLIGHT_LEN]}")
            if len(lines) >= _MAX_HIGHLIGHTS:
                return lines
    return lines


async def build_interview_grounding(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Return CV picker + selected-CV grounding for a mock interview.

    Raises the same ``ResourceNotFoundError`` / permission errors as
    ``job_fit_for_job`` when the job is not publicly visible or the CV is not
    readable. ``selected`` is ``None`` only when the student has no ready CV.
    """

    fit = await job_fit_for_job(session, principal=principal, job_id=job_id)
    results: list[dict[str, Any]] = list(fit.get("results") or [])
    recommended = fit.get("recommended_cv_id")

    picker = [
        {
            "cv_id": r["cv_id"],
            "title": r.get("title") or "CV",
            "score": r.get("score"),
            "is_recommended": r["cv_id"] == recommended,
        }
        for r in results
    ]

    requested = str(cv_id) if cv_id is not None else None
    chosen_id = requested or recommended or (results[0]["cv_id"] if results else None)
    chosen = next((r for r in results if r["cv_id"] == chosen_id), None)

    # An explicitly requested CV that is not among the owner's ready CVs is a 404
    # for the caller to raise (do not silently substitute another CV).
    if requested is not None and chosen is None:
        return {
            "cvs": picker,
            "recommended_cv_id": recommended,
            "signal": fit.get("signal"),
            "selected": None,
            "requested_missing": True,
        }

    selected: dict[str, Any] | None = None
    if chosen is not None and principal.user_id is not None:
        highlights: list[str] = []
        skills: list[str] = []
        language = "vi"
        active = await _load_active_cvs(session, user_id=principal.user_id)
        cv_row = next((c for c in active if str(c.id) == chosen_id), None)
        if cv_row is not None:
            cv_input = await _build_cv_input(
                session, cv=cv_row, now=datetime.now(tz=UTC)
            )
            language = cv_input.language or "vi"
            highlights = _flatten_highlights(cv_input.sections)
            skills = _extract_skills(cv_input.sections)
        selected = {
            "cv_id": chosen_id,
            "title": chosen.get("title") or "CV",
            "language": language,
            "highlights": highlights,
            "skills": skills or list(chosen.get("matched_skills") or []),
            "matched_skills": list(chosen.get("matched_skills") or []),
            "gaps": list(chosen.get("gaps") or []),
            "score": chosen.get("score"),
        }

    return {
        "cvs": picker,
        "recommended_cv_id": recommended,
        "signal": fit.get("signal"),
        "selected": selected,
        "requested_missing": False,
    }
