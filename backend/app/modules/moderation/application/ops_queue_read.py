"""Operations-queue read helpers for the AI human-review queue.

Feeds the unified University Operations overview
(``dashboards.application.operations_read``): the pending advisory-finding
backlog, its SLA state (derived from ``created_at`` + the 4h AI-flagged SLA), and
the severity distribution that drives the "moderation risk" mix. Read-only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.moderation.domain.models import STATUS_PENDING, HumanReviewItem
from app.shared.moderation import QUEUE_AI_REVIEW, queue_sla_hours, summarize_queue


async def ai_review_stats(session: AsyncSession, *, now: datetime) -> dict:
    """SLA-aware stats for the pending AI human-review queue.

    The queue stores no explicit ``due_by``; ``summarize_queue`` derives one from
    ``created_at`` plus the 4h AI-flagged SLA (BUSINESS_LOGIC.md §11).
    """

    rows = (
        await session.execute(
            select(HumanReviewItem.created_at).where(
                HumanReviewItem.status == STATUS_PENDING
            )
        )
    ).all()
    return summarize_queue(
        [(r.created_at, None) for r in rows],
        now=now,
        sla_hours=queue_sla_hours(QUEUE_AI_REVIEW),
    )


async def severity_mix(session: AsyncSession) -> dict:
    """Count pending review items by severity (``high`` / ``medium`` / ``low``)."""

    rows = (
        await session.execute(
            select(HumanReviewItem.severity, func.count())
            .where(HumanReviewItem.status == STATUS_PENDING)
            .group_by(HumanReviewItem.severity)
        )
    ).all()
    mix = {"high": 0, "medium": 0, "low": 0}
    for severity, count in rows:
        if severity in mix:
            mix[severity] = int(count)
    return mix
