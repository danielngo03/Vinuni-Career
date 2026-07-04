"""University admin: user management HTTP routes (``/api/v1/admin/users``).

All endpoints require a university actor (jobs:moderate + university org) or
platform superadmin. Business logic lives in ``admin_users_service``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.users.application import admin_users_service
from app.shared.responses import success

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", summary="List platform users — university governance view")
async def list_platform_users(
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


@router.post("/{user_id}/suspend", summary="Suspend a user account")
async def suspend_user(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.suspend_user(
        session, principal=auth.principal, user_id=user_id
    )
    return success(data)


@router.post("/{user_id}/unsuspend", summary="Restore a suspended user account")
async def unsuspend_user(
    user_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await admin_users_service.unsuspend_user(
        session, principal=auth.principal, user_id=user_id
    )
    return success(data)
