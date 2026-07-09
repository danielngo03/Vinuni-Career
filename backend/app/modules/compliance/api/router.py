"""Privacy & compliance HTTP routes (ADR-0014, ``docs/API_CONTRACTS.md``).

``router`` mounts the student-facing self-service surface at
``/account/privacy``; ``admin_router`` mounts the ``privacy:process``-gated
staff surface at ``/admin/privacy-requests``. HTTP-only — RBAC/audit live in
the application services.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.compliance.application import (
    consent_service,
    privacy_request_service,
    retention_service,
)
from app.shared.responses import success

router = APIRouter(prefix="/account/privacy", tags=["compliance"])
admin_router = APIRouter(prefix="/admin/privacy-requests", tags=["compliance-admin"])


class ConsentPutRequest(BaseModel):
    granted: bool


class PrivacyRequestCreate(BaseModel):
    request_type: str
    note: str | None = Field(default=None, max_length=2000)


class PrivacyRequestFulfill(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=2000)


@router.get("/consents", summary="Read my consent state")
async def get_my_consents(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await consent_service.get_mine(session, principal=auth.principal)
    return success(data)


@router.put("/consents/{consent_type}", summary="Grant or revoke a consent")
async def put_my_consent(
    consent_type: str,
    body: ConsentPutRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await consent_service.set_mine(
        session,
        principal=auth.principal,
        consent_type=consent_type,
        granted=body.granted,
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/retention", summary="Read-only retention policy text")
async def get_retention(
    locale: str = Query(default="vi"),
) -> dict:
    return success(retention_service.get_policy_text(locale=locale))


@router.post("/requests", summary="Submit a privacy export/deletion request")
async def submit_privacy_request(
    body: PrivacyRequestCreate,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await privacy_request_service.submit(
        session,
        principal=auth.principal,
        request_type=body.request_type,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/requests", summary="List my own privacy requests")
async def list_my_privacy_requests(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await privacy_request_service.list_mine(session, principal=auth.principal)
    return success(data)


@admin_router.get("", summary="Staff list of privacy requests")
async def list_privacy_requests_admin(
    status: str | None = Query(default=None),
    request_type: str | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await privacy_request_service.list_staff(
        session,
        principal=auth.principal,
        status=status,
        request_type=request_type,
        assigned_to=assigned_to,
    )
    return success(data)


@admin_router.post("/{request_id}/start", summary="Claim + start processing a request")
async def start_privacy_request(
    request_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await privacy_request_service.start_processing(
        session,
        principal=auth.principal,
        request_id=request_id,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/{request_id}/fulfill", summary="Fulfill/reject a privacy request")
async def fulfill_privacy_request(
    request_id: uuid.UUID,
    body: PrivacyRequestFulfill,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await privacy_request_service.fulfill(
        session,
        principal=auth.principal,
        request_id=request_id,
        status=body.status,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(data)
