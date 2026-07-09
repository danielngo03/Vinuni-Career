"""Ops command-center queue count for advertising (sponsored-ad review).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade. Returns only a light ``{"open": int, "overdue": int}``
COUNT, never rows.

The counted queue is the SPONSORED PLACEMENT approval queue
(``status == pending_approval``): the primary university advertising decision
that ``/university/advertising`` surfaces (a placement carries its ad
creatives). Overdue is derived from the shared SLA window against
``created_at`` (the placement stores a ``due_by`` column, but the ops policy
uses the created-at cutoff for every non-job/event queue for a single, uniform
overdue definition).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import SponsoredPlacement
from app.shared.moderation import QUEUE_AD_CREATIVE, QUEUE_SLA_HOURS


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for the sponsored-ad review queue ``kind``."""

    if kind != QUEUE_AD_CREATIVE:
        raise ValueError(f"unknown advertising queue kind: {kind}")

    overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_AD_CREATIVE])
    open_filter = (
        SponsoredPlacement.deleted_at.is_(None),
        SponsoredPlacement.status == lifecycle.PENDING_APPROVAL,
    )
    open_count = int(
        (
            await session.execute(
                select(func.count()).select_from(SponsoredPlacement).where(*open_filter)
            )
        ).scalar_one()
    )
    overdue_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SponsoredPlacement)
                .where(*open_filter, SponsoredPlacement.created_at < overdue_before)
            )
        ).scalar_one()
    )
    return {"open": open_count, "overdue": overdue_count}
