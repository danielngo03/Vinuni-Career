"""User lookup/creation and identity bootstrap.

Foundational identity-core service used by ``auth``. Email is normalised
(lower-cased, trimmed) so uniqueness is case-insensitive.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.models import Identity, User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(
        User.email == normalize_email(email), User.deleted_at.is_(None)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str | None,
    full_name: str | None,
    preferred_language: str = "vi",
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=password_hash,
        full_name=full_name,
        preferred_language=preferred_language,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def add_identity(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    persona: str,
    org_id: uuid.UUID | None = None,
    is_primary: bool = False,
) -> Identity:
    identity = Identity(
        user_id=user_id, persona=persona, org_id=org_id, is_primary=is_primary
    )
    session.add(identity)
    await session.flush()
    return identity


async def list_identities(
    session: AsyncSession, user_id: uuid.UUID
) -> list[Identity]:
    stmt = (
        select(Identity)
        .where(Identity.user_id == user_id)
        .order_by(Identity.is_primary.desc(), Identity.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_identity(
    session: AsyncSession, *, identity_id: uuid.UUID, user_id: uuid.UUID
) -> Identity | None:
    stmt = select(Identity).where(
        Identity.id == identity_id, Identity.user_id == user_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def primary_identity(
    session: AsyncSession, user_id: uuid.UUID
) -> Identity | None:
    identities = await list_identities(session, user_id)
    return identities[0] if identities else None


async def get_many(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, User]:
    """Batch fetch active users -> ``{user_id: User}`` (missing/deleted ids absent).

    One query for a set of ids so callers that need several users at once (e.g. the
    partner candidate-ranking triage resolving revealed applicant identities) avoid
    an N+1 of :func:`get_by_id`.
    """

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(User).where(User.id.in_(ids), User.deleted_at.is_(None))
        )
    ).scalars().all()
    return {u.id: u for u in rows}
