"""Advertising HTTP routes (ADR-0009 §7).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit
+ tenant isolation + transactions), and shape the response envelope. Two routers
are exported and mounted by the app: ``router`` (the partner advertiser surface
under ``/advertising``) and ``admin_router`` (the university oversight surface
under ``/admin/advertising``). The public marketplace contract is unchanged — the
public never sees campaign internals, only the resulting non-removable label.
"""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.advertising.api.schemas import (
    CreativeReviewRequest,
    DisclosureClassRequest,
    PlacementAdminCancelRequest,
    PlacementApproveRequest,
    PlacementBulkApproveRequest,
    PlacementBulkRejectRequest,
    PlacementCreateRequest,
    PlacementEscalateRequest,
    PlacementMarkPaidRequest,
    PlacementRejectRequest,
    PlacementSubmitRequest,
    PlacementUpdateRequest,
    PlacementVersionRequest,
)
from app.modules.advertising.application import (
    creative_service,
    moderation_service,
    placement_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import GUEST, Principal
from app.shared.responses import paginated, success

router = APIRouter(prefix="/advertising", tags=["advertising"])
admin_router = APIRouter(prefix="/admin/advertising", tags=["advertising-admin"])


# --------------------------------------------------------------------------- #
# Pricing catalog (auth optional — public pricing display)                    #
# --------------------------------------------------------------------------- #


@router.get("/packages", summary="Advertising pricing tiers")
async def list_packages(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Packages are non-sensitive pricing data; available to any authenticated
    # partner (and guests browsing pricing). No campaign internals here.
    _principal: Principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            _principal = auth.principal
        except Exception:  # noqa: BLE001
            _principal = GUEST
    data = await placement_service.list_packages(session)
    return success(data)


# --------------------------------------------------------------------------- #
# Partner advertiser surface                                                  #
# --------------------------------------------------------------------------- #


@router.get("/placements", summary="My org's placements (any status)")
async def list_placements(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    placement_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items, next_cursor, page_limit = await placement_service.list_my_placements(
        session,
        principal=auth.principal,
        status=placement_status,
        cursor=cursor,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@router.post(
    "/placements",
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft placement request",
)
async def create_placement(
    body: PlacementCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await placement_service.create_placement(
        session,
        principal=auth.principal,
        payload=body.model_dump(),
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/placements/{placement_id}", summary="Placement detail (owner / 404)")
async def get_placement(
    placement_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await placement_service.get_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
    )
    return success(data)


@router.patch("/placements/{placement_id}", summary="Edit a draft/rejected placement")
async def update_placement(
    placement_id: uuid.UUID,
    body: PlacementUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await placement_service.update_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@router.post("/placements/{placement_id}/submit", summary="Submit for approval")
async def submit_placement(
    placement_id: uuid.UUID,
    body: PlacementSubmitRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    disclosure = body.disclosure_confirmed if body else None
    data = await placement_service.submit_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        ctx=auth.ctx,
        version=version,
        disclosure_confirmed=disclosure,
    )
    return success(data)


@router.post("/placements/{placement_id}/cancel", summary="Cancel my placement")
async def cancel_placement(
    placement_id: uuid.UUID,
    body: PlacementVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await placement_service.cancel_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        ctx=auth.ctx,
        version=version,
    )
    return success(data)


@router.delete("/placements/{placement_id}", summary="Soft-delete a draft/rejected")
async def delete_placement(
    placement_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await placement_service.delete_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        ctx=auth.ctx,
    )
    return success({"status": "deleted"})


# --------------------------------------------------------------------------- #
# Campaign creatives (banner images) — partner upload / list / delete          #
# --------------------------------------------------------------------------- #


@router.get(
    "/placements/{placement_id}/creatives",
    summary="List a placement's creatives (owner / 404)",
)
async def list_creatives(
    placement_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await creative_service.list_creatives(
        session,
        principal=auth.principal,
        placement_id=placement_id,
    )
    return success(items, meta={"count": len(items)})


@router.post(
    "/placements/{placement_id}/creatives",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a banner creative for a slot",
)
async def upload_creative(
    placement_id: uuid.UUID,
    file: UploadFile = File(...),
    slot: str = Form(...),
    alt_vi: str | None = Form(default=None),
    alt_en: str | None = Form(default=None),
    focal_x: float = Form(default=0.5),
    focal_y: float = Form(default=0.5),
    click_target: str | None = Form(default=None),
    analytics_source_surface: str | None = Form(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await file.read()
    # Fail fast before further buffering; the service validator re-checks.
    if len(data) > get_settings().campaign_creative_max_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy chọn ảnh banner nhỏ hơn.",
            details={"reason": "file_too_large"},
        )
    result = await creative_service.upload_creative(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        slot=slot,
        data=data,
        content_type=file.content_type,
        alt_vi=alt_vi,
        alt_en=alt_en,
        focal_x=focal_x,
        focal_y=focal_y,
        click_target=click_target,
        analytics_source_surface=analytics_source_surface,
        ctx=auth.ctx,
    )
    return success(result)


@router.delete("/creatives/{creative_id}", summary="Soft-delete a creative")
async def delete_creative(
    creative_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await creative_service.delete_creative(
        session,
        principal=auth.principal,
        creative_id=creative_id,
        ctx=auth.ctx,
    )
    return success({"status": "deleted"})


@router.get(
    "/creatives/{creative_id}/image",
    summary="Public creative bytes (approved + active placement only)",
    response_class=Response,
)
async def serve_creative(
    creative_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    media = await creative_service.serve_creative(session, creative_id=creative_id)
    return Response(
        content=media.content,
        media_type=media.media_type,
        headers={
            # Public marketing asset; the ``?v=`` cache key on the URL lets a
            # replaced creative bust the cache safely.
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


# --------------------------------------------------------------------------- #
# University / admin oversight                                                #
# --------------------------------------------------------------------------- #


@admin_router.get("/placements", summary="All placements + spend roll-up")
async def list_all_placements(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    placement_status: str | None = Query(default=None, alias="status"),
    org_id: uuid.UUID | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, total, spend = await moderation_service.list_all(
        session,
        principal=auth.principal,
        status=placement_status,
        org_id=org_id,
        limit=limit,
    )
    return success(items, meta={"count": total, "spend": spend})


@admin_router.post("/placements/{placement_id}/approve", summary="Approve a placement")
async def approve_placement(
    placement_id: uuid.UUID,
    body: PlacementApproveRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    note = body.note if body else None
    version = body.version if body else None
    data = await moderation_service.approve_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        note=note,
        version=version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/placements/{placement_id}/reject", summary="Reject a placement")
async def reject_placement(
    placement_id: uuid.UUID,
    body: PlacementRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.reject_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        reason=body.reason,
        reason_code=body.reason_code,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/placements/{placement_id}/claim", summary="Claim a placement for review")
async def claim_placement(
    placement_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.claim_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post(
    "/placements/{placement_id}/escalate",
    summary="Escalate a placement to the human review queue",
)
async def escalate_placement(
    placement_id: uuid.UUID,
    body: PlacementEscalateRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason_code = body.reason_code if body else None
    note = body.note if body else None
    data = await moderation_service.escalate_placement(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        reason_code=reason_code,
        note=note,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/placements/bulk-approve", summary="Approve multiple placements")
async def bulk_approve_placements(
    body: PlacementBulkApproveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    results = await moderation_service.bulk_approve_placements(
        session,
        principal=auth.principal,
        placement_ids=body.placement_ids,
        ctx=auth.ctx,
    )
    return success(results)


@admin_router.post("/placements/bulk-reject", summary="Reject multiple placements")
async def bulk_reject_placements(
    body: PlacementBulkRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = [item.model_dump() for item in body.items]
    results = await moderation_service.bulk_reject_placements(
        session,
        principal=auth.principal,
        items=items,
        ctx=auth.ctx,
    )
    return success(results)


@admin_router.post(
    "/placements/{placement_id}/mark-paid",
    summary="Record manual/bank-transfer payment",
)
async def mark_paid(
    placement_id: uuid.UUID,
    body: PlacementMarkPaidRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.mark_paid(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        payment_reference=body.payment_reference,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/placements/{placement_id}/cancel", summary="Disable any placement immediately")
async def admin_cancel(
    placement_id: uuid.UUID,
    body: PlacementAdminCancelRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason = body.reason if body else None
    version = body.version if body else None
    data = await moderation_service.admin_cancel(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        reason=reason,
        version=version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post(
    "/placements/{placement_id}/disclosure-class",
    summary="Relabel a placement's public inventory class",
)
async def set_disclosure_class(
    placement_id: uuid.UUID,
    body: DisclosureClassRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.set_disclosure_class(
        session,
        principal=auth.principal,
        placement_id=placement_id,
        disclosure_class=body.disclosure_class,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/creatives/{creative_id}/review", summary="Approve or reject a creative")
async def review_creative(
    creative_id: uuid.UUID,
    body: CreativeReviewRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await moderation_service.review_creative(
        session,
        principal=auth.principal,
        creative_id=creative_id,
        decision=body.decision,
        note=body.note,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)
