"""Partner command-center read model (``GET /dashboards/partner``).

RBAC + tenancy: the acting principal must be a ``partner_member`` (wrong persona
-> ``403``) and must have an org context (``principal.org_id``); a partner without
an org -> ``404``. Every count/list is scoped to that single ``org_id`` — a
partner never sees another org's jobs, applications, or reveals.

Privacy: ``applications_recent`` rows carry only the deterministic anonymous
candidate handle (never name/email); the partner opens the application detail
(which enforces the reveal handshake) to see identity where permitted.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain import personas
from app.modules.dashboards.application._common import RECENT_CAP, empty_rows, safe
from app.modules.opportunities.application import dashboard_read as opportunities_read
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal

_ZERO_JOB_COUNTS = {
    "active": 0,
    "draft": 0,
    "pending_review": 0,
    "rejected": 0,
    "closed": 0,
}


def _require_partner(principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.PARTNER_MEMBER:
        raise PermissionDeniedError()


async def _org_name(session: AsyncSession, org_id: uuid.UUID) -> str | None:
    return await org_reporting_facade.display_name_for(session, org_id)


async def get_partner_dashboard(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    _require_partner(principal)
    org_id = principal.org_id
    if org_id is None:
        raise ResourceNotFoundError()

    org_name = await safe(session, lambda: _org_name(session, org_id), fallback=None)
    job_counts = await safe(
        session,
        lambda: opportunities_read.count_org_jobs_by_status(session, org_id=org_id),
        fallback=dict(_ZERO_JOB_COUNTS),
    )
    applications_total = await safe(
        session,
        lambda: recruitment_read.count_org_applications(session, org_id=org_id),
        fallback=0,
    )
    reveals_pending = await safe(
        session,
        lambda: recruitment_read.count_org_pending_reveals(session, org_id=org_id),
        fallback=0,
    )

    metrics = {
        "jobs_active": job_counts["active"],
        "jobs_draft": job_counts["draft"],
        "jobs_pending_review": job_counts["pending_review"],
        "applications_total": applications_total,
        "reveals_pending_response": reveals_pending,
    }

    next_actions: list[dict] = []
    if reveals_pending > 0:
        next_actions.append(
            {
                "key": "respond_reveals",
                "href": "/partner/applications",
                "count": reveals_pending,
            }
        )
    if job_counts["draft"] > 0:
        next_actions.append(
            {"key": "jobs_in_draft", "href": "/partner/jobs", "count": job_counts["draft"]}
        )
    if job_counts["pending_review"] > 0:
        next_actions.append(
            {
                "key": "jobs_pending_review",
                "href": "/partner/jobs",
                "count": job_counts["pending_review"],
            }
        )
    # Posting a job is always available to a partner.
    next_actions.append({"key": "post_job", "href": "/partner/jobs/new", "count": None})

    jobs_attention = await safe(
        session,
        lambda: opportunities_read.list_org_jobs_needing_attention(
            session, org_id=org_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )
    applications_recent = await safe(
        session,
        lambda: recruitment_read.list_recent_org_applications(
            session, org_id=org_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )

    return {
        "org_name": org_name,
        "metrics": metrics,
        "next_actions": next_actions,
        "jobs_attention": jobs_attention,
        "applications_recent": applications_recent,
    }
