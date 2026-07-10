"""Own-org job-list export rows (assistant ``export_jobs`` tool).

Returns flat, presentation-ready row dicts (no ORM objects, no xlsx bytes — the
assistant's export layer renders the workbook). RBAC: ``jobs:export`` at org
scope, enforced HERE in the application layer (the tool-loop gate is defense in
depth, never the only check). Org-scoped: only ``principal.org_id``'s own jobs
are ever read; a caller with no org gets an empty export, never another org's.

Row values are user-safe: status labels (never raw enum codes to the file a
recruiter forwards around), the poster's display name (never email), and live
funnel counts read through the recruitment stats facade (module boundary:
opportunities never imports the Application ORM).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "jobs"
MAX_EXPORT_ROWS = 5000


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


async def export_job_rows(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    locale: str = "vi",
) -> list[dict]:
    """All of the caller org's jobs as flat export rows (newest first, capped).

    ``status`` matches the raw code OR the localized label, case-insensitively
    (so "pending" also matches ``pending_review``). Date bounds filter on
    ``created_at`` (the tool layer parses user input to aware datetimes).
    """

    org_id = principal.org_id
    permission_checker.require(principal, _RESOURCE, "export", resource_org_id=org_id)
    if org_id is None:
        return []

    from_dt = created_from
    to_dt = created_to

    stmt = (
        select(Job)
        .where(Job.org_id == org_id, Job.deleted_at.is_(None))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(MAX_EXPORT_ROWS)
    )
    if from_dt is not None:
        stmt = stmt.where(Job.created_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(Job.created_at <= to_dt)
    jobs = list((await session.execute(stmt)).scalars().all())

    status_q = (status or "").strip().lower()
    if status_q:
        jobs = [
            j
            for j in jobs
            if status_q in j.status.lower()
            or status_q in lifecycle.status_label(j.status, locale=locale).lower()
        ]

    # Live funnel counts + poster display names — batched facade reads (no N+1;
    # opportunities never touches the recruitment/users ORM directly).
    from app.modules.recruitment.application import job_application_stats_facade
    from app.modules.users.application import user_read_facade

    stats = await job_application_stats_facade.application_stats_for_jobs(
        session, [j.id for j in jobs]
    )
    owner_names = await user_read_facade.get_full_names(session, [j.posted_by for j in jobs])

    empty = job_application_stats_facade.JobAppStats()
    return [
        {
            "title": j.title,
            "status": lifecycle.status_label(j.status, locale=locale),
            "applicants": j.application_count,
            "unreviewed": stats.get(j.id, empty).unreviewed,
            "deadline": _iso(j.application_deadline),
            "created_at": _iso(j.created_at),
            "owner": owner_names.get(j.posted_by) or "",
        }
        for j in jobs
    ]
