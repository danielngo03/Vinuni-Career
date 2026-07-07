"""AI ops admin HTTP routes — superadmin only.

Every endpoint requires ``require_superadmin``; authorization happens in the
dependency layer (``deps.py``), not just the router.

Identity masking: ``provider``/``model`` values in the events list are masked
(set to ``None``) unless the caller additionally holds the explicit
``ai_settings:view_provider_identity`` grant.  This is an additive permission
checked on the raw ``permissions`` frozenset — it is intentionally NOT
short-circuited by ``is_superadmin`` because exposing raw provider/model names
is a deliberate least-privilege gate on telemetry internals.
"""

from __future__ import annotations

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.ai_ops.api.deps import require_superadmin
from app.modules.ai_ops.application import ai_ops_read_service
from app.shared.permissions import Principal
from app.shared.responses import paginated, success

admin_router = APIRouter(prefix="/admin/ai-ops", tags=["ai-ops-admin"])

_IDENTITY_GRANT = "ai_settings:view_provider_identity"


def _can_reveal_identity(principal: Principal) -> bool:
    """Return True only when the caller explicitly holds the identity-reveal grant.

    Intentionally checks the raw ``permissions`` frozenset rather than calling
    ``permission_checker.can()`` so that ``is_superadmin=True`` does NOT bypass
    this gate.  Revealing concrete provider/model names is a separate additive
    privilege even for platform superadmins.
    """
    return any(
        g in (_IDENTITY_GRANT, "ai_settings:*", "*:view_provider_identity", "*")
        for g in principal.permissions
    )


@admin_router.get("/overview", summary="AI platform health overview")
async def get_overview(
    range_days: int = Query(default=7, ge=1, le=365),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ai_ops_read_service.overview(db, range_days=range_days)
    return success(data)


@admin_router.get("/spend", summary="AI spend breakdown")
async def get_spend(
    range_days: int = Query(default=7, ge=1, le=365),
    group_by: str = Query(default="day"),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ai_ops_read_service.spend(db, range_days=range_days, group_by=group_by)
    return success(data)


@admin_router.get("/reliability", summary="AI reliability metrics and circuit-breaker states")
async def get_reliability(
    range_days: int = Query(default=7, ge=1, le=365),
    group_by: str = Query(default="day"),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ai_ops_read_service.reliability(db, range_days=range_days, group_by=group_by)
    return success(data)


@admin_router.get("/volume", summary="AI request and token volume")
async def get_volume(
    range_days: int = Query(default=7, ge=1, le=365),
    group_by: str = Query(default="day"),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ai_ops_read_service.volume(db, range_days=range_days, group_by=group_by)
    return success(data)


@admin_router.get("/events", summary="AI ops event log (cursor-paginated)")
async def get_events(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    task_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    reveal_identity = _can_reveal_identity(principal)
    filters: dict[str, str] = {}
    if task_type:
        filters["task_type"] = task_type
    if status:
        filters["status"] = status

    data = await ai_ops_read_service.events(
        db,
        cursor=cursor,
        filters=filters,
        reveal_identity=reveal_identity,
        limit=limit,
    )
    return paginated(
        data["items"],
        next_cursor=data["next_cursor"],
        limit=limit,
    )
