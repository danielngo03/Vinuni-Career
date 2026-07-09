"""Ops command-center queue count for organization (partner registrations).

Application-layer read seam consumed by the university ops command-center read
model. RBAC-free by design — the ops read-model owns the university gate before
calling this facade (partner review is platform-wide governance, mirroring
:mod:`partner_registration_service`). Returns only a light
``{"open": int, "overdue": int}`` COUNT, never rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.domain.models import PartnerRegistrationRequest
from app.shared.moderation import QUEUE_PARTNER_REGISTRATION, QUEUE_SLA_HOURS

# Matches ``partner_registration_service`` — a request awaiting a moderator's
# decision (no shared status constant exists in the domain vocabulary yet).
_PENDING_REVIEW = "pending_review"


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for the partner-registration review queue ``kind``."""

    if kind != QUEUE_PARTNER_REGISTRATION:
        raise ValueError(f"unknown organization queue kind: {kind}")

    overdue_before = now - timedelta(hours=QUEUE_SLA_HOURS[QUEUE_PARTNER_REGISTRATION])
    open_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PartnerRegistrationRequest)
                .where(PartnerRegistrationRequest.status == _PENDING_REVIEW)
            )
        ).scalar_one()
    )
    overdue_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PartnerRegistrationRequest)
                .where(
                    PartnerRegistrationRequest.status == _PENDING_REVIEW,
                    PartnerRegistrationRequest.created_at < overdue_before,
                )
            )
        ).scalar_one()
    )
    return {"open": open_count, "overdue": overdue_count}
