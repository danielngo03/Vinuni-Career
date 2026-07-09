"""Human review queue HTTP routes (``/api/v1/moderation/review-queue``).

University-moderator surface for AI-escalated findings (AI_PRODUCT_SPEC §9.3).
HTTP-only: RBAC and transitions live in ``review_queue_service``. The presenter
returns rule-based findings verbatim (they contain no provider/model/prompt
internals by construction) but never internal raw scores from fraud
assessment — those are mapped to ``risk_level`` wording upstream.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.moderation.application import (
    fraud_scan_service,
    report_service,
    review_queue_service,
    triage_service,
)
from app.modules.moderation.domain.models import HumanReviewItem
from app.shared.responses import success

router = APIRouter(prefix="/moderation", tags=["moderation"])
content_reports_router = APIRouter(tags=["moderation"])


class ReviewDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _present(item: HumanReviewItem) -> dict:
    return {
        "id": str(item.id),
        "source": item.source,
        "resource_type": item.resource_type,
        "resource_id": str(item.resource_id) if item.resource_id else None,
        "severity": item.severity,
        "status": item.status,
        "findings": item.findings_json,
        "resolution_note": item.resolution_note,
        "created_at": item.created_at.isoformat(),
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
    }


@router.get("/review-queue", summary="List AI-escalated human review items")
async def list_review_items(
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await review_queue_service.list_items(
        session, principal=auth.principal, status=status, source=source, limit=limit
    )
    return success([_present(i) for i in items])


@router.post(
    "/fraud-scan/jobs/{job_id}",
    summary="Run a deterministic fraud-signal scan on a job posting",
)
async def fraud_scan_job(
    job_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await fraud_scan_service.scan_job(
        session, principal=auth.principal, job_id=job_id
    )
    return success(result)


@router.post(
    "/review-queue/{item_id}/resolve",
    summary="Confirm an AI finding after human review",
)
async def resolve_review_item(
    item_id: uuid.UUID,
    body: ReviewDecisionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    item = await review_queue_service.resolve_item(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        item_id=item_id,
        note=body.note,
    )
    return success(_present(item))


@router.post(
    "/review-queue/{item_id}/dismiss",
    summary="Dismiss an AI finding as a false positive",
)
async def dismiss_review_item(
    item_id: uuid.UUID,
    body: ReviewDecisionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    item = await review_queue_service.dismiss_item(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        item_id=item_id,
        note=body.note,
    )
    return success(_present(item))


# --------------------------------------------------------------------------- #
# Abuse & content reports (ADR-0014, E36)                                     #
# --------------------------------------------------------------------------- #


class ContentReportCreate(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    reason_code: str = Field(max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class OverrideRequest(BaseModel):
    note: str = Field(max_length=2000)


@content_reports_router.post("/content-reports", summary="Report an entity")
async def create_content_report(
    body: ContentReportCreate,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await report_service.submit(
        session,
        principal=auth.principal,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        reason_code=body.reason_code,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(result)


@content_reports_router.post(
    "/content-reports/{report_id}/escalate",
    summary="Escalate a content report into the human review queue",
)
async def escalate_content_report(
    report_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await triage_service.escalate_report(
        session, principal=auth.principal, report_id=report_id, ctx=auth.ctx
    )
    return success(result)


@content_reports_router.post(
    "/content-reports/{report_id}/dismiss",
    summary="Dismiss a content report as no-action",
)
async def dismiss_content_report(
    report_id: uuid.UUID,
    body: ReviewDecisionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await triage_service.dismiss_report(
        session,
        principal=auth.principal,
        report_id=report_id,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(result)


@router.get("/triage", summary="Merged abuse/fraud triage list")
async def list_triage(
    source: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await triage_service.list_triage(
        session,
        principal=auth.principal,
        source=source,
        entity_type=entity_type,
        limit=limit,
    )
    return success(items)


@router.post(
    "/actions/{review_item_id}/override",
    summary="Reverse a prior moderation action",
)
async def override_moderation_action(
    review_item_id: uuid.UUID,
    body: OverrideRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await triage_service.override_action(
        session,
        principal=auth.principal,
        review_item_id=review_item_id,
        note=body.note,
        ctx=auth.ctx,
    )
    return success(result)
