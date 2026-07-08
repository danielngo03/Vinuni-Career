"""University control-plane account governance HTTP routes.

Mounted at ``/api/v1/university/governance/accounts``. The university control
plane governs BOTH student and partner-member accounts. All endpoints are
grant-gated in ``admin_users_service`` (``accounts:govern`` + acting-university
org; superadmin bypasses). Routers carry no business logic.

- GET    ""                        -> list accounts (cross-persona, privacy-safe)
- GET    "/{user_id}"              -> account detail (privacy-safe)
- POST   "/{user_id}/suspend"      -> suspend  (body: {reason})
- POST   "/{user_id}/reinstate"    -> reinstate (body: {reason})

The superadmin ``/admin/users`` surface (``platform_admin``) is separate and
unchanged.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.users.application import admin_users_service
from app.shared.responses import success

router = APIRouter(
    prefix="/university/governance/accounts", tags=["university-governance"]
)


class GovernanceActionRequest(BaseModel):
    """Required, non-empty reason recorded on every governance write."""

    reason: str = Field(min_length=1, max_length=500)


@router.get("", summary="List student & partner accounts — university governance")
async def list_accounts(
    persona: str | None = Query(
        None, description="Filter by persona (student|partner_member|university_staff)"
    ),
    q: str | None = Query(None, description="Search by email or name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.list_platform_users(
        session,
        principal=auth.principal,
        persona=persona,
        q=q,
        page=page,
        page_size=page_size,
    )
    return success(data)


@router.get("/{user_id}", summary="Account detail — university governance")
async def get_account_detail(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.get_account_detail(
        session, principal=auth.principal, user_id=user_id
    )
    return success(data)


@router.post("/{user_id}/suspend", summary="Suspend an account (reason required)")
async def suspend_account(
    user_id: uuid.UUID,
    body: GovernanceActionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.suspend_user(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
        reason=body.reason,
    )
    return success(data)


@router.post("/{user_id}/reinstate", summary="Reinstate an account (reason required)")
async def reinstate_account(
    user_id: uuid.UUID,
    body: GovernanceActionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.unsuspend_user(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        user_id=user_id,
        reason=body.reason,
    )
    return success(data)
