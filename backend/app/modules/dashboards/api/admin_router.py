"""Superadmin-only admin HTTP routes (``/admin/*``).

Exposes the platform overview landing payload.  Authorization is enforced by
the ``require_superadmin`` dependency — a non-superadmin caller receives 403
before any service code is reached.

Path: ``GET /admin/overview`` (prefix ``/admin``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.ai_ops.api.deps import require_superadmin
from app.modules.dashboards.application import platform_overview
from app.shared.permissions import Principal
from app.shared.responses import success

admin_router = APIRouter(prefix="/admin", tags=["admin-overview"])


@admin_router.get("/overview", summary="Superadmin platform overview")
async def get_platform_overview(
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return the superadmin landing payload.

    Composes AI health, outbox health, moderation pending count, and active
    user count.  Each sub-section degrades gracefully on failure.
    """
    data = await platform_overview.platform_overview(db)
    return success(data)
