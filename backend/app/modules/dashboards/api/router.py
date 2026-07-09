"""Persona dashboard HTTP routes (``/api/v1/dashboards``).

Routers are HTTP-only: authenticate, delegate to the read-model service (which
enforces the persona RBAC gate and assembles the failure-tolerant widgets), and
wrap the result in the standard object envelope. No business logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.analytics.application import (
    advertising_performance_service,
    partner_ops_dashboard_service,
    partner_recruiting_funnel_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.dashboards.application import (
    market_intelligence_service,
    partner_dashboard,
    student_dashboard,
    university_dashboard,
)
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.responses import success

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("/student", summary="Student command-center read model")
async def get_student_dashboard(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await student_dashboard.get_student_dashboard(session, principal=auth.principal)
    return success(data)


@router.get("/partner", summary="Partner command-center read model")
async def get_partner_dashboard(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_dashboard.get_partner_dashboard(session, principal=auth.principal)
    return success(data)


@router.get("/university", summary="University command-center read model")
async def get_university_dashboard(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await university_dashboard.get_university_dashboard(session, principal=auth.principal)
    return success(data)


@router.get(
    "/university/market-intelligence",
    summary="Aggregate hiring-market intelligence (university staff only)",
)
async def get_market_intelligence(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await market_intelligence_service.get_market_intelligence(
        session, principal=auth.principal
    )
    return success(data)


@router.get(
    "/university/reports", summary="University platform stats — KPI snapshot for governance"
)
async def get_university_reports(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.modules.dashboards.application import university_dashboard

    data = await university_dashboard.platform_stats_for_university(
        session, principal=auth.principal
    )
    return success(data)


@router.get(
    "/partner/pipeline-overview",
    summary="Partner pipeline overview — per-job candidate counts",
)
async def get_partner_pipeline_overview(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    p = auth.principal
    if not p.is_authenticated:
        raise AuthRequiredError()
    if p.persona != "partner_member":
        raise PermissionDeniedError()
    if not p.org_id:
        return success({"jobs": [], "total_active": 0})

    jobs = await recruitment_read.pipeline_overview_for_org(session, org_id=p.org_id)
    total_active = sum(j["active_total"] for j in jobs)
    return success({"jobs": jobs, "total_active": total_active})


@router.get(
    "/partner/ops",
    summary="Partner command-center V2 — todos, job performance, team activity, RBAC-gated widgets",
)
async def get_partner_dashboard_ops(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        session, principal=auth.principal
    )
    return success(data)


@router.get("/partner/analytics", summary="Partner analytics — funnel, top jobs, monthly trend")
async def get_partner_analytics(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    p = auth.principal
    if not p.is_authenticated:
        raise AuthRequiredError()
    if p.persona != "partner_member":
        raise PermissionDeniedError()
    if not p.org_id:
        return success({"funnel": [], "top_jobs": [], "monthly_trend": []})

    funnel = await recruitment_read.analytics_application_funnel(session, org_id=p.org_id)
    top_jobs = await recruitment_read.analytics_top_jobs(session, org_id=p.org_id)
    monthly = await recruitment_read.analytics_monthly_trend(session, org_id=p.org_id)
    return success({"funnel": funnel, "top_jobs": top_jobs, "monthly_trend": monthly})


@router.get(
    "/partner/analytics/recruiting-funnel",
    summary="Partner recruiting funnel — stage conversion, time-to-hire, time-in-stage",
)
async def get_partner_recruiting_funnel(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await partner_recruiting_funnel_service.get_recruiting_funnel(
        session, principal=auth.principal
    )
    return success(data)


@router.get(
    "/partner/analytics/advertising",
    summary="Partner campaign/advertising performance — impressions, clicks, CTR, spend",
)
async def get_partner_advertising_performance(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await advertising_performance_service.get_campaign_performance(
        session, principal=auth.principal
    )
    return success(data)
