"""Resolve a :class:`Principal` from a raw access token (WebSocket-friendly seam).

The HTTP path (:func:`auth.api.deps.get_current_auth`) resolves the principal from the
``Authorization`` header + a FastAPI ``Request``. WebSocket handshakes carry the token in
a query param instead, and live in OTHER modules (e.g. ``messaging`` realtime). This
application-layer function encapsulates the same decode + revocation + session/user/
identity + grant resolution so those modules never import ``auth``'s domain/infrastructure
directly (module-boundary rule; ``docs/ARCHITECTURE.md`` §8). Returns ``None`` on any
failure — the caller closes the socket.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.models import Session
from app.modules.auth.infrastructure import token_revocation
from app.modules.auth.infrastructure.jwt import (
    InvalidTokenError,
    decode_access_token,
)
from app.modules.organization.application import grant_resolver
from app.modules.users.application import user_service
from app.shared.permissions import Principal


async def principal_from_access_token(
    session: AsyncSession, token: str
) -> Principal | None:
    """Return the acting :class:`Principal` for ``token``, or ``None`` if invalid."""

    if not token:
        return None
    try:
        claims = decode_access_token(token)
    except InvalidTokenError:
        return None
    if await token_revocation.is_revoked(claims.jti):
        return None

    sess = (
        await session.execute(select(Session).where(Session.id == claims.session_id))
    ).scalar_one_or_none()
    if sess is None or not sess.is_active(now=datetime.now(tz=UTC)):
        return None

    user = await user_service.get_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        return None
    identity = await user_service.get_identity(
        session, identity_id=claims.identity_id, user_id=user.id
    )
    if identity is None:
        return None

    permissions = await grant_resolver.resolve_grants(
        session, user_id=user.id, identity=identity
    )
    return Principal(
        user_id=user.id,
        persona=identity.persona,
        org_id=identity.org_id,
        is_superadmin=user.is_superadmin,
        permissions=permissions,
    )
