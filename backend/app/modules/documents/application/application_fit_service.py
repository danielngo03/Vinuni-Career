"""Partner-facing CV-JD fit for an application's immutable CV snapshot.

Reuses the deterministic 6-criteria engine (``app.ai.cv.job_fit``) — the SAME
scorer that powers the student's own CV-JD fit — to score the CV a candidate
actually submitted against the job they applied to. The scorer is PURE and
DETERMINISTIC: same snapshot + same JD => identical score, no AI call, no
``UsageContext``, no token spend. So this is a cheap deterministic reuse computed
on demand (the snapshot is immutable, so there is nothing to invalidate).

The result is user-safe: ``{score (0-100 int), band (localized label),
reasons (short evidence strings)}``. It NEVER exposes provider/model/token/
latency/raw confidence/embedding/prompt internals — the deterministic engine has
none, and only curated JD skill strings (which the partner authored) are echoed.

Returns ``None`` (never an error) when the fit is not computable: no snapshot,
empty/tombstoned CV content, the job is missing, or the JD carries too little
structured signal to score meaningfully (``low_signal``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import grounding, job_fit
from app.modules.documents.domain.models import ApplicationCvSnapshot
from app.modules.opportunities.application import job_fit_read

# Snapshots never go stale for the partner view (they are immutable + already
# submitted), so pass a very large ``stale_days`` and let ``stale`` stay False.
_NEVER_STALE_DAYS = 10_000

_RETENTION_TOMBSTONE_MARKER = "_retention_anonymized"

_BAND_LABELS: dict[str, dict[str, str]] = {
    "strong": {"vi": "Rất phù hợp", "en": "Strong match"},
    "good": {"vi": "Phù hợp", "en": "Good match"},
    "fair": {"vi": "Khá phù hợp", "en": "Fair match"},
    "weak": {"vi": "Ít phù hợp", "en": "Weak match"},
}


def _band_label(score: int, locale: str) -> str:
    if score >= 80:
        key = "strong"
    elif score >= 65:
        key = "good"
    elif score >= 50:
        key = "fair"
    else:
        key = "weak"
    labels = _BAND_LABELS[key]
    return labels.get(locale, labels["vi"])


def _reasons(fit: job_fit.CvFit, locale: str) -> list[str]:
    """Short, user-safe evidence strings — curated JD skills only (never CV text)."""

    out: list[str] = []
    matched = [m for m in fit.matched_skills if m][:4]
    gaps = [g for g in fit.gaps if g][:4]
    if matched:
        prefix = "Điểm mạnh" if locale == "vi" else "Strengths"
        out.append(f"{prefix}: {', '.join(matched)}")
    if gaps:
        prefix = "Còn thiếu" if locale == "vi" else "Gaps"
        out.append(f"{prefix}: {', '.join(gaps)}")
    return out


def _normalize_sections(raw: object) -> list[dict]:
    """Map a snapshot's stored sections into the shape the scorer consumes.

    Builder-CV snapshots store ``{section_type, title, content_json}``; uploaded-CV
    snapshots store ``{title, content_json}`` (no ``section_type``). The scorer
    reads ``section.get("content")`` and ``section.get("section_type")``, so we
    project ``content_json`` -> ``content`` and infer a section type from the title
    when one is absent (e.g. "Experience" -> ``experience``).
    """

    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for section in raw:
        if not isinstance(section, dict):
            continue
        content = section.get("content")
        if not isinstance(content, dict):
            raw_content = section.get("content_json")
            content = raw_content if isinstance(raw_content, dict) else {}
        section_type = section.get("section_type")
        if not section_type:
            section_type = grounding.normalize(str(section.get("title") or "")).replace(" ", "_")
        out.append(
            {
                "section_type": section_type,
                "title": section.get("title"),
                "content": content,
            }
        )
    return out


def _snapshot_to_cv_input(snap: ApplicationCvSnapshot) -> job_fit.CvInput | None:
    body = snap.snapshot_json if isinstance(snap.snapshot_json, dict) else {}
    if not body or body.get(_RETENTION_TOMBSTONE_MARKER):
        return None
    sections = _normalize_sections(body.get("sections"))
    if not sections:
        return None
    return job_fit.CvInput(
        cv_id=str(snap.id),
        title=str(body.get("title") or "CV"),
        language=str(body.get("language") or "vi"),
        sections=sections,
        last_updated_days=0,
    )


async def application_snapshot_fit(
    session: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    job_id: uuid.UUID,
    locale: str = "vi",
) -> dict | None:
    """Deterministic CV-JD fit of ``snapshot_id`` against ``job_id`` (or ``None``).

    The caller (recruitment) must have already verified that the partner may read
    this application/job; this function only loads leak-safe requirements + the
    immutable snapshot and scores them. ``None`` on any non-computable case.
    """

    snap = (
        await session.execute(
            select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.id == snapshot_id)
        )
    ).scalar_one_or_none()
    if snap is None:
        return None
    cv_input = _snapshot_to_cv_input(snap)
    if cv_input is None:
        return None

    job = await job_fit_read.load_job_requirements(session, job_id=job_id)
    if job is None:
        return None

    outcome = job_fit.evaluate(job, [cv_input], stale_days=_NEVER_STALE_DAYS)
    if not outcome.results or outcome.signal == "low_signal":
        # Not enough structured JD signal to make a defensible claim -> null.
        return None
    fit = outcome.results[0]
    return {
        "score": fit.score,
        "band": _band_label(fit.score, locale),
        "reasons": _reasons(fit, locale),
    }
