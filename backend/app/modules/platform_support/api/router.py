"""Support-console HTTP routes (``/api/v1/platform-support/*``, ADR-0014).

HTTP-only: RBAC/audit live in the application services.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.platform_support.application import (
    lookup_service,
    outbox_health_service,
    package_override_service,
    reveal_service,
    support_case_service,
)
from app.shared.responses import success

router = APIRouter(prefix="/platform-support", tags=["platform-support"])


class PackageOverrideRequest(BaseModel):
    plan_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class RevealRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CaseResolveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.get("/lookup", summary="Account/org lookup")
async def lookup(
    q: str | None = Query(default=None),
    type: str = Query(default="user"),  # noqa: A002 - matches API contract param name
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await lookup_service.lookup(
        session, principal=auth.principal, q=q, type_=type, page=page, page_size=page_size
    )
    return success(data)


@router.get("/outbox-health", summary="Notification outbox health counts")
async def outbox_health(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await outbox_health_service.get_health(session, principal=auth.principal)
    return success(data)


@router.post("/outbox/{outbox_id}/requeue", summary="Requeue a dead-lettered outbox row")
async def requeue_outbox(
    outbox_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await outbox_health_service.requeue(
        session, principal=auth.principal, outbox_id=outbox_id, ctx=auth.ctx
    )
    return success(data)


@router.post("/users/{user_id}/package-override", summary="Override a student's package")
async def package_override(
    user_id: uuid.UUID,
    body: PackageOverrideRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await package_override_service.override_package(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
        plan_id=body.plan_id,
        reason=body.reason,
    )
    return success(data)


@router.post("/reveal/{resource_type}/{resource_id}", summary="Reveal masked PII")
async def reveal_pii(
    resource_type: str,
    resource_id: uuid.UUID,
    body: RevealRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await reveal_service.reveal(
        session,
        principal=auth.principal,
        resource_type=resource_type,
        resource_id=resource_id,
        reason=body.reason,
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/cases", summary="Support cases (human_review_queue, source=support_case)")
async def list_cases(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await support_case_service.list_cases(
        session, principal=auth.principal, status=status, limit=limit
    )
    return success(data)


@router.post("/cases/{item_id}/resolve", summary="Resolve a support case")
async def resolve_case(
    item_id: uuid.UUID,
    body: CaseResolveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await support_case_service.resolve_case(
        session, principal=auth.principal, item_id=item_id, note=body.note, ctx=auth.ctx
    )
    return success(data)
