"""Career-outcomes university read routes (``/api/v1/career-outcomes``).

HTTP-only: authenticate, delegate to the read service (which enforces the
university-only RBAC gate and maps raw enums to friendly labels), wrap in the
standard envelope. The underlying table holds no student PII / no salary, and the
service exposes only aggregates + a privacy-safe record list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.career_outcomes.application import read_service
from app.shared.responses import success

router = APIRouter(prefix="/career-outcomes", tags=["career-outcomes"])


@router.get("/kpi", summary="University career-outcomes KPI roll-up")
async def get_kpi(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    locale: str = Query(default="vi"),
) -> dict:
    data = await read_service.get_kpi(session, principal=auth.principal, locale=locale)
    return success(data)


@router.get("/records", summary="University privacy-safe outcome records")
async def list_records(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    trust_level: int | None = Query(default=None, ge=1, le=4),
    limit: int | None = Query(default=None),
    locale: str = Query(default="vi"),
) -> dict:
    data = await read_service.list_records(
        session,
        principal=auth.principal,
        trust_level=trust_level,
        limit=limit,
        locale=locale,
    )
    return success(data)
