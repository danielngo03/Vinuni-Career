"""Read-only aggregation helpers for the persona dashboards (no writes, no audit).

These are **scoped-by-argument** read functions: each takes the already-resolved
owner ``user_id`` or ``org_id`` and returns small, projected rows. They do not
re-check RBAC — the calling ``dashboards`` application service owns the persona
gate and only ever passes the caller's own scope. This mirrors the RBAC-free
``opportunities.public_read`` facade.

Privacy rule for partner-facing rows: a dashboard is a glance surface, so partner
candidate rows carry **only** the deterministic anonymous handle
(``presenters.anonymous_handle``) — never the student's name/email — regardless of
reveal state. Full identity (post-reveal) lives on the application *detail*
endpoint, not on the org-wide glance.

Job titles / org display names are resolved through the ``opportunities`` /
``organization`` internal read facades (no cross-module ORM import) with a
second batched query rather than a live JOIN, consistent with the "no cross-
module imports" rule (`docs/ARCHITECTURE.md` §8).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared
from app.modules.recruitment.domain import lifecycle, pipeline
from app.modules.recruitment.domain.models import (
    Application,
    ApplicationRevealRequest,
    CandidateStage,
    Interview,
    Offer,
)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Student scope                                                               #
# --------------------------------------------------------------------------- #


async def count_student_applications(
    session: AsyncSession, *, user_id: uuid.UUID
) -> dict[str, int]:
    """``{total, active}`` counts of the student's own (non-deleted) applications."""

    rows = (
        await session.execute(
            select(Application.status, func.count())
            .where(
                Application.applicant_id == user_id,
                Application.deleted_at.is_(None),
            )
            .group_by(Application.status)
        )
    ).all()
    by_status: dict[str, int] = {}
    for status, count in rows:
        by_status[status] = count
    total = sum(by_status.values())
    active = sum(
        count for status, count in by_status.items() if status in lifecycle.ACTIVE_STATUSES
    )
    return {"total": total, "active": active}


async def list_recent_student_applications(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    """Newest-first compact rows of the student's own applications (with employer)."""

    apps = (
        (
            await session.execute(
                select(Application)
                .where(
                    Application.applicant_id == user_id,
                    Application.deleted_at.is_(None),
                )
                .order_by(Application.applied_at.desc(), Application.id.desc())
                .limit(max(limit, 0))
            )
        )
        .scalars()
        .all()
    )
    titles = await job_read_facade.get_job_titles(session, (a.job_id for a in apps))
    names = await org_reporting_facade.display_names_for(session, (a.org_id for a in apps))
    return [
        {
            "id": str(app.id),
            "job_title": titles.get(app.job_id),
            "company_name": names.get(app.org_id),
            "status": app.status,
            "status_label": lifecycle.status_label(app.status, locale=locale),
            "submitted_at": _iso(app.applied_at),
        }
        for app in apps
    ]


async def _pending_reveals_for_student(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[tuple[ApplicationRevealRequest, str | None, str | None]]:
    """Non-expired ``pending`` reveal requests on the student's applications.

    Expiry is evaluated in Python (``_shared.as_aware``) so the lazily-expired
    convention used elsewhere (``apply_service._effective_reveal_status``) holds
    identically across SQLite (tests) and PostgreSQL (runtime).
    """

    rows = (
        await session.execute(
            select(ApplicationRevealRequest, Application.job_id)
            .join(Application, Application.id == ApplicationRevealRequest.application_id)
            .where(
                Application.applicant_id == user_id,
                Application.deleted_at.is_(None),
                ApplicationRevealRequest.status == lifecycle.REVEAL_PENDING,
            )
            .order_by(ApplicationRevealRequest.created_at.desc())
        )
    ).all()
    titles = await job_read_facade.get_job_titles(session, (job_id for _, job_id in rows))
    names = await org_reporting_facade.display_names_for(
        session, (req.requester_org_id for req, _ in rows)
    )
    now = _shared.now()
    return [
        (req, titles.get(job_id), names.get(req.requester_org_id))
        for req, job_id in rows
        if _shared.as_aware(req.expires_at) > now
    ]


async def list_upcoming_student_interviews(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    """Upcoming scheduled interviews for the student's own applications (soonest first)."""

    now = _shared.now()
    rows = (
        await session.execute(
            select(Interview, Application.job_id)
            .join(Application, Application.id == Interview.application_id)
            .where(
                Application.applicant_id == user_id,
                Application.deleted_at.is_(None),
                Interview.status == "scheduled",
                Interview.scheduled_at > now,
            )
            .order_by(Interview.scheduled_at.asc())
            .limit(max(limit, 0))
        )
    ).all()
    titles = await job_read_facade.get_job_titles(session, (job_id for _, job_id in rows))
    names = await org_reporting_facade.display_names_for(session, (iv.org_id for iv, _ in rows))
    return [
        {
            "id": str(iv.id),
            "application_id": str(iv.application_id),
            "job_title": titles.get(job_id),
            "company_name": names.get(iv.org_id),
            "title": iv.title,
            "mode": iv.mode,
            "scheduled_at": _iso(iv.scheduled_at),
            "duration_minutes": iv.duration_minutes,
            "location": iv.location,
        }
        for iv, job_id in rows
    ]


async def count_pending_reveals_for_student(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    return len(await _pending_reveals_for_student(session, user_id=user_id))


async def list_pending_reveals_for_student(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    pending = await _pending_reveals_for_student(session, user_id=user_id)
    return [
        {
            "application_id": str(req.application_id),
            "job_title": title,
            "company_name": company,
            "requested_at": _iso(req.created_at),
        }
        for req, title, company in pending[: max(limit, 0)]
    ]


# --------------------------------------------------------------------------- #
# Partner (org) scope                                                         #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Platform-wide (university governance) scope                                  #
# --------------------------------------------------------------------------- #


async def count_all_applications(session: AsyncSession) -> int:
    """Total non-deleted applications across the platform (university KPI)."""

    return (
        await session.execute(
            select(func.count()).select_from(Application).where(Application.deleted_at.is_(None))
        )
    ).scalar_one()


async def monthly_application_counts(session: AsyncSession, *, months: int = 6) -> list[dict]:
    """Applied-count per calendar month for the last ``months`` months (oldest first)."""

    now = datetime.now(tz=UTC)
    out: list[dict] = []
    for i in range(months - 1, -1, -1):
        start = (now.replace(day=1) - timedelta(days=30 * i)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end = (
            start.replace(year=start.year + 1, month=1)
            if start.month == 12
            else start.replace(month=start.month + 1)
        )
        count = (
            await session.execute(
                select(func.count())
                .select_from(Application)
                .where(
                    Application.applied_at >= start,
                    Application.applied_at < end,
                    Application.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        out.append(
            {
                "month": start.strftime("%Y-%m"),
                "label": start.strftime("%b %Y"),
                "count": count,
            }
        )
    return out


async def count_org_applications(session: AsyncSession, *, org_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(Application.org_id == org_id, Application.deleted_at.is_(None))
        )
    ).scalar_one()


async def count_org_applications_needing_review(
    session: AsyncSession, *, org_id: uuid.UUID
) -> int:
    """New applications awaiting partner triage (``submitted``) for this org."""

    return (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.org_id == org_id,
                Application.status == lifecycle.SUBMITTED,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one()


async def count_org_offers_by_status(
    session: AsyncSession, *, org_id: uuid.UUID, statuses: tuple[str, ...]
) -> int:
    """Count this org's offers in any of ``statuses`` (e.g. pending_approval / approved)."""

    if not statuses:
        return 0
    return (
        await session.execute(
            select(func.count())
            .select_from(Offer)
            .where(Offer.org_id == org_id, Offer.status.in_(statuses))
        )
    ).scalar_one()


async def count_org_pending_reveals(session: AsyncSession, *, org_id: uuid.UUID) -> int:
    """Reveal requests this org initiated that are still awaiting a student
    response (non-expired ``pending``)."""

    rows = (
        (
            await session.execute(
                select(ApplicationRevealRequest).where(
                    ApplicationRevealRequest.requester_org_id == org_id,
                    ApplicationRevealRequest.status == lifecycle.REVEAL_PENDING,
                )
            )
        )
        .scalars()
        .all()
    )
    now = _shared.now()
    return sum(1 for req in rows if _shared.as_aware(req.expires_at) > now)


async def list_recent_org_applications(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    """Newest-first applications to the org's jobs — ANONYMOUS handle only.

    The dashboard never surfaces applicant PII; the partner opens the application
    detail (which enforces the reveal handshake) to see identity where allowed.
    """

    apps = (
        (
            await session.execute(
                select(Application)
                .where(Application.org_id == org_id, Application.deleted_at.is_(None))
                .order_by(Application.applied_at.desc(), Application.id.desc())
                .limit(max(limit, 0))
            )
        )
        .scalars()
        .all()
    )
    titles = await job_read_facade.get_job_titles(session, (a.job_id for a in apps))
    return [
        {
            "id": str(app.id),
            "job_title": titles.get(app.job_id),
            "candidate_handle": presenters.anonymous_handle(
                applicant_id=app.applicant_id, org_id=app.org_id
            ),
            "status": app.status,
            "status_label": lifecycle.status_label(app.status, locale=locale),
            "submitted_at": _iso(app.applied_at),
        }
        for app in apps
    ]


# --------------------------------------------------------------------------- #
# proj_partner_pipeline (live read) — ADR-0004 consequence #4                  #
# --------------------------------------------------------------------------- #
#
# ``docs/DATA_MODEL.md`` §15 declares ``proj_partner_pipeline`` as a materialized
# view. ADR-0004 moved the FINE pipeline position out of ``applications.status``
# (which is now the COARSE outcome only) and into ``candidate_stages`` (one ACTIVE
# row per application). The pre-ADR projection counted by-stage from
# ``applications.status IN ('interview','offer',…)`` — those values no longer exist,
# so the by-stage buckets must be recomputed from the ACTIVE ``candidate_stages``
# rows. The functions below are the canonical LIVE read; the materialized view in
# ``DATA_MODEL`` §15 was updated to the SAME shape (refresh: on every stage move +
# scheduled 5 min) and, when built, must back these reads unchanged.
#
# Coarse outcome buckets (``rejected`` / ``withdrawn``) stay sourced from
# ``applications.status`` (correct + projection-friendly); only the by-stage and
# the pre-pipeline "new" buckets read from ``candidate_stages``.


async def _coarse_status_counts(session: AsyncSession, *, where) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Application.status, func.count()).where(*where).group_by(Application.status)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _active_stage_counts(session: AsyncSession, *, where) -> dict[uuid.UUID, int]:
    """Count ACTIVE ``candidate_stages`` rows per stage for under_review apps.

    Joins ``applications`` so the coarse outcome gates the count: a withdrawn
    application can retain a lingering ACTIVE stage row (withdraw does not close
    it), but it is NOT "in the pipeline" — only ``under_review`` rows count.
    """

    rows = (
        await session.execute(
            select(CandidateStage.stage_id, func.count())
            .join(Application, Application.id == CandidateStage.application_id)
            .where(
                *where,
                Application.deleted_at.is_(None),
                Application.status == lifecycle.UNDER_REVIEW,
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
            .group_by(CandidateStage.stage_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _new_bucket_count(session: AsyncSession, *, where) -> int:
    """Active-outcome applications with no ACTIVE stage row (pre-pipeline bucket).

    Captures ``submitted`` (never reviewed) plus any legacy ``under_review`` that
    predates the stage engine and so has no ACTIVE ``candidate_stages`` row — the
    SAME predicate the board's LEFT JOIN uses, so counts and cards never disagree.
    """

    active_exists = (
        select(CandidateStage.id)
        .where(
            CandidateStage.application_id == Application.id,
            CandidateStage.status == pipeline.STAGE_ACTIVE,
        )
        .exists()
    )
    return (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                *where,
                Application.deleted_at.is_(None),
                Application.status.in_(tuple(lifecycle.ACTIVE_STATUSES)),
                ~active_exists,
            )
        )
    ).scalar_one()


def _assemble_pipeline_counts(
    *,
    coarse: dict[str, int],
    by_stage: dict[uuid.UUID, int],
    new_count: int,
) -> dict:
    by_stage_str = {str(k): v for k, v in by_stage.items()}
    return {
        "new": new_count,
        "by_stage": by_stage_str,
        "active_total": new_count + sum(by_stage.values()),
        "rejected": coarse.get(lifecycle.REJECTED, 0),
        "withdrawn": coarse.get(lifecycle.WITHDRAWN, 0),
    }


async def pipeline_counts_for_job(session: AsyncSession, *, job_id: uuid.UUID) -> dict:
    """``proj_partner_pipeline`` counts for ONE job, derived from candidate_stages.

    Returns ``{new, by_stage:{stage_id: count}, active_total, rejected,
    withdrawn}``. ``by_stage`` keys are the ACTIVE stage ids; the caller maps them
    onto the job's template stages (a stage with zero candidates is simply absent
    and renders as an empty column).
    """

    job_where = (Application.job_id == job_id,)
    coarse = await _coarse_status_counts(
        session, where=(Application.job_id == job_id, Application.deleted_at.is_(None))
    )
    by_stage = await _active_stage_counts(session, where=job_where)
    new_count = await _new_bucket_count(session, where=job_where)
    return _assemble_pipeline_counts(coarse=coarse, by_stage=by_stage, new_count=new_count)


async def pipeline_counts_for_org(session: AsyncSession, *, org_id: uuid.UUID) -> dict:
    """``proj_partner_pipeline`` counts rolled up across ALL of an org's jobs.

    Same shape as :func:`pipeline_counts_for_job`; powers the partner dashboard
    "pipeline overview" glance without a heavy live join (one grouped aggregate
    each over ``applications`` and ``candidate_stages``).
    """

    org_where = (Application.org_id == org_id,)
    coarse = await _coarse_status_counts(
        session, where=(Application.org_id == org_id, Application.deleted_at.is_(None))
    )
    by_stage = await _active_stage_counts(session, where=org_where)
    new_count = await _new_bucket_count(session, where=org_where)
    return _assemble_pipeline_counts(coarse=coarse, by_stage=by_stage, new_count=new_count)


# --------------------------------------------------------------------------- #
# Per-job pipeline overview (no PII, counts only)                               #
# --------------------------------------------------------------------------- #


async def pipeline_overview_for_org(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int = 50,
) -> list[dict]:
    """Per-job pipeline snapshot across ALL of an org's jobs.

    Returns one row per job, sorted by descending active candidate count then by
    newest job first. No candidate PII — counts only.
    """

    from sqlalchemy import case

    job_refs = await job_read_facade.list_org_job_refs(session, org_id=org_id)
    if not job_refs:
        return []

    active_sum = func.sum(
        case((Application.status.in_(list(lifecycle.ACTIVE_STATUSES)), 1), else_=0)
    )
    rejected_sum = func.sum(case((Application.status == lifecycle.REJECTED, 1), else_=0))
    withdrawn_sum = func.sum(case((Application.status == lifecycle.WITHDRAWN, 1), else_=0))
    count_rows = (
        await session.execute(
            select(
                Application.job_id,
                func.count(Application.id).label("total"),
                func.coalesce(active_sum, 0).label("active_total"),
                func.coalesce(rejected_sum, 0).label("rejected"),
                func.coalesce(withdrawn_sum, 0).label("withdrawn"),
            )
            .where(Application.org_id == org_id, Application.deleted_at.is_(None))
            .group_by(Application.job_id)
        )
    ).all()
    counts = {r.job_id: r for r in count_rows}

    rows: list[tuple[job_read_facade.JobRef, int, int, int, int]] = []
    for ref in job_refs:
        c = counts.get(ref.id)
        rows.append(
            (
                ref,
                int((c.total if c else 0) or 0),
                int((c.active_total if c else 0) or 0),
                int((c.rejected if c else 0) or 0),
                int((c.withdrawn if c else 0) or 0),
            )
        )

    rows.sort(key=lambda r: (-r[2], -r[0].created_at.timestamp()))
    items = [
        {
            "job_id": str(ref.id),
            "title": ref.title or "",
            "status": ref.status,
            "deadline": ref.application_deadline.isoformat() if ref.application_deadline else None,
            "total": total,
            "active_total": active_total,
            "rejected": rejected,
            "withdrawn": withdrawn,
        }
        for ref, total, active_total, rejected, withdrawn in rows
    ]
    return items[: max(limit, 0)]


# --------------------------------------------------------------------------- #
# Partner analytics (read-only aggregations, no PII)                           #
# --------------------------------------------------------------------------- #


async def analytics_application_funnel(session: AsyncSession, *, org_id: uuid.UUID) -> list[dict]:
    """Application funnel counts grouped by coarse status for an org.

    Returns counts for active statuses in pipeline order, then terminal statuses.
    No candidate PII — counts only.
    """

    rows = (
        await session.execute(
            select(Application.status, func.count().label("n"))
            .where(Application.org_id == org_id, Application.deleted_at.is_(None))
            .group_by(Application.status)
        )
    ).all()
    count_by_status: dict[str, int] = {r.status: r.n for r in rows}

    # Return in a meaningful funnel order.
    ordered = [
        "submitted",
        "under_review",
        "shortlisted",
        "interview",
        "offer",
        "hired",
        "rejected",
        "withdrawn",
    ]
    return [
        {"status": s, "count": count_by_status.get(s, 0)}
        for s in ordered
        if count_by_status.get(s, 0) > 0
    ]


async def analytics_top_jobs(
    session: AsyncSession, *, org_id: uuid.UUID, limit: int = 5
) -> list[dict]:
    """Top jobs by application volume (non-deleted applications)."""

    rows = (
        await session.execute(
            select(Application.job_id, func.count(Application.id).label("n"))
            .where(Application.org_id == org_id, Application.deleted_at.is_(None))
            .group_by(Application.job_id)
            .order_by(func.count(Application.id).desc())
            .limit(max(limit, 1))
        )
    ).all()
    titles = await job_read_facade.get_job_titles(session, (r.job_id for r in rows))
    return [
        {"job_id": str(r.job_id), "title": titles.get(r.job_id) or "—", "application_count": r.n}
        for r in rows
    ]


async def analytics_monthly_trend(
    session: AsyncSession, *, org_id: uuid.UUID, months: int = 6
) -> list[dict]:
    """Monthly application counts for the last N months (oldest first).

    Month-bucketing SQL is dialect-specific: PostgreSQL (real runtime) has no
    ``strftime`` function — it raises ``UndefinedFunctionError`` — so this uses
    ``to_char`` there and falls back to SQLite's ``strftime`` only for the
    in-memory test dialect.

    Month labels are ISO ``YYYY-MM`` strings so the frontend can format them.
    """

    cutoff = datetime.now(tz=UTC) - timedelta(days=months * 31)
    dialect = session.bind.dialect.name if session.bind is not None else "postgresql"
    if dialect == "sqlite":
        month_expr = func.strftime("%Y-%m", Application.applied_at)
    else:
        month_expr = func.to_char(Application.applied_at, "YYYY-MM")
    rows = (
        await session.execute(
            select(
                month_expr.label("month"),
                func.count().label("n"),
            )
            .where(
                Application.org_id == org_id,
                Application.deleted_at.is_(None),
                Application.applied_at >= cutoff,
            )
            .group_by(month_expr)
            .order_by(month_expr)
        )
    ).all()
    return [{"month": r.month, "count": r.n} for r in rows]


async def hiring_outcomes_for_org(
    session: AsyncSession, *, org_id: uuid.UUID, months: int = 12
) -> dict:
    """Hires / accepted-offers / recent-application counts for an org's CRM rollup."""

    from app.modules.recruitment.domain.offer import STATUS_ACCEPTED

    total_applications = await count_org_applications(session, org_id=org_id)
    hired_count = (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.org_id == org_id,
                Application.status == lifecycle.HIRED,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    offers_accepted = (
        await session.execute(
            select(func.count())
            .select_from(Offer)
            .where(Offer.org_id == org_id, Offer.status == STATUS_ACCEPTED)
        )
    ).scalar_one()
    since = datetime.now(tz=UTC) - timedelta(days=30 * months)
    recent_applications = (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(
                Application.org_id == org_id,
                Application.applied_at >= since,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    return {
        "total_applications": total_applications,
        "hired": hired_count,
        "offers_accepted": offers_accepted,
        "recent_applications": recent_applications,
        "window_months": months,
    }
