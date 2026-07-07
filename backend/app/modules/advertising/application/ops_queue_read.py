"""Operations-queue read helpers for sponsored-placement moderation.

Feeds the unified University Operations overview
(``dashboards.application.operations_read``) with the pending ad-review backlog,
its SLA state, and per-moderator workload. Read-only, single-table selects only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import SponsoredPlacement
from app.shared.moderation import QUEUE_ADS, queue_sla_hours, summarize_queue


async def ad_queue_stats(session: AsyncSession, *, now: datetime) -> dict:
    """SLA-aware stats for the pending sponsored-placement review queue."""

    rows = (
        await session.execute(
            select(SponsoredPlacement.submitted_at, SponsoredPlacement.due_by).where(
                SponsoredPlacement.status == lifecycle.PENDING_APPROVAL,
                SponsoredPlacement.deleted_at.is_(None),
            )
        )
    ).all()
    return summarize_queue(
        [(r.submitted_at, r.due_by) for r in rows],
        now=now,
        sla_hours=queue_sla_hours(QUEUE_ADS),
    )


async def pending_claimant_counts(session: AsyncSession) -> list[tuple[uuid.UUID | None, int]]:
    """``(claimed_by, count)`` for pending placements (workload panel)."""

    rows = (
        await session.execute(
            select(SponsoredPlacement.claimed_by, func.count())
            .where(
                SponsoredPlacement.status == lifecycle.PENDING_APPROVAL,
                SponsoredPlacement.deleted_at.is_(None),
            )
            .group_by(SponsoredPlacement.claimed_by)
        )
    ).all()
    return [(r[0], int(r[1])) for r in rows]
