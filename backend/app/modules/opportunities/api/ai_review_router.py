"""AI human-review queue HTTP routes (``/api/v1/university/moderation/ai-review-queue``).

University-moderator surface over AI/rule-FLAGGED jobs + events (B-579). HTTP-only:
RBAC (grant-gated), transitions, and audit live in
``opportunities.application.ai_review_queue_service`` (which reuses the existing
``moderation_service`` / ``event_moderation_service`` transitions). AI flags are
ADVISORY; every decision here is a human's final say.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.opportunities.application import ai_review_queue_service
from app.shared.responses import success

ai_review_router = APIRouter(
    prefix="/university/moderation/ai-review-queue", tags=["university-moderation"]
)


class FlagDecisionRequest(BaseModel):
    """Human decision on an AI/rule flag — a reason is always required."""

    reason: str = Field(min_length=1, max_length=2000)
    # Uphold only: the structured moderation reason code to record on the reject.
    # Defaults to the flag's own reason code when omitted.
    reason_code: str | None = Field(default=None, max_length=30)


@ai_review_router.get("", summary="AI human-review queue (flagged jobs + events)")
async def list_ai_review_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    limit: int | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    items, counts = await ai_review_queue_service.list_queue(
        session, principal=auth.principal, limit=limit, locale=locale,
    )
    return success(items, meta={"counts": counts, "count": counts["total"]})


@ai_review_router.get("/counts", summary="AI human-review queue badge counts")
async def ai_review_queue_counts(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    counts = await ai_review_queue_service.get_counts(
        session, principal=auth.principal,
    )
    return success(counts)


@ai_review_router.post(
    "/{item_type}/{item_id}/uphold",
    summary="Uphold an AI flag (reject the item) — human final say",
)
async def uphold_flag(
    item_type: str,
    item_id: uuid.UUID,
    body: FlagDecisionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await ai_review_queue_service.uphold(
        session, principal=auth.principal, item_type=item_type, item_id=item_id,
        reason=body.reason, reason_code=body.reason_code, ctx=auth.ctx, locale=locale,
    )
    return success(data)


@ai_review_router.post(
    "/{item_type}/{item_id}/dismiss",
    summary="Dismiss an AI flag (clear it) — human final say",
)
async def dismiss_flag(
    item_type: str,
    item_id: uuid.UUID,
    body: FlagDecisionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await ai_review_queue_service.dismiss(
        session, principal=auth.principal, item_type=item_type, item_id=item_id,
        reason=body.reason, ctx=auth.ctx, locale=locale,
    )
    return success(data)
