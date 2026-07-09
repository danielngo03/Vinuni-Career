"""Cross-module user/identity write facade for `auth`'s registration and login
flows.

`auth`'s registration/login use cases create and mutate ``User``/``Identity``
rows and per-account defaults (``UserPreference``) as part of authenticating a
principal, but ``users`` owns those ORM rows. ``auth`` communicates through
this facade instead of importing ``users.domain.models`` directly
(`docs/ARCHITECTURE.md` Sec 8). ``create_user``/``create_identity`` delegate to
the same ``user_service`` helpers, and ``set_preference`` builds the same
``UserPreference`` row, that ``auth_service.py`` previously called/constructed
inline — behaviour is unchanged, this is a structural move only.

``User`` and ``Identity`` are re-exported (not duplicated/wrapped) so ``auth``
can type its own request/response shapes (e.g. a login result carrying the
authenticated user + active identity) against the real mapped rows it already
fetches via ``user_service``, without importing the ORM module directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.application import user_service
from app.modules.users.domain.models import Identity, User, UserPreference

__all__ = [
    "Identity",
    "User",
    "create_identity",
    "create_user",
    "set_preference",
    "update_identity_persona",
]


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password_hash: str | None,
    full_name: str | None,
    preferred_language: str = "vi",
) -> User:
    return await user_service.create_user(
        session,
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        preferred_language=preferred_language,
    )


async def create_identity(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    persona: str,
    org_id: uuid.UUID | None = None,
    is_primary: bool = False,
) -> Identity:
    return await user_service.add_identity(
        session,
        user_id=user_id,
        persona=persona,
        org_id=org_id,
        is_primary=is_primary,
    )


async def update_identity_persona(
    session: AsyncSession, *, user_id: uuid.UUID, persona: str
) -> Identity | None:
    """Update the primary identity persona for a user (e.g. student → partner_member)."""
    from sqlalchemy import select

    from app.modules.users.domain.models import Identity as _Identity

    stmt = select(_Identity).where(_Identity.user_id == user_id, _Identity.is_primary.is_(True))
    identity = (await session.execute(stmt)).scalar_one_or_none()
    if identity is not None:
        identity.persona = persona
        await session.flush()
    return identity


async def set_preference(
    session: AsyncSession, *, user_id: uuid.UUID, locale: str, timezone: str
) -> UserPreference:
    """Create the default per-account preference row for a newly registered
    user (locale/timezone only; notification/theme fields keep their column
    defaults, matching the previous inline construction)."""

    preference = UserPreference(user_id=user_id, locale=locale, timezone=timezone)
    session.add(preference)
    return preference
