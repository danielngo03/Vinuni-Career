"""Company-profile + university-approval HTTP routes.

Routers are HTTP-only: validate, delegate to
``company_profile_service`` (RBAC + audit + tenant isolation + file safety), and
shape the response envelope. Public API paths live under
``/api/v1/organizations`` and ``/api/v1/admin/company-approvals``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.organization.api.schemas import (
    CompanyApproveRequest,
    CompanyProfileUpdateRequest,
    CompanyRejectRequest,
)
from app.modules.organization.application import company_profile_service
from app.shared.exceptions import ValidationFailedError
from app.shared.responses import success

# Partner-facing company profile routes (under /organizations).
partner_router = APIRouter(prefix="/organizations", tags=["organization"])

# University-facing approval queue (under /admin/company-approvals).
admin_router = APIRouter(prefix="/admin/company-approvals", tags=["organization"])


# --------------------------------------------------------------------------- #
# Signed company-document serve (bearer token capability). Declared before the #
# ``/{org_id}/...`` routes so the literal segment wins the match.             #
# --------------------------------------------------------------------------- #


@partner_router.get(
    "/company-documents/{token}",
    summary="Serve a signed company document (legal/verification file)",
)
async def serve_company_document(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    doc = await company_profile_service.serve_company_document(session, token=token)
    return Response(
        content=doc.content,
        media_type=doc.media_type,
        headers={
            # Force download (never inline execution) — defence-in-depth even
            # though uploads are content-type allowlisted at ingestion.
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# --------------------------------------------------------------------------- #
# Partner: profile read / update                                              #
# --------------------------------------------------------------------------- #


@partner_router.get("/{org_id}/profile", summary="Get the full company profile")
async def get_company_profile(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.get_company_profile(
        session, principal=auth.principal, org_id=org_id
    )
    return success(data)


@partner_router.put(
    "/{org_id}/profile",
    summary="Update the company profile (cosmetic immediate; sensitive -> approval)",
)
async def update_company_profile(
    org_id: uuid.UUID,
    body: CompanyProfileUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.update_company_profile(
        session,
        principal=auth.principal,
        org_id=org_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Partner: company documents + change requests                                #
# --------------------------------------------------------------------------- #


@partner_router.post(
    "/{org_id}/documents",
    status_code=status.HTTP_201_CREATED,
    summary="Attach a company document (awaits university approval)",
)
async def upload_company_document(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: str | None = Form(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn.", details={"reason": "file_too_large"}
        )
    result = await company_profile_service.attach_company_document(
        session,
        principal=auth.principal,
        org_id=org_id,
        filename=file.filename,
        data=data,
        content_type=file.content_type,
        kind=kind,
        ctx=auth.ctx,
    )
    return success(result)


@partner_router.get(
    "/{org_id}/change-requests",
    summary="List this org's company-profile change requests",
)
async def list_change_requests(
    org_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    req_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items = await company_profile_service.list_change_requests(
        session, principal=auth.principal, org_id=org_id, status=req_status
    )
    return success(items, meta={"count": len(items)})


@partner_router.post(
    "/{org_id}/change-requests/{req_id}/withdraw",
    summary="Withdraw a pending change request",
)
async def withdraw_change_request(
    org_id: uuid.UUID,
    req_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.withdraw_change_request(
        session, principal=auth.principal, org_id=org_id, req_id=req_id, ctx=auth.ctx
    )
    return success(data)


# --------------------------------------------------------------------------- #
# University: approval queue + decisions                                      #
# --------------------------------------------------------------------------- #


@admin_router.get("", summary="List company-profile change requests (university)")
async def list_approval_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    req_status: str | None = Query(default="pending", alias="status"),
) -> dict:
    items = await company_profile_service.list_approval_queue(
        session, principal=auth.principal, status=req_status
    )
    return success(items, meta={"count": len(items)})


@admin_router.get("/{req_id}", summary="Get a change request detail (university)")
async def get_approval(
    req_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.get_approval(
        session, principal=auth.principal, req_id=req_id
    )
    return success(data)


@admin_router.post("/{req_id}/approve", summary="Approve a change request (university)")
async def approve_change_request(
    req_id: uuid.UUID,
    body: CompanyApproveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.approve_change_request(
        session,
        principal=auth.principal,
        req_id=req_id,
        note=body.note,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/{req_id}/reject", summary="Reject a change request (university)")
async def reject_change_request(
    req_id: uuid.UUID,
    body: CompanyRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await company_profile_service.reject_change_request(
        session,
        principal=auth.principal,
        req_id=req_id,
        reason=body.reason,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)
