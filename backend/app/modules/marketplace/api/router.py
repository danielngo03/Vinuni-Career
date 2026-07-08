"""Public marketplace overview route under ``/api/v1/marketplace``.

HTTP-only: resolve optional auth + the first-party ``vinuni_discovery`` cookie so
the ``recommended_jobs`` rail can personalize honestly, then delegate to the
read-only :mod:`overview_service` aggregator. Auth is optional — a guest still
gets the full homepage (session-based or recent/popular recommendations).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import get_current_auth
from app.modules.discovery.application import session_service
from app.modules.marketplace.application import overview_service
from app.shared.permissions import GUEST, Principal
from app.shared.responses import success

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


async def _optional_principal(request: Request, session: AsyncSession) -> Principal:
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            return auth.principal
        except Exception:  # noqa: BLE001 — optional auth: a bad token degrades to guest
            pass
    return GUEST


@router.get("/overview", summary="Public career-marketplace homepage aggregate")
async def marketplace_overview(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    principal = await _optional_principal(request, session)
    cookie_id = request.cookies.get(get_settings().discovery_session_cookie_name)
    session_tags = await session_service.get_coarse_tags(session, cookie_id=cookie_id)
    data = await overview_service.get_overview(
        session,
        principal=principal,
        session_tags=session_tags,
        discovery_session_id=session_service.resolve_session_id(cookie_id),
    )
    return success(data)
