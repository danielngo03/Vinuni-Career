"""Ops command-center queue counts for career_services (CV review + at-risk).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade. Returns only a light ``{"open": int, "overdue": int}``
COUNT, never student rows or PII.

- ``cv_review`` — CV review queue items still open
  (:data:`catalog.CV_REVIEW_OPEN_STATUSES`: queued / in_review / changes_requested).
- ``at_risk`` — at-risk flags still open
  (:data:`catalog.RISK_OPEN_STATUSES`: open / in_progress).

These read models are platform-wide here (governance ops center); per-tenant
counselor scoping stays in the counselor-facing services, not this roll-up.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import AtRiskFlag, CvReviewQueueItem
from app.shared.moderation import QUEUE_AT_RISK, QUEUE_CV_REVIEW, QUEUE_SLA_HOURS


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for one career-services queue ``kind``."""

    if kind == QUEUE_CV_REVIEW:
        overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_CV_REVIEW])
        cv_open = CvReviewQueueItem.status.in_(list(catalog.CV_REVIEW_OPEN_STATUSES))
        open_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(CvReviewQueueItem).where(cv_open)
                )
            ).scalar_one()
        )
        overdue_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(CvReviewQueueItem)
                    .where(cv_open, CvReviewQueueItem.created_at < overdue_before)
                )
            ).scalar_one()
        )
        return {"open": open_count, "overdue": overdue_count}

    if kind == QUEUE_AT_RISK:
        overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_AT_RISK])
        risk_open = AtRiskFlag.status.in_(list(catalog.RISK_OPEN_STATUSES))
        open_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(AtRiskFlag).where(risk_open)
                )
            ).scalar_one()
        )
        overdue_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(AtRiskFlag)
                    .where(risk_open, AtRiskFlag.created_at < overdue_before)
                )
            ).scalar_one()
        )
        return {"open": open_count, "overdue": overdue_count}

    raise ValueError(f"unknown career_services queue kind: {kind}")
