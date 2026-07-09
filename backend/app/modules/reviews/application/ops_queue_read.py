"""Ops command-center queue count for reviews (reported company reviews).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade (mirrors the gate on ``review_moderation_service``). Returns
only a light ``{"open": int, "overdue": int}`` COUNT.

The open set is reviews awaiting a moderator: ``pending`` (never published) plus
``flagged`` (published then reported) — the same two figures
``review_moderation_service.list_queue`` reports as ``counts.pending`` /
``counts.flagged``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.domain import entities
from app.modules.reviews.domain.models import CompanyReview
from app.shared.moderation import QUEUE_COMPANY_REVIEW, QUEUE_SLA_HOURS

_OPEN_STATUSES = (entities.STATUS_PENDING, entities.STATUS_FLAGGED)


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for the reported-reviews queue ``kind``."""

    if kind != QUEUE_COMPANY_REVIEW:
        raise ValueError(f"unknown reviews queue kind: {kind}")

    overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_COMPANY_REVIEW])
    open_filter = (
        CompanyReview.deleted_at.is_(None),
        CompanyReview.status.in_(_OPEN_STATUSES),
    )
    open_count = int(
        (
            await session.execute(
                select(func.count()).select_from(CompanyReview).where(*open_filter)
            )
        ).scalar_one()
    )
    overdue_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CompanyReview)
                .where(*open_filter, CompanyReview.created_at < overdue_before)
            )
        ).scalar_one()
    )
    return {"open": open_count, "overdue": overdue_count}
