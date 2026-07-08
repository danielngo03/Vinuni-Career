"""AI governance HTTP routes — university capacity + superadmin distribution.

University staff (authenticated university member):
  POST /university/ai/capacity-requests        — submit a capacity request
  GET  /university/ai/capacity-requests/me      — my own requests

Superadmin only:
  GET  /admin/ai/capacity-requests?status=       — the capacity-request queue
  POST /admin/ai/capacity-requests/{id}/decide   — approve/deny (audited)
  GET  /admin/ai/allocations?org_id=             — org distribution read-model
  PUT  /admin/ai/allocations                     — upsert a scope ceiling (audited)

Routers validate HTTP + delegate to the application services, which enforce RBAC
(defence-in-depth) and write audit records. No provider/model/token/USD leaks.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Query
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.ai_governance.application import allocation_service, capacity_service
from app.modules.auth.api.deps import (
    CurrentAuth,
    get_current_auth,
    require_superadmin,
)
from app.shared.audit import AuditContext
from app.shared.permissions import Principal
from app.shared.responses import success

university_capacity_router = APIRouter(
    prefix="/university/ai/capacity-requests", tags=["ai-governance-university"]
)
admin_capacity_router = APIRouter(
    prefix="/admin/ai/capacity-requests", tags=["ai-governance-admin"]
)
admin_allocation_router = APIRouter(
    prefix="/admin/ai/allocations", tags=["ai-governance-admin"]
)


def _audit_ctx(auth: CurrentAuth) -> AuditContext:
    return AuditContext(
        actor_id=auth.principal.user_id,
        actor_org_id=auth.principal.org_id,
        session_id=auth.claims.session_id,
        ip=auth.ctx.ip,
        user_agent=auth.ctx.user_agent,
    )


# --------------------------------------------------------------------------- #
# University staff                                                              #
# --------------------------------------------------------------------------- #


@university_capacity_router.post("", summary="Submit an AI capacity request")
async def submit_capacity_request(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await capacity_service.submit_request(
        db,
        principal=auth.principal,
        ctx=_audit_ctx(auth),
        reason=str(body.get("reason", "")),
        requested_units=body.get("requested_units"),
    )
    return success(data)


@university_capacity_router.get("/me", summary="My AI capacity requests")
async def my_capacity_requests(
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await capacity_service.list_my_requests(db, principal=auth.principal)
    return success(data)


# --------------------------------------------------------------------------- #
# Superadmin — capacity queue + decision                                       #
# --------------------------------------------------------------------------- #


@admin_capacity_router.get("", summary="AI capacity-request queue — superadmin")
async def list_capacity_requests(
    status: str | None = Query(default="pending"),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await capacity_service.list_requests(db, principal=principal, status=status)
    return success(data)


@admin_capacity_router.post(
    "/{request_id}/decide", summary="Approve/deny a capacity request — superadmin"
)
async def decide_capacity_request(
    request_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()
    data = await capacity_service.decide_request(
        db,
        principal=auth.principal,
        ctx=_audit_ctx(auth),
        request_id=request_id,
        decision=str(body.get("decision", "")),
        granted_units=body.get("granted_units"),
        note=body.get("note"),
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Superadmin — energy distribution                                             #
# --------------------------------------------------------------------------- #


@admin_allocation_router.get("", summary="Org energy distribution read-model — superadmin")
async def list_allocations(
    org_id: uuid.UUID = Query(...),
    principal: Principal = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await allocation_service.list_allocations(
        db, principal=principal, org_id=org_id
    )
    return success(data)


@admin_allocation_router.put("", summary="Upsert a scope energy ceiling — superadmin")
async def upsert_allocation(
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.shared.exceptions import PermissionDeniedError, ValidationFailedError

    if not auth.principal.is_superadmin:
        raise PermissionDeniedError()

    scope_type = str(body.get("scope_type", ""))
    try:
        scope_id = uuid.UUID(str(body.get("scope_id")))
        org_id = uuid.UUID(str(body.get("org_id")))
    except (ValueError, TypeError, AttributeError):
        raise ValidationFailedError("scope_id và org_id phải là UUID hợp lệ.") from None

    raw_units = body.get("weekly_allowance_units")
    units = None if raw_units is None else int(raw_units)

    data = await allocation_service.upsert_allocation(
        db,
        principal=auth.principal,
        ctx=_audit_ctx(auth),
        scope_type=scope_type,
        scope_id=scope_id,
        org_id=org_id,
        weekly_allowance_units=units,
    )
    return success(data)
