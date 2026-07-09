"""Read-only seam over onboarding state for other modules.

Lets callers (today: the auth ``/me`` affiliation resolver) read a coarse
onboarding fact without importing the onboarding ORM directly. One indexed
lookup by ``user_id``; no writes, no PII beyond what the caller already holds.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.onboarding.domain.models import OnboardingState


async def get_seeker_type(
    session: AsyncSession, *, user_id: uuid.UUID
) -> str | None:
    """Return the onboarding seeker sub-type for ``user_id`` (or ``None``).

    Values: ``student`` | ``professional`` | ``fresh_graduate`` — used only to
    derive a provisional affiliation label before a student verifies.
    """

    return (
        await session.execute(
            select(OnboardingState.seeker_type).where(
                OnboardingState.user_id == user_id
            )
        )
    ).scalar_one_or_none()


__all__ = ["get_seeker_type"]
