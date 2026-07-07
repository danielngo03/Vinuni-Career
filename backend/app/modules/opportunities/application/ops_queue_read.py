"""Operations-queue read helpers for the University Operations command center.

Thin, read-only projections over ``jobs`` and ``events`` that feed the unified
university operations overview (``dashboards.application.operations_read``). Kept
separate from ``dashboard_read`` so the ops surface can evolve without touching
the per-org job dashboards, and so the aggregator never imports ORM models from
another module directly (module-boundary rule).

Everything here is a single-table SELECT of the PENDING slice (bounded — the
moderation backlog, not the whole catalog) plus in-Python SLA math via
``app.shared.moderation``. No cross-module joins.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.shared.moderation import (
    QUEUE_EVENTS,
    QUEUE_JOBS,
    queue_sla_hours,
    summarize_queue,
)


async def job_queue_stats(session: AsyncSession, *, now: datetime) -> dict:
    """SLA-aware stats for the pending job-moderation queue (all orgs)."""

    rows = (
        await session.execute(
            select(Job.submitted_at, Job.due_by).where(
                Job.moderation_status == lifecycle.MOD_PENDING,
                Job.deleted_at.is_(None),
            )
        )
    ).all()
    return summarize_queue(
        [(r.submitted_at, r.due_by) for r in rows],
        now=now,
        sla_hours=queue_sla_hours(QUEUE_JOBS),
    )


async def event_queue_stats(session: AsyncSession, *, now: datetime) -> dict:
    """SLA-aware stats for the pending event-moderation queue (all orgs)."""

    rows = (
        await session.execute(
            select(Event.submitted_at, Event.due_by).where(
                Event.moderation_status == event_lifecycle.MOD_PENDING,
                Event.deleted_at.is_(None),
            )
        )
    ).all()
    return summarize_queue(
        [(r.submitted_at, r.due_by) for r in rows],
        now=now,
        sla_hours=queue_sla_hours(QUEUE_EVENTS),
    )


async def flagged_risk_counts(session: AsyncSession) -> dict:
    """Count content flagged by moderators/AI (``moderation_status=flagged``).

    Feeds the operations "moderation risk" mix as the high-attention bucket for
    listings; the AI review queue contributes its own severity distribution.
    """

    jobs_flagged = (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.moderation_status == lifecycle.MOD_FLAGGED, Job.deleted_at.is_(None))
        )
    ).scalar_one()
    events_flagged = (
        await session.execute(
            select(func.count())
            .select_from(Event)
            .where(
                Event.moderation_status == event_lifecycle.MOD_FLAGGED,
                Event.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    return {"jobs_flagged": int(jobs_flagged), "events_flagged": int(events_flagged)}


async def pending_claimant_counts(session: AsyncSession) -> list[tuple[uuid.UUID | None, int]]:
    """``(claimed_by, count)`` for pending jobs + events, for the workload panel.

    ``claimed_by is None`` rows are the unassigned backlog; the aggregator sums
    them into a single "unassigned" bucket. Grouped in SQL so the payload is one
    row per distinct moderator, not per item.
    """

    result: list[tuple[uuid.UUID | None, int]] = []
    for model, mod_pending in (
        (Job, lifecycle.MOD_PENDING),
        (Event, event_lifecycle.MOD_PENDING),
    ):
        rows = (
            await session.execute(
                select(model.claimed_by, func.count())
                .where(model.moderation_status == mod_pending, model.deleted_at.is_(None))
                .group_by(model.claimed_by)
            )
        ).all()
        result.extend((r[0], int(r[1])) for r in rows)
    return result


async def upcoming_events(
    session: AsyncSession, *, now: datetime, limit: int = 5
) -> list[dict]:
    """Next published events starting on/after ``now`` — operations glance panel.

    PII-free: title, timing, and capacity/registration counts only. Seats-left is
    ``None`` for uncapped events.
    """

    rows = (
        await session.execute(
            select(
                Event.id,
                Event.title,
                Event.starts_at,
                Event.capacity,
                Event.registration_count,
                Event.org_id,
            )
            .where(
                Event.status == event_lifecycle.PUBLISHED,
                Event.starts_at >= now,
                Event.deleted_at.is_(None),
            )
            .order_by(Event.starts_at.asc())
            .limit(limit)
        )
    ).all()

    out: list[dict] = []
    for r in rows:
        seats_left = None if r.capacity is None else max(0, r.capacity - r.registration_count)
        out.append(
            {
                "id": str(r.id),
                "title": r.title,
                "starts_at": r.starts_at.isoformat() if r.starts_at else None,
                "capacity": r.capacity,
                "registration_count": int(r.registration_count),
                "seats_left": seats_left,
                "org_id": str(r.org_id),
            }
        )
    return out
