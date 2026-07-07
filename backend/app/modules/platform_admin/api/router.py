"""Platform Admin HTTP routes — superadmin only.

Endpoints:
  GET  /admin/audit-log            — cursor-paginated platform-wide audit log
  GET  /admin/audit-log/export     — CSV download of filtered audit rows

Authorization is enforced both in the ``require_superadmin`` dependency *and*
re-checked inside the service layer (defence-in-depth per backend rules).

Response shape for the list endpoint matches the ``paginated()`` envelope used
by ``ai_ops/api/router.py`` so the frontend ``api.list`` helper works unchanged:

    {
      "data": [ { ...item... }, ... ],
      "page": { "next_cursor": "...|null", "limit": 50 }
    }
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import require_superadmin
from app.modules.platform_admin.application import audit_read_service
from app.shared.permissions import Principal
from app.shared.responses import paginated

admin_router = APIRouter(prefix="/admin/audit-log", tags=["platform-admin-audit"])


@admin_router.get("", summary="Platform-wide audit log (cursor-paginated)")
async def list_audit_log(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, next_cursor, page_limit = await audit_read_service.list_platform_audit(
        db,
        principal=principal,
        cursor=cursor,
        limit=limit,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        since=since,
        until=until,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@admin_router.get("/export", summary="Platform-wide audit log CSV export")
async def export_audit_log(
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    csv_body = await audit_read_service.export_platform_audit_csv(
        db,
        principal=principal,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        since=since,
        until=until,
    )
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="platform_audit_log.csv"'},
    )
