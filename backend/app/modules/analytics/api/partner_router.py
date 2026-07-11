"""Partner-analytics HTTP routes: public engagement pixel + the (permission-
gated) candidate-access compliance log.

Routers are HTTP-only: validate, delegate to the application-layer services
(which enforce RBAC + tenant isolation), and shape the response envelope. No
business logic here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.analytics.api.schemas import JobEngagementRequest
from app.modules.analytics.application import (
    partner_candidate_access_service,
    partner_job_metrics_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.opportunities.application import job_read_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker
from app.shared.responses import success

router = APIRouter(prefix="/analytics", tags=["analytics"])

_ENGAGEMENT_EVENT_TYPES = {"impression", "cta_click", "share_click"}


@router.post(
    "/jobs/{job_id}/engagement",
    summary="Record a public job-engagement signal (impression / CTA click / share)",
)
async def record_job_engagement(
    job_id: uuid.UUID,
    body: JobEngagementRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Public (optional-auth) engagement pixel for signals with no other
    authoritative backend write (a genuine detail view / save / apply are
    already recorded server-side at their own endpoint — this is only for the
    list-impression / CTA-click / share-click surfaces).

    Mirrors ``POST /discovery/events``: returns only ``{"recorded": true}``,
    never the internal metrics row, and never distinguishes a hidden/missing job
    from an ignored one (enumeration-safe no-op).
    """

    if body.event_type not in _ENGAGEMENT_EVENT_TYPES:
        raise ValidationFailedError(details={"field": "event_type"})
    if body.source is not None and body.source not in partner_job_metrics_service.SOURCE_VALUES:
        raise ValidationFailedError(details={"field": "source"})

    principal: Principal | None = None
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001
            principal = None

    job = await job_read_facade.get_job_ref(session, job_id)
    if job is not None and job.status == "active":
        try:
            source = body.source or await partner_job_metrics_service.default_source_for_job(
                session, job_id=job.id
            )
            student_tier = (
                partner_job_metrics_service.student_tier_for_persona(principal.persona)
                if principal is not None
                else None
            )
            major_group, year_group = await partner_job_metrics_service.coarse_academic_dims(
                session, user_id=principal.user_id if principal is not None else None
            )
            await partner_job_metrics_service.record_job_metric_event(
                session,
                org_id=job.org_id,
                job_id=job.id,
                event_type=body.event_type,
                source=source,
                device_class=partner_job_metrics_service.coarse_device_class(
                    request.headers.get("user-agent")
                ),
                student_tier=student_tier,
                major_group=major_group,
                year_group=year_group,
            )
            await session.commit()
        except Exception:  # noqa: BLE001 — this endpoint's entire job is best-effort telemetry
            await session.rollback()
    return success({"recorded": True})


def _require_access_log_permission(principal: Principal, *, org_id: uuid.UUID) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.org_id != org_id and not principal.is_superadmin:
        raise PermissionDeniedError()
    if not (
        principal.is_superadmin
        or permission_checker.can(
            principal, "candidate_identity", "download_cv", resource_org_id=org_id
        )
        or permission_checker.can(principal, "analytics", "view_clicks", resource_org_id=org_id)
    ):
        raise PermissionDeniedError()


@router.get(
    "/partner/candidate-access-log",
    summary="Who accessed which candidate — compliance/security review (permission-gated)",
)
async def get_candidate_access_log(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    limit: int = 50,
) -> dict:
    principal = auth.principal
    if principal.org_id is None:
        raise PermissionDeniedError()
    _require_access_log_permission(principal, org_id=principal.org_id)
    items = await partner_candidate_access_service.list_access_events(
        session, org_id=principal.org_id, limit=limit
    )
    return success({"items": items})
