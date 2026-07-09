"""Company-reviews HTTP routes (ADR-0013).

`router` — public company-profile reviews + student CRUD + report
(`/api/v1/companies/{slug}/reviews`, `/api/v1/reviews/{id}`).
`admin_router` — university moderation (`/api/v1/admin/reviews`).

HTTP-only: authenticate, delegate to the services (which own RBAC, eligibility,
audit, projection recompute), wrap in the standard envelope.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.reviews.api.schemas import (
    PartnerResponseRequest,
    ReviewRemoveRequest,
    ReviewReportRequest,
    ReviewWriteRequest,
)
from app.modules.reviews.application import (
    review_moderation_service,
    review_service,
)
from app.shared.permissions import GUEST
from app.shared.responses import success

router = APIRouter(tags=["reviews"])
admin_router = APIRouter(prefix="/admin/reviews", tags=["reviews-moderation"])


# --------------------------------------------------------------------------- #
# Public + student surface                                                    #
# --------------------------------------------------------------------------- #


@router.get(
    "/companies/{slug}/reviews",
    summary="Public published reviews for a company",
)
async def list_company_reviews(
    slug: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    limit: int | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    # Optional auth: inject my_vote when caller is authenticated.
    principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001 — optional: bad token → guest
            pass
    data = await review_service.list_public_reviews(
        session, slug=slug, principal=principal, limit=limit, locale=locale
    )
    return success(data)


@router.post(
    "/companies/{slug}/reviews",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review (eligible student)",
)
async def submit_company_review(
    slug: str,
    body: ReviewWriteRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_service.submit_review(
        session,
        principal=auth.principal,
        slug=slug,
        payload=body.to_payload(),
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.get(
    "/companies/{slug}/reviews/mine",
    summary="My own review for a company (any status, or 404)",
)
async def get_my_company_review(
    slug: str,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_service.get_my_review(
        session, principal=auth.principal, slug=slug, locale=locale
    )
    return success(data)


@router.patch("/reviews/{review_id}", summary="Edit own review (re-moderates)")
async def update_review(
    review_id: uuid.UUID,
    body: ReviewWriteRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_service.update_review(
        session,
        principal=auth.principal,
        review_id=review_id,
        payload=body.to_payload(),
        version=body.version,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@router.delete(
    "/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete own review",
)
async def delete_review(
    review_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await review_service.delete_review(
        session, principal=auth.principal, review_id=review_id, ctx=auth.ctx
    )


@router.post(
    "/reviews/{review_id}/helpful",
    summary="Mark a published review as helpful (authenticated)",
)
async def vote_helpful(
    review_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await review_service.vote_helpful(session, principal=auth.principal, review_id=review_id)
    return success(data)


@router.delete(
    "/reviews/{review_id}/helpful",
    summary="Remove helpful vote from a review (authenticated)",
)
async def remove_helpful_vote(
    review_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await review_service.remove_helpful_vote(
        session, principal=auth.principal, review_id=review_id
    )
    return success(data)


@router.post(
    "/reviews/{review_id}/response",
    summary="Add or update partner public response to a review",
)
async def add_partner_response(
    review_id: uuid.UUID,
    body: PartnerResponseRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _ = request
    data = await review_service.add_partner_response(
        session,
        principal=auth.principal,
        review_id=review_id,
        response_text=body.response,
        ctx=auth.ctx,
    )
    return success(data)


@router.post("/reviews/{review_id}/report", summary="Report a published review")
async def report_review(
    review_id: uuid.UUID,
    body: ReviewReportRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await review_service.report_review(
        session,
        principal=auth.principal,
        review_id=review_id,
        reason_code=body.reason_code,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# University moderation surface                                               #
# --------------------------------------------------------------------------- #


@admin_router.get("", summary="Review moderation queue (university)")
async def moderation_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    review_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_moderation_service.list_queue(
        session,
        principal=auth.principal,
        status=review_status,
        limit=limit,
        locale=locale,
    )
    return success(data)


@admin_router.post("/{review_id}/publish", summary="Publish a pending review")
async def publish_review(
    review_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_moderation_service.publish_review(
        session,
        principal=auth.principal,
        review_id=review_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@admin_router.post("/{review_id}/remove", summary="Remove a review (policy-gated)")
async def remove_review(
    review_id: uuid.UUID,
    body: ReviewRemoveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_moderation_service.remove_review(
        session,
        principal=auth.principal,
        review_id=review_id,
        reason=body.reason,
        note=body.note,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


@admin_router.post("/{review_id}/restore", summary="Restore a removed review")
async def restore_review(
    review_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await review_moderation_service.restore_review(
        session,
        principal=auth.principal,
        review_id=review_id,
        ctx=auth.ctx,
        locale=locale,
    )
    return success(data)


__all__ = ["router", "admin_router"]
