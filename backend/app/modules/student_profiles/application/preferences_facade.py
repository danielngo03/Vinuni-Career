"""Read facade: a student's confirmed ranking preferences (spec §4).

The ``discovery`` ranker personalizes authenticated-student recommendations from
*confirmed first-party preferences* without deep-importing the
``StudentProfile`` ORM. This facade returns a small, leak-safe
:class:`RankingPreferences` DTO (job types, location, field/degree, graduation
year) — never contact PII, phone, raw visibility settings, or completion
internals. ``None`` when the student has no profile yet (the ranker then simply
treats preferences as absent).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_profiles.domain.models import StudentProfile


@dataclass(frozen=True, slots=True)
class RankingPreferences:
    """Confirmed, privacy-safe preference signals for organic personalization."""

    is_open_to_work: bool
    job_types: list[str]  # open_to_work_types (internship | full_time | ...)
    location_city: str | None
    location_country: str | None
    field: str | None  # major
    degree_level: str | None
    graduation_year: int | None

    @property
    def has_signal(self) -> bool:
        return bool(
            self.job_types
            or self.location_city
            or self.field
            or self.is_open_to_work
        )


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
        job_types=list(profile.open_to_work_types or []),
        location_city=profile.location_city,
        location_country=profile.location_country,
        field=profile.major,
        degree_level=profile.degree_level,
        graduation_year=profile.graduation_year,
    )
