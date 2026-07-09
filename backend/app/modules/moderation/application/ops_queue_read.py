"""Ops command-center queue counts for moderation (content reports + AI-flagged).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade (mirrors ``review_queue_service.list_items_unchecked``).
Returns only a light ``{"open": int, "overdue": int}`` COUNT.

- ``content_report`` — user-submitted abuse reports (``content_reports``) still
  ``PENDING`` triage.
- ``ai_flagged`` — the AI advisory human-review queue (``human_review_queue``)
  still ``PENDING``, EXCLUDING ``support_case`` rows (those are the
  platform_support queue, counted separately).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.moderation.application import review_queue_service
from app.modules.moderation.domain.models import (
    REPORT_STATUS_PENDING,
    SOURCE_SUPPORT_CASE,
    ContentReport,
)
from app.shared.moderation import QUEUE_AI_FLAGGED, QUEUE_CONTENT_REPORT, QUEUE_SLA_HOURS


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for one moderation trust/safety queue ``kind``."""

    if kind == QUEUE_CONTENT_REPORT:
        overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_CONTENT_REPORT])
        open_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ContentReport)
                    .where(ContentReport.status == REPORT_STATUS_PENDING)
                )
            ).scalar_one()
        )
        overdue_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ContentReport)
                    .where(
                        ContentReport.status == REPORT_STATUS_PENDING,
                        ContentReport.created_at < overdue_before,
                    )
                )
            ).scalar_one()
        )
        return {"open": open_count, "overdue": overdue_count}

    if kind == QUEUE_AI_FLAGGED:
        overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_AI_FLAGGED])
        return await review_queue_service.count_pending(
            session,
            exclude_sources=frozenset({SOURCE_SUPPORT_CASE}),
            overdue_before=overdue_before,
        )

    raise ValueError(f"unknown moderation queue kind: {kind}")
