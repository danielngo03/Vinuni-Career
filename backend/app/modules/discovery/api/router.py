"""Discovery HTTP routes under ``/api/v1/discovery`` (public, optional-auth).

HTTP-only: validate, resolve optional auth + the first-party discovery cookie, and
delegate to the services (which enforce the privacy allowlist, derive scope, and
own the commit). Responses carry NO internal data — ``POST /events`` returns only
``{"recorded": true}`` and never the session id, coarse tags, or scope. The session
id lives only in the httpOnly ``vinuni_discovery`` cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import get_current_auth
from app.modules.auth.application.context import RequestContext, context_from_request
from app.modules.discovery.api.schemas import (
    DiscoveryEventRequest,
    DiscoverySessionResetRequest,
)
from app.modules.discovery.application import event_service, session_service
from app.modules.discovery.domain.models import DiscoverySession
from app.shared.permissions import GUEST, Principal
from app.shared.responses import success

router = APIRouter(prefix="/discovery", tags=["discovery"])

# httpOnly cookie scoped to the whole API so the discovery session id is also sent
# to the discovery-reading GET endpoints (``/marketplace/overview``,
# ``/jobs/recommendations``, ``/jobs/{id}/similar``) — otherwise guest coarse
# signals are stored server-side but never read back, defeating guest
# personalization. The cookie holds ONLY a random session id (no PII).
_COOKIE_PATH = "/api/v1"


async def _optional_auth(
    request: Request, session: AsyncSession
) -> tuple[Principal, RequestContext]:
    """Resolve the principal if a valid bearer token is present; else GUEST.

    Public endpoint: a missing/invalid token degrades to an anonymous guest rather
    than raising — authentication is optional here (spec §8).
    """

    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            return auth.principal, auth.ctx
        except Exception:  # noqa: BLE001 - optional auth: never block on a bad token
            pass
    return GUEST, context_from_request(request)


def _set_discovery_cookie(response: Response, discovery_session: DiscoverySession) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.discovery_session_cookie_name,
        value=str(discovery_session.id),
        max_age=settings.discovery_cookie_max_age,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _clear_discovery_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.discovery_session_cookie_name,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


@router.post("/events", summary="Record a privacy-safe discovery analytics event")
async def record_discovery_event(
    body: DiscoveryEventRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    principal, ctx = await _optional_auth(request, session)
    cookie_id = request.cookies.get(get_settings().discovery_session_cookie_name)

    discovery_session, result = await event_service.ingest(
        session,
        principal=principal,
        cookie_id=cookie_id,
        payload=body.model_dump(),
        ctx=ctx,
    )
    # Set/refresh the first-party cookie unless the holder has opted out.
    if not discovery_session.opt_out:
        _set_discovery_cookie(response, discovery_session)
    return success(result)


@router.post("/session/reset", summary="Clear coarse signals / opt out of personalization")
async def reset_discovery_session(
    body: DiscoverySessionResetRequest | None = None,
    *,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    principal, ctx = await _optional_auth(request, session)
    cookie_id = request.cookies.get(get_settings().discovery_session_cookie_name)
    opt_out = bool(body.opt_out) if body else False

    cleared = await session_service.reset(
        session, cookie_id=cookie_id, principal=principal, opt_out=opt_out, ctx=ctx
    )
    # On opt-out, drop the cookie entirely so no further session linkage occurs.
    if opt_out or cleared is None:
        _clear_discovery_cookie(response)
    return success({"reset": True, "opt_out": opt_out})
