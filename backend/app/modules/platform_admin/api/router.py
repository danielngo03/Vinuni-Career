"""Platform Admin HTTP routes — superadmin only.

Endpoints:
  GET  /admin/audit-log              — cursor-paginated platform-wide audit log
  GET  /admin/audit-log/export       — CSV download of filtered audit rows
  GET  /admin/system-health          — combined jobs + queues + services snapshot
  GET  /admin/system-health/jobs     — latest run per REGISTRY job
  GET  /admin/system-health/queues   — Redis reachability + Celery queue depth
  GET  /admin/system-health/services — DB, Redis, and notification outbox counts

  --- P4a: Users & Access ---
  GET  /admin/users                        — list platform users (offset-paged)
  GET  /admin/users/{user_id}              — user 360 detail view
  POST /admin/users/{user_id}/suspend      — suspend user (audited)
  POST /admin/users/{user_id}/unsuspend         — unsuspend user (audited)
  POST /admin/users/{user_id}/grant-superadmin  — grant superadmin (audited)
  POST /admin/users/{user_id}/revoke-superadmin — revoke superadmin (audited)
  GET  /admin/sessions                     — cursor-paginated active sessions
  POST /admin/sessions/{session_id}/revoke — admin-revoke session (audited)

  --- P5: Feature Flags & Permission Catalog ---
  GET   /admin/feature-flags               — list all feature flags (sorted by key)
  POST  /admin/feature-flags               — create feature flag (audited)
  PATCH /admin/feature-flags/{flag_id}     — partial update flag (audited)
  GET   /admin/permission-catalog          — read-only permission vocabulary

  --- P6: Analytics read models (superadmin-only, aggregate-only) ---
  GET  /admin/analytics/kpis               — top-line KPI totals
  GET  /admin/analytics/funnel             — application funnel + conversion rates
  GET  /admin/analytics/growth             — per-day growth trend series

  --- P7: Alerts & Incidents ---
  GET    /admin/alerts/rules               — list alert rules
  POST   /admin/alerts/rules               — create alert rule (audited)
  PATCH  /admin/alerts/rules/{id}          — update alert rule (audited)
  DELETE /admin/alerts/rules/{id}          — delete alert rule (audited)
  GET    /admin/alerts/incidents           — cursor-paginated incidents list
  POST   /admin/alerts/incidents/{id}/acknowledge — acknowledge incident (audited)
  POST   /admin/alerts/incidents/{id}/resolve     — resolve incident (audited)

Authorization is enforced both in the ``require_superadmin`` dependency *and*
re-checked inside the service layer (defence-in-depth per backend rules).

Response shape for the list endpoint matches the ``paginated()`` envelope used
by ``ai_ops/api/router.py`` so the frontend ``api.list`` helper works unchanged:

    {
      "data": [ { ...item... }, ... ],
      "page": { "next_cursor": "...|null", "limit": 50 }
    }

Health and user 360 endpoints use the plain ``success()`` envelope:

    { "data": { ... } }
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import Depends, Query, Response
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth, require_superadmin
from app.modules.platform_admin.application import (
    alerts_service,
    analytics_read_service,
    audit_read_service,
    feature_flags_service,
    permission_catalog_service,
    system_health_service,
    users_admin_service,
)
from app.shared.audit import AuditContext
from app.shared.permissions import Principal
from app.shared.responses import paginated, success

admin_router = APIRouter(prefix="/admin/audit-log", tags=["platform-admin-audit"])
health_router = APIRouter(prefix="/admin/system-health", tags=["platform-admin-health"])
users_router = APIRouter(prefix="/admin/users", tags=["platform-admin-users"])
sessions_router = APIRouter(prefix="/admin/sessions", tags=["platform-admin-sessions"])
alerts_rules_router = APIRouter(prefix="/admin/alerts/rules", tags=["platform-admin-alerts"])
alerts_incidents_router = APIRouter(
    prefix="/admin/alerts/incidents", tags=["platform-admin-alerts"]
)
analytics_router = APIRouter(prefix="/admin/analytics", tags=["platform-admin-analytics"])
flags_router = APIRouter(prefix="/admin/feature-flags", tags=["platform-admin-flags"])
catalog_router = APIRouter(prefix="/admin/permission-catalog", tags=["platform-admin-catalog"])


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


# ---------------------------------------------------------------------------
# System health endpoints (P3)
# ---------------------------------------------------------------------------


@health_router.get("", summary="System health: combined snapshot (jobs + queues + services)")
async def get_system_health(
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    jobs = await system_health_service.jobs_health(db, principal=principal)
    queues = await system_health_service.queues_health(principal=principal)
    services = await system_health_service.services_health(db, principal=principal)
    return success({"jobs": jobs, "queues": queues, "services": services})


@health_router.get("/jobs", summary="System health: latest run per scheduled job")
async def get_jobs_health(
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    jobs = await system_health_service.jobs_health(db, principal=principal)
    return success({"jobs": jobs})


@health_router.get("/queues", summary="System health: broker and queue depth")
async def get_queues_health(
    principal: Principal = Depends(require_superadmin),
) -> dict:
    queues = await system_health_service.queues_health(principal=principal)
    return success(queues)


@health_router.get("/services", summary="System health: database, Redis, and outbox")
async def get_services_health(
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    services = await system_health_service.services_health(db, principal=principal)
    return success(services)


# ---------------------------------------------------------------------------
# P4a: Users & Access — superadmin only
# ---------------------------------------------------------------------------


@users_router.get("", summary="List platform users — superadmin view (offset-paged)")
async def list_platform_users(
    persona: str | None = Query(
        None, description="Filter by persona (student|partner_member|university_staff)"
    ),
    q: str | None = Query(None, description="Search by email or name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await users_admin_service.list_users(
        db,
        principal=principal,
        persona=persona,
        q=q,
        page=page,
        page_size=page_size,
    )
    return success(data)


@users_router.get("/{user_id}", summary="User 360 detail — superadmin")
async def get_user_360(
    user_id: uuid.UUID,
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await users_admin_service.user_360(db, principal=principal, user_id=user_id)
    return success(data)


@users_router.post("/{user_id}/suspend", summary="Suspend a user — superadmin")
async def suspend_user(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not auth.principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    data = await users_admin_service.suspend_user(
        db,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
    )
    return success(data)


@users_router.post("/{user_id}/unsuspend", summary="Unsuspend a user — superadmin")
async def unsuspend_user(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not auth.principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    data = await users_admin_service.unsuspend_user(
        db,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
    )
    return success(data)


@users_router.post(
    "/{user_id}/grant-superadmin",
    summary="Grant superadmin to a user — superadmin only",
)
async def grant_superadmin(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not auth.principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    data = await users_admin_service.grant_superadmin(
        db,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
    )
    return success(data)


@users_router.post(
    "/{user_id}/revoke-superadmin",
    summary="Revoke superadmin from a user — superadmin only",
)
async def revoke_superadmin(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not auth.principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    data = await users_admin_service.revoke_superadmin(
        db,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
    )
    return success(data)


@sessions_router.get("", summary="List active sessions platform-wide — superadmin")
async def list_platform_sessions(
    user_id: uuid.UUID | None = Query(default=None, description="Filter to one user"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, next_cursor, page_limit = await users_admin_service.list_platform_sessions(
        db,
        principal=principal,
        user_id=user_id,
        cursor=cursor,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@sessions_router.post("/{session_id}/revoke", summary="Admin-revoke a session — superadmin")
async def revoke_platform_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if not auth.principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    data = await users_admin_service.revoke_platform_session(
        db,
        principal=auth.principal,
        ctx=auth.ctx,
        session_id=session_id,
    )
    return success(data)


# ---------------------------------------------------------------------------
# P6: Analytics read models — superadmin-only, aggregate-only, no PII
# ---------------------------------------------------------------------------


@analytics_router.get("/kpis", summary="Platform KPI totals — superadmin")
async def get_analytics_kpis(
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await analytics_read_service.kpis(db)
    return success(data)


@analytics_router.get("/funnel", summary="Application funnel + conversion rates — superadmin")
async def get_analytics_funnel(
    range_days: int = Query(default=30, ge=1, le=365),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await analytics_read_service.funnel(db, range_days=range_days)
    return success(data)


@analytics_router.get("/growth", summary="Per-day growth trend series — superadmin")
async def get_analytics_growth(
    range_days: int = Query(default=30, ge=1, le=365),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await analytics_read_service.growth(db, range_days=range_days)
    return success(data)


# ---------------------------------------------------------------------------
# P5: Feature Flags — superadmin only
# ---------------------------------------------------------------------------


@flags_router.get("", summary="List all feature flags — superadmin")
async def list_feature_flags(
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await feature_flags_service.list_flags(db)
    return success(items)


@flags_router.post("", summary="Create a feature flag — superadmin (audited)")
async def create_feature_flag(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await feature_flags_service.create_flag(
        db,
        principal=auth.principal,
        ctx=ctx,
        key=body.get("key", ""),
        description=body.get("description", ""),
        enabled=body.get("enabled", False),
        rollout_percentage=body.get("rollout_percentage", 0),
    )
    return success(result)


@flags_router.patch("/{flag_id}", summary="Update a feature flag — superadmin (audited)")
async def update_feature_flag(
    flag_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await feature_flags_service.update_flag(
        db,
        principal=auth.principal,
        ctx=ctx,
        flag_id=flag_id,
        **body,
    )
    return success(result)


# ---------------------------------------------------------------------------
# P5: Permission Catalog — superadmin read-only
# ---------------------------------------------------------------------------


@catalog_router.get("", summary="Permission catalog vocabulary — superadmin")
async def get_permission_catalog(
    _principal: Principal = Depends(require_superadmin),
) -> dict:
    catalog = permission_catalog_service.permission_catalog()
    return success({"catalog": catalog})


# ---------------------------------------------------------------------------
# P7: Alert Rules — superadmin only
# ---------------------------------------------------------------------------


@alerts_rules_router.get("", summary="List alert rules — superadmin")
async def list_alert_rules(
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await alerts_service.list_rules(db, principal=principal)
    return success(items)


@alerts_rules_router.post("", summary="Create alert rule — superadmin (audited)")
async def create_alert_rule(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await alerts_service.create_rule(
        db,
        principal=auth.principal,
        ctx=ctx,
        name=body.get("name", ""),
        metric=body.get("metric", ""),
        comparison=body.get("comparison", ""),
        threshold=float(body.get("threshold", 0)),
        window_days=int(body.get("window_days", 1)),
        severity=body.get("severity", "warning"),
        enabled=bool(body.get("enabled", True)),
        channels=list(body.get("channels", [])),
    )
    return success(result)


@alerts_rules_router.patch("/{rule_id}", summary="Update alert rule — superadmin (audited)")
async def update_alert_rule(
    rule_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await alerts_service.update_rule(
        db,
        principal=auth.principal,
        ctx=ctx,
        rule_id=rule_id,
        **body,
    )
    return success(result)


@alerts_rules_router.delete("/{rule_id}", summary="Delete alert rule — superadmin (audited)")
async def delete_alert_rule(
    rule_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await alerts_service.delete_rule(
        db,
        principal=auth.principal,
        ctx=ctx,
        rule_id=rule_id,
    )
    return success(result)


# ---------------------------------------------------------------------------
# P7: Incidents — superadmin only
# ---------------------------------------------------------------------------


@alerts_incidents_router.get("", summary="List incidents — superadmin (cursor-paginated)")
async def list_incidents(
    status: str | None = Query(
        default=None, description="Filter by status: open|acknowledged|resolved"
    ),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    items, next_cursor, page_limit = await alerts_service.list_incidents(
        db,
        status=status,
        cursor=cursor,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@alerts_incidents_router.post(
    "/{incident_id}/acknowledge",
    summary="Acknowledge an incident — superadmin (audited)",
)
async def acknowledge_incident(
    incident_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await alerts_service.acknowledge_incident(
        db,
        principal=auth.principal,
        ctx=ctx,
        incident_id=incident_id,
    )
    return success(result)


@alerts_incidents_router.post(
    "/{incident_id}/resolve",
    summary="Manually resolve an incident — superadmin (audited)",
)
async def resolve_incident(
    incident_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    ctx = AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )
    result = await alerts_service.resolve_incident(
        db,
        principal=auth.principal,
        ctx=ctx,
        incident_id=incident_id,
    )
    return success(result)
