"""FastAPI auth dependencies: principal resolution and request context.

``get_current_auth`` decodes the bearer access token, enforces JTI revocation and
session liveness, loads the user + active identity, and builds the
:class:`Principal` the service-layer :class:`PermissionChecker` consumes. Any
failure surfaces as ``401 AUTH_REQUIRED`` — authorization (``403``) is decided
later, in the service layer (``docs/API_CONTRACTS.md``, ``docs/SECURITY_PRIVACY.md``).

``require_superadmin`` is defined here (canonical shared location) so that any
module can import it without coupling to ``ai_ops``.  The ``ai_ops`` module
re-imports it from here for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.application.context import RequestContext, context_from_request
from app.modules.auth.domain.models import Session
from app.modules.auth.infrastructure import token_revocation
from app.modules.auth.infrastructure.jwt import (
    AccessClaims,
    InvalidTokenError,
    decode_access_token,
)
from app.modules.organization.application import grant_resolver
from app.modules.users.application import user_service
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal


@dataclass(slots=True)
class CurrentAuth:
    principal: Principal
    claims: AccessClaims
    ctx: RequestContext


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthRequiredError()
    return token.strip()


async def get_current_auth(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> CurrentAuth:
    from datetime import UTC, datetime

    token = _bearer_token(request)
    try:
        claims = decode_access_token(token)
    except InvalidTokenError as exc:
        raise AuthRequiredError() from exc

    if await token_revocation.is_revoked(claims.jti):
        raise AuthRequiredError()

    sess = (
        await session.execute(select(Session).where(Session.id == claims.session_id))
    ).scalar_one_or_none()
    if sess is None or not sess.is_active(now=datetime.now(tz=UTC)):
        raise AuthRequiredError()

    user = await user_service.get_by_id(session, claims.user_id)
    if user is None or not user.is_active:
        raise AuthRequiredError()

    identity = await user_service.get_identity(
        session, identity_id=claims.identity_id, user_id=user.id
    )
    if identity is None:
        raise AuthRequiredError()

    permissions, department_grants = await grant_resolver.resolve_scoped_grants(
        session, user_id=user.id, identity=identity
    )
    principal = Principal(
        user_id=user.id,
        persona=identity.persona,
        org_id=identity.org_id,
        is_superadmin=user.is_superadmin,
        permissions=permissions,
        department_grants=department_grants,
    )
    return CurrentAuth(
        principal=principal,
        claims=claims,
        ctx=context_from_request(request),
    )


async def get_current_principal(
    auth: CurrentAuth = Depends(get_current_auth),
) -> Principal:
    return auth.principal


def get_request_context(request: Request) -> RequestContext:
    return context_from_request(request)


async def require_superadmin(
    auth: CurrentAuth = Depends(get_current_auth),
) -> Principal:
    """Return the principal only if the caller is a platform superadmin.

    Canonical shared location — import from here, not from ``ai_ops``.

    Raises:
        AuthRequiredError: propagated from ``get_current_auth`` when token is absent/invalid (401).
        PermissionDeniedError: when the caller is authenticated but not a superadmin (403).
    """

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()
    return auth.principal
