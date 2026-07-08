"""Public recommendation + similar-jobs delivery routes + the admin health read.

HTTP-only: resolve optional auth + the first-party ``vinuni_discovery`` cookie,
then delegate to :mod:`ranking_service` / :mod:`health_service` (which own the
eligibility predicate, scoring, source separation, and RBAC). These paths live in
the ``discovery`` module — not ``opportunities`` — so the dependency stays one-way
(``discovery → opportunities``) and there is no import cycle. They are registered
**before** the opportunities jobs router so ``/jobs/recommendations`` is matched
as a static path (never captured by ``/jobs/{job_id}``).

No provider/model/token/raw-confidence is ever exposed; the ``score`` is a product
score. A guest never sees another student's data.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import get_current_auth
from app.modules.discovery.application import (
    health_service,
    ranking_service,
    session_service,
)
from app.shared.permissions import GUEST, Principal
from app.shared.responses import success

# Static-path recommendation/similar routes that share the ``/jobs`` prefix with
# the opportunities router (registered first in bootstrap to win path matching).
jobs_reco_router = APIRouter(prefix="/jobs", tags=["discovery"])
# Admin governance surface.
admin_discovery_router = APIRouter(prefix="/admin/discovery", tags=["discovery"])


async def _optional_principal(request: Request, session: AsyncSession) -> Principal:
    """Resolve the principal from a bearer token if present; else GUEST.

    Recommendations are public/optional-auth: a missing/invalid token degrades to
    a guest rather than raising (no cross-student leak — a guest gets only
    session/popular signals).
    """

    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            return auth.principal
        except Exception:  # noqa: BLE001 — optional auth never blocks on a bad token
            pass
    return GUEST


async def _cookie_tags(request: Request, session: AsyncSession) -> dict:
    cookie_id = request.cookies.get(get_settings().discovery_session_cookie_name)
    return await session_service.get_coarse_tags(session, cookie_id=cookie_id)


@jobs_reco_router.get(
    "/recommendations", summary="Personalized job recommendations (optional-auth)"
)
async def job_recommendations(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=12, ge=1, le=30),
) -> dict:
    principal = await _optional_principal(request, session)
    tags = await _cookie_tags(request, session)
    cookie_id = request.cookies.get(get_settings().discovery_session_cookie_name)
    data = await ranking_service.recommend_jobs(
        session,
        principal=principal,
        cookie_tags=tags,
        q=q,
        limit=limit,
        discovery_session_id=session_service.resolve_session_id(cookie_id),
        snapshot_surface="jobs_recommendations",
    )
    return success(data)


@jobs_reco_router.get(
    "/{job_id}/similar", summary="Similar public jobs (deterministic, eligible-only)"
)
async def similar_jobs(
    job_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=6, ge=1, le=20),
) -> dict:
    principal = await _optional_principal(request, session)
    data = await ranking_service.similar_jobs(
        session, principal=principal, job_id=job_id, limit=limit
    )
    return success(data)


@admin_discovery_router.get(
    "/health", summary="Discovery + advertising inventory health (university/admin)"
)
async def discovery_health(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    auth = await get_current_auth(request, session)
    data = await health_service.get_discovery_health(session, principal=auth.principal)
    return success(data)
