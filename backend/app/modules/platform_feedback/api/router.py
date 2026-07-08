"""Platform feedback endpoint — POST /feedback."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import get_current_auth
from app.modules.platform_feedback.domain.models import UserFeedback
from app.shared.permissions import GUEST, Principal
from app.shared.responses import success

router = APIRouter(prefix="/feedback", tags=["feedback"])

_ALLOWED_CATEGORIES = {"bug", "suggestion", "praise", "other"}


class FeedbackBody(BaseModel):
    category: str = Field(min_length=1, max_length=32)
    message: str = Field(min_length=3, max_length=1000)
    page_url: str | None = Field(default=None, max_length=512)


async def _optional_principal(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Principal:
    """Resolve the caller's principal; degrade to guest on any auth failure."""
    try:
        auth = await get_current_auth(request, session)
        return auth.principal
    except Exception:  # noqa: BLE001 — optional auth, never block on a bad token
        return GUEST


@router.post("", summary="Submit platform feedback")
async def submit_feedback(
    body: Annotated[FeedbackBody, Body()],
    principal: Principal = Depends(_optional_principal),
    session: AsyncSession = Depends(get_db_session),
):
    category = body.category.lower().strip()
    if category not in _ALLOWED_CATEGORIES:
        category = "other"

    fb = UserFeedback(
        id=uuid.uuid4(),
        user_id=principal.user_id if principal.is_authenticated else None,
        category=category,
        message=body.message.strip(),
        page_url=body.page_url,
        created_at=datetime.now(UTC),
    )
    session.add(fb)
    await session.commit()

    return success({"id": str(fb.id), "created_at": fb.created_at.isoformat()})
