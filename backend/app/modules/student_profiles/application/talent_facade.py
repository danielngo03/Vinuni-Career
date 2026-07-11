"""Student-profiles read seam for talent-pool discovery.

The ``talent_pool`` module gates indexing/search on student consent + visibility
and shows candidate identity cards, but must NOT reach into
``student_profiles.domain.models`` (module-boundary guard,
``docs/ARCHITECTURE.md`` §8). This facade owns the ``StudentProfile`` ORM and
exposes only the consent/visibility signals + safe display fields as plain
dataclasses/ids.

Consent proxy (owner follow-up — no dedicated ``talent_pool_opt_in`` flag yet):
a student is DISCOVERABLE when ``is_open_to_work = True`` AND
``profile_visibility != private``. Visibility scope: an external partner sees only
``public`` profiles; VinUni personas + superadmin also see ``vinuni_only``.

Never returns contact PII (email/phone) or the raw avatar storage key — only the
safe ``avatar_url`` pointer, matching ``talent_pool_service`` (passive search).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import StudentProfile
from app.modules.users.application import user_read_facade

_DISCOVERABLE_VISIBILITY = (vocab.VISIBILITY_PUBLIC, vocab.VISIBILITY_VINUNI_ONLY)


@dataclass(frozen=True, slots=True)
class TalentCard:
    """Safe identity summary for a talent-pool result (no contact PII)."""

    profile_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str | None
    avatar_url: str | None
    location_city: str | None
    location_country: str | None


def _visibility_scope(*, include_vinuni_only: bool) -> tuple[str, ...]:
    return _DISCOVERABLE_VISIBILITY if include_vinuni_only else (vocab.VISIBILITY_PUBLIC,)


def _avatar_url(profile: StudentProfile) -> str | None:
    if not getattr(profile, "avatar_path", None):
        return None
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{profile.id}/avatar?v={profile.version}"


async def is_discoverable(session: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """True when the user has a discoverable (consented, non-private) profile."""

    row = (
        await session.execute(
            select(StudentProfile.profile_visibility, StudentProfile.is_open_to_work).where(
                StudentProfile.user_id == user_id,
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).first()
    return bool(
        row is not None
        and row.is_open_to_work
        and row.profile_visibility in _DISCOVERABLE_VISIBILITY
    )


async def list_discoverable_user_ids(
    session: AsyncSession, *, include_vinuni_only: bool = True
) -> list[uuid.UUID]:
    """User ids of every discoverable student within the caller's visibility scope."""

    scope = _visibility_scope(include_vinuni_only=include_vinuni_only)
    rows = (
        await session.execute(
            select(StudentProfile.user_id).where(
                StudentProfile.deleted_at.is_(None),
                StudentProfile.is_open_to_work.is_(True),
                StudentProfile.profile_visibility.in_(scope),
            )
        )
    ).scalars().all()
    return list(rows)


async def talent_cards(
    session: AsyncSession, *, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TalentCard]:
    """Safe identity cards keyed by ``user_id`` for the given users.

    Carries the real display name + safe avatar URL + coarse location. Never
    contact PII. Users without a profile are simply absent from the map.
    """

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    profiles = (
        (
            await session.execute(
                select(StudentProfile).where(
                    StudentProfile.user_id.in_(ids),
                    StudentProfile.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    names = await user_read_facade.get_full_names(session, (p.user_id for p in profiles))
    return {
        p.user_id: TalentCard(
            profile_id=p.id,
            user_id=p.user_id,
            display_name=names.get(p.user_id),
            avatar_url=_avatar_url(p),
            location_city=p.location_city,
            location_country=p.location_country,
        )
        for p in profiles
    }
