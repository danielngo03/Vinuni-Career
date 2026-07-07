"""Operations-queue read helper for pending partner registrations.

Feeds the unified University Operations overview
(``dashboards.application.operations_read``). Partner registrations store no
``due_by``; the 48h SLA (BUSINESS_LOGIC.md §11) is derived from ``created_at``.
Read-only, single-table select.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.domain.models import PartnerRegistrationRequest
from app.shared.moderation import (
    QUEUE_PARTNER_REGISTRATIONS,
    queue_sla_hours,
    summarize_queue,
)

_PENDING = "pending_review"


async def partner_registration_stats(session: AsyncSession, *, now: datetime) -> dict:
    """SLA-aware stats for the pending partner-registration review queue."""

    rows = (
        await session.execute(
            select(PartnerRegistrationRequest.created_at).where(
                PartnerRegistrationRequest.status == _PENDING
            )
        )
    ).all()
    return summarize_queue(
        [(r.created_at, None) for r in rows],
        now=now,
        sla_hours=queue_sla_hours(QUEUE_PARTNER_REGISTRATIONS),
    )
