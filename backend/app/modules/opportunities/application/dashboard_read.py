"""Read-only aggregation helpers for the persona dashboards (no writes, no audit).

Scoped-by-argument read functions consumed by the ``dashboards`` application
services, which own the persona RBAC gate (RBAC-free here, like
:mod:`public_read`). Partner helpers are org-scoped; the moderation helpers are
platform-wide (a university moderator reviews pending jobs across all orgs) and
are only ever called after the dashboard's university gate.

Every status code is paired with a localized label (raw enum codes never reach the
client).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade


def _iso(value) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Partner (org) scope                                                         #
# --------------------------------------------------------------------------- #


async def count_org_jobs_by_status(
    session: AsyncSession, *, org_id: uuid.UUID
) -> dict[str, int]:
    """Counts of the org's own (non-deleted) jobs grouped by lifecycle status."""

    rows = (
        await session.execute(
            select(Job.status, func.count())
            .where(Job.org_id == org_id, Job.deleted_at.is_(None))
            .group_by(Job.status)
        )
    ).all()
    by_status: dict[str, int] = {}
    for status, count in rows:
        by_status[status] = count
    return {
        "active": by_status.get(lifecycle.ACTIVE, 0),
        "draft": by_status.get(lifecycle.DRAFT, 0),
        "pending_review": by_status.get(lifecycle.PENDING_REVIEW, 0),
        "rejected": by_status.get(lifecycle.REJECTED, 0),
        "closed": by_status.get(lifecycle.CLOSED, 0),
    }


async def list_org_jobs_needing_attention(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    limit: int,
    locale: str = "vi",
) -> list[dict]:
    """The org's jobs that need partner action: drafts, rejected, pending review."""

    attention = (lifecycle.DRAFT, lifecycle.REJECTED, lifecycle.PENDING_REVIEW)
    rows = (
        await session.execute(
            select(Job)
            .where(
                Job.org_id == org_id,
                Job.deleted_at.is_(None),
                Job.status.in_(attention),
            )
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(max(limit, 0))
        )
    ).scalars().all()
    return [
        {
            "id": str(job.id),
            "title": job.title,
            "status": job.status,
            "status_label": lifecycle.status_label(job.status, locale=locale),
            "application_count": job.application_count,
        }
        for job in rows
    ]


# --------------------------------------------------------------------------- #
# University moderation scope (platform-wide)                                 #
# --------------------------------------------------------------------------- #


async def count_pending_moderation_jobs(session: AsyncSession) -> int:
    """Jobs awaiting university moderation across all orgs."""

    return (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.deleted_at.is_(None), Job.status == lifecycle.PENDING_REVIEW)
        )
    ).scalar_one()


async def list_pending_moderation_jobs(
    session: AsyncSession, *, limit: int, locale: str = "vi"
) -> list[dict]:
    """Oldest-first pending-review jobs (with employer) for the moderation queue."""

    jobs = (
        await session.execute(
            select(Job)
            .where(Job.deleted_at.is_(None), Job.status == lifecycle.PENDING_REVIEW)
            .order_by(Job.submitted_at.asc().nulls_last(), Job.created_at.asc())
            .limit(max(limit, 0))
        )
    ).scalars().all()
    names = await org_reporting_facade.display_names_for(
        session, (j.org_id for j in jobs)
    )
    return [
        {
            "id": str(job.id),
            "title": job.title,
            "company_name": names.get(job.org_id),
            "submitted_at": _iso(job.submitted_at),
        }
        for job in jobs
    ]


async def count_events_by_status_for_org(
    session: AsyncSession, *, org_id: uuid.UUID
) -> dict[str, int]:
    """Event status counts for an org's CRM rollup (no ``Event`` ORM export)."""

    from app.modules.opportunities.domain.event_models import Event

    rows = (
        await session.execute(
            select(Event.status, func.count())
            .where(Event.org_id == org_id, Event.deleted_at.is_(None))
            .group_by(Event.status)
        )
    ).all()
    return {status: count for status, count in rows}
