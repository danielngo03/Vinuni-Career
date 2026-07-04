"""Internal user/identity read facade for cross-module surfaces.

Other modules (``recruitment``, ``messaging``, ``notifications``, ``billing``,
``dashboards``, ``student_profiles``) resolve user/identity shape through this
seam instead of importing the ``User``/``Identity`` ORM, so the module boundary
holds (`docs/ARCHITECTURE.md`: communicate through interfaces/read models).

Unlike ``student_directory_facade`` (display-name-only, no PII — used by public
reviews), this facade is for **internal, already-permission-checked** surfaces
(partner-owned recruitment pipelines, in-app notification dispatch, university
platform reporting) that legitimately need contact fields (email) or identity
rows (persona/org membership) to do their job. Callers remain responsible for
their own RBAC gate before calling in; this facade does not re-check permission.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.models import Identity, NotificationPreference, User


@dataclass(frozen=True)
class UserContact:
    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool


@dataclass(frozen=True)
class IdentityRef:
    user_id: uuid.UUID
    persona: str
    org_id: uuid.UUID | None


async def get_user_contact(
    session: AsyncSession, user_id: uuid.UUID | None
) -> UserContact | None:
    if user_id is None:
        return None
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return None
    return UserContact(
        id=user.id, email=user.email, full_name=user.full_name, is_active=user.is_active
    )


async def get_user_contacts(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, UserContact]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(select(User).where(User.id.in_(ids)))
    ).scalars().all()
    return {
        u.id: UserContact(
            id=u.id, email=u.email, full_name=u.full_name, is_active=u.is_active
        )
        for u in rows
    }


async def get_full_names(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(User.id, User.full_name).where(User.id.in_(ids))
        )
    ).all()
    return {row.id: row.full_name for row in rows}


async def get_full_name(
    session: AsyncSession, user_id: uuid.UUID | None
) -> str | None:
    if user_id is None:
        return None
    return (
        await session.execute(select(User.full_name).where(User.id == user_id))
    ).scalar_one_or_none()


async def get_email(session: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    return (
        await session.execute(select(User.email).where(User.id == user_id))
    ).scalar_one_or_none()


async def existing_user_ids(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    """The subset of ``user_ids`` that resolve to a real user row."""

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return set()
    return set(
        (await session.execute(select(User.id).where(User.id.in_(ids)))).scalars().all()
    )


async def get_preferred_language(
    session: AsyncSession, user_id: uuid.UUID
) -> str | None:
    return (
        await session.execute(
            select(User.preferred_language).where(User.id == user_id)
        )
    ).scalar_one_or_none()


async def get_notification_in_app_preference(
    session: AsyncSession, *, user_id: uuid.UUID, category: str
) -> bool | None:
    """The recipient's stored in-app preference for ``category``, or ``None`` if unset."""

    row = (
        await session.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == category,
            )
        )
    ).scalar_one_or_none()
    return None if row is None else bool(row.in_app_enabled)


async def is_org_member(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> bool:
    found = (
        await session.execute(
            select(Identity.id).where(
                Identity.user_id == user_id, Identity.org_id == org_id
            )
        )
    ).first()
    return found is not None


async def get_identity_persona_in_org(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> str | None:
    """The caller's identity ``persona`` within ``org_id``, or ``None`` if not a member."""

    return (
        await session.execute(
            select(Identity.persona).where(
                Identity.user_id == user_id, Identity.org_id == org_id
            )
        )
    ).scalar_one_or_none()


async def get_identities_for_users(
    session: AsyncSession, user_ids: Iterable[uuid.UUID]
) -> list[IdentityRef]:
    """All identity rows (persona + org membership) for the given users."""

    ids = list({i for i in user_ids if i is not None})
    if not ids:
        return []
    rows = (
        await session.execute(
            select(Identity.user_id, Identity.persona, Identity.org_id).where(
                Identity.user_id.in_(ids)
            )
        )
    ).all()
    return [
        IdentityRef(user_id=row.user_id, persona=str(row.persona), org_id=row.org_id)
        for row in rows
    ]


async def get_user_ids_by_persona(
    session: AsyncSession, persona: str, *, limit: int | None = None
) -> list[uuid.UUID]:
    """Distinct user ids holding ``persona`` in any identity row (e.g. university staff)."""

    stmt = select(Identity.user_id).where(Identity.persona == persona).distinct()
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())


@dataclass(frozen=True)
class PersonaContact:
    id: uuid.UUID
    full_name: str | None
    email: str
    preferred_language: str | None


async def list_active_persona_contacts(
    session: AsyncSession, persona: str, *, limit: int
) -> list[PersonaContact]:
    """Active, non-deleted users holding ``persona`` (e.g. for a batch digest sweep)."""

    rows = (
        await session.execute(
            select(User.id, User.full_name, User.email, User.preferred_language)
            .join(Identity, Identity.user_id == User.id)
            .where(
                Identity.persona == persona,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .distinct()
            .order_by(User.id)
            .limit(limit)
        )
    ).all()
    return [
        PersonaContact(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            preferred_language=row.preferred_language,
        )
        for row in rows
    ]


async def count_identities_by_persona(session: AsyncSession, persona: str) -> int:
    """Count of ``identities`` rows with ``persona`` (not deduped by user)."""

    from sqlalchemy import func

    return (
        await session.execute(
            select(func.count()).select_from(Identity).where(Identity.persona == persona)
        )
    ).scalar_one()
