"""Read facade: a student's confirmed ranking preferences (spec §4).

The ``discovery`` ranker personalizes authenticated-student recommendations from
*confirmed first-party preferences* without deep-importing the ``StudentProfile``
ORM. Since the profile is now identity-only (owner decision 2026-07-06), the only
confirmed preference signals it can supply are ``is_open_to_work`` and the
student's location. The career-derived signals (job types, field/major, degree,
graduation year) no longer exist on the profile — they are kept on the DTO as
inert ``[]`` / ``None`` so downstream consumers (ranking, analytics) keep
compiling and simply treat them as "no signal" rather than churning. Career
personalization now comes from the student's CV(s), not this facade.

Returns ``None`` when the student has no profile yet (the ranker then treats
preferences as absent).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_profiles.domain.models import StudentProfile


@dataclass(frozen=True, slots=True)
class RankingPreferences:
    """Confirmed, privacy-safe preference signals for organic personalization.

    Only ``is_open_to_work`` and location are live signals now. The remaining
    career fields are retained (inert) so ranking/analytics consumers that read
    them keep working without change; they always resolve to "no signal".
    """

    is_open_to_work: bool
    location_city: str | None
    location_country: str | None
    job_types: list[str] = field(default_factory=list)  # inert: career content moved to CVs
    field: str | None = None  # inert
    degree_level: str | None = None  # inert
    graduation_year: int | None = None  # inert

    @property
    def has_signal(self) -> bool:
        return bool(self.location_city or self.is_open_to_work)


async def get_ranking_preferences(
    session: AsyncSession, *, user_id: uuid.UUID
) -> RankingPreferences | None:
    """Return the student's confirmed preference DTO, or ``None`` if no profile."""

    profile = (
        await session.execute(
            select(StudentProfile).where(
                StudentProfile.user_id == user_id,
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        return None
    return RankingPreferences(
        is_open_to_work=bool(profile.is_open_to_work),
        location_city=profile.location_city,
        location_country=profile.location_country,
    )
