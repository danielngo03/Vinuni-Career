"""Ops command-center queue count for platform_support (open support cases).

Support cases are ``human_review_queue`` rows with ``source="support_case"``
(owned physically by the ``moderation`` module — there is no duplicate support
table). This facade counts them through moderation's application-layer read seam
(:func:`review_queue_service.count_pending`) instead of importing moderation's
ORM directly, exactly like :mod:`support_case_service` already does.

RBAC-free by design — the ops read-model owns the university gate before calling
this facade. Returns only a light ``{"open": int, "overdue": int}`` COUNT.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.moderation.application import review_queue_service
from app.modules.moderation.application.review_queue_service import SOURCE_SUPPORT_CASE
from app.shared.moderation import QUEUE_SLA_HOURS, QUEUE_SUPPORT_CASE


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for the open support-case queue ``kind``."""

    if kind != QUEUE_SUPPORT_CASE:
        raise ValueError(f"unknown platform_support queue kind: {kind}")

    overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_SUPPORT_CASE])
    return await review_queue_service.count_pending(
        session, source=SOURCE_SUPPORT_CASE, overdue_before=overdue_before
    )
