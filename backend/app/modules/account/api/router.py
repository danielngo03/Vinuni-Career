"""Account settings HTTP routes (``/api/v1/account/*``).

HTTP-only: validate, delegate to the account service (which enforces RBAC + audit),
shape the envelope. Device/session responses are privacy-safe by construction.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.account.api.schemas import (
    PasswordChangeRequest,
    PreferencesPatch,
    TotpVerifyRequest,
)
from app.modules.account.application import account_service
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.responses import paginated, success

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/preferences", summary="Get account + notification preferences")
async def get_preferences(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await account_service.get_preferences(session, principal=auth.principal)
    return success(data)


@router.patch("/preferences", summary="Update account + notification preferences")
async def update_preferences(
    body: PreferencesPatch,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await account_service.update_preferences(
        session,
        principal=auth.principal,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/sessions", summary="List active sessions/devices (safe metadata)")
async def list_sessions(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await account_service.list_sessions(
        session, principal=auth.principal, current_session_id=auth.claims.session_id
    )
    return paginated(items, next_cursor=None, limit=len(items))


@router.post("/sessions/{session_id}/revoke", summary="Remote-logout a session")
async def revoke_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await account_service.revoke_session(
        session, principal=auth.principal, session_id=session_id, ctx=auth.ctx
    )
    return success({"status": "revoked"})


@router.get("/security-events", summary="Recent security events")
async def list_security_events(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await account_service.list_events(session, principal=auth.principal)
    return paginated(items, next_cursor=None, limit=len(items))


@router.patch("/password", summary="Change password (re-auth + revoke others)")
async def change_password(
    body: PasswordChangeRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await account_service.change_password(
        session,
        principal=auth.principal,
        current_session_id=auth.claims.session_id,
        current_password=body.current_password,
        new_password=body.new_password,
        ctx=auth.ctx,
    )
    return success({"status": "password_changed"})


@router.post("/totp/setup", summary="Begin TOTP enrolment")
async def totp_setup(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await account_service.totp_setup(session, principal=auth.principal, ctx=auth.ctx)
    return success(data)


@router.post("/totp/verify", summary="Confirm TOTP enrolment")
async def totp_verify(
    body: TotpVerifyRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await account_service.totp_verify(
        session, principal=auth.principal, code=body.code, ctx=auth.ctx
    )
    return success(data)


@router.post("/totp/disable", summary="Disable TOTP")
async def totp_disable(
    body: TotpVerifyRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await account_service.totp_disable(
        session, principal=auth.principal, code=body.code, ctx=auth.ctx
    )
    return success(data)
