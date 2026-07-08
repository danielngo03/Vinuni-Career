"""Mock-interview admin routes — university governance + AI-ops debug.

HTTP only. Authorization is enforced in the application layer:
- University staff (``org_type == "university"`` + ``mock_interview`` grant) read
  aggregate stats/config (``governance_service``).
- Platform superadmins read flagged-session metadata and open audited transcripts
  for AI debugging (``ops_service``). Partners can reach none of it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.mock_interview.application import governance_service, ops_service
from app.shared.responses import success

admin_router = APIRouter(prefix="/admin/mock-interview", tags=["mock-interview-admin"])


@admin_router.get("/stats", summary="Aggregate mock-interview usage (university)")
async def stats(
    days: int = Query(30, ge=1, le=365),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await governance_service.stats(
        session, principal=auth.principal, days=days
    )
    return success(data)


@admin_router.get("/config", summary="Effective caps + realtime status (university)")
async def config(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await governance_service.config(session, principal=auth.principal)
    return success(data)


@admin_router.get("/flagged", summary="Safety-flagged sessions (superadmin)")
async def flagged(
    limit: int = Query(50, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ops_service.list_flagged(
        session, principal=auth.principal, limit=limit
    )
    return success(data)


@admin_router.get(
    "/sessions/{session_id}/transcript",
    summary="Open a session transcript for AI debugging (superadmin, audited)",
)
async def transcript(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await ops_service.view_transcript(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        session_id=session_id,
    )
    return success(data)
