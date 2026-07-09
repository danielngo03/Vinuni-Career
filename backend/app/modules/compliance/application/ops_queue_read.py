"""Ops command-center queue count for compliance (open privacy requests).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade. Returns only a light ``{"open": int, "overdue": int}``
COUNT, never request bodies or PII. The open set is ``pending`` + ``processing``
(:data:`OPEN_STATUSES`); overdue uses the shared 30-day privacy SLA window
against ``created_at``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compliance.domain.models import OPEN_STATUSES, PrivacyRequest
from app.shared.moderation import QUEUE_PRIVACY_REQUEST, QUEUE_SLA_HOURS


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for the privacy-request queue ``kind``."""

    if kind != QUEUE_PRIVACY_REQUEST:
        raise ValueError(f"unknown compliance queue kind: {kind}")

    overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_PRIVACY_REQUEST])
    open_statuses = list(OPEN_STATUSES)
    open_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PrivacyRequest)
                .where(PrivacyRequest.status.in_(open_statuses))
            )
        ).scalar_one()
    )
    overdue_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PrivacyRequest)
                .where(
                    PrivacyRequest.status.in_(open_statuses),
                    PrivacyRequest.created_at < overdue_before,
                )
            )
        ).scalar_one()
    )
    return {"open": open_count, "overdue": overdue_count}
