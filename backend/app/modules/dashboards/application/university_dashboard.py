"""University command-center read model (``GET /dashboards/university``).

RBAC mirrors the job-moderation / partner-review gate
(``moderation_service._require_university_moderator`` /
``partner_registration_service._require_university_actor``): a platform superadmin,
or a member of a **university** org holding ``jobs:moderate``. A partner Admin holds
``*:*`` (which would otherwise match ``jobs:moderate``), so the org-type gate keeps
this surface university-only. Wrong persona -> ``403``.

The university moderation scope is platform-wide by design (pending jobs and
partner registrations across all orgs); this is the governance surface, not a
tenant-scoped one.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboards.application._common import RECENT_CAP, empty_rows, safe
from app.modules.opportunities.application import dashboard_read as opportunities_read
from app.modules.opportunities.application import job_read_facade, public_read
from app.modules.organization.application import (
    company_directory_service,
    org_reporting_facade,
    partner_registration_service,
)
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.modules.users.application import user_read_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal, permission_checker


async def _require_university(session: AsyncSession, principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "jobs", "moderate"):
        raise PermissionDeniedError()
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def get_university_dashboard(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    await _require_university(session, principal)

    jobs_pending = await safe(
        session,
        lambda: opportunities_read.count_pending_moderation_jobs(session),
        fallback=0,
    )
    jobs_active_total = await safe(
        session,
        lambda: public_read.count_visible_jobs(session),
        fallback=0,
    )
    partners_active = await safe(
        session,
        lambda: company_directory_service.count_public_companies(session),
        fallback=0,
    )
    # Pending partner registrations (single source -> both metric + recent list).
    partner_requests = await safe(
        session,
        lambda: partner_registration_service.list_requests(
            session, principal=principal, status="pending_review", locale=locale
        ),
        fallback=empty_rows(),
    )
    partners_pending = len(partner_requests)

    metrics = {
        "jobs_pending_moderation": jobs_pending,
        "partners_pending": partners_pending,
        "partners_active": partners_active,
        "jobs_active_total": jobs_active_total,
    }

    next_actions: list[dict] = []
    if jobs_pending > 0:
        next_actions.append(
            {
                "key": "review_jobs",
                "href": "/university/moderation/jobs",
                "count": jobs_pending,
            }
        )
    if partners_pending > 0:
        next_actions.append(
            {
                "key": "review_partners",
                "href": "/university/moderation/partners",
                "count": partners_pending,
            }
        )

    moderation_queue_recent = await safe(
        session,
        lambda: opportunities_read.list_pending_moderation_jobs(
            session, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )
    partner_requests_recent = [
        {
            "id": req["id"],
            "company_name": req["company_name"],
            "submitted_at": req["created_at"],
        }
        for req in partner_requests[:RECENT_CAP]
    ]

    return {
        "metrics": metrics,
        "next_actions": next_actions,
        "moderation_queue_recent": moderation_queue_recent,
        "partner_requests_recent": partner_requests_recent,
    }


async def platform_stats_for_university(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Platform-wide KPI snapshot for university governance reporting.

    Returns aggregate counts across the entire platform — no per-user PII.
    Gated to university staff / superadmin (same gate as the dashboard).
    """
    await _require_university(session, principal)

    students = await safe(
        session,
        lambda: user_read_facade.count_identities_by_persona(session, "student"),
        fallback=0,
    )
    partner_members = await safe(
        session,
        lambda: user_read_facade.count_identities_by_persona(session, "partner_member"),
        fallback=0,
    )
    jobs = await safe(session, lambda: job_read_facade.count_all_jobs(session), fallback=0)
    applications = await safe(
        session, lambda: recruitment_read.count_all_applications(session), fallback=0
    )
    events = await safe(
        session, lambda: job_read_facade.count_published_events(session), fallback=0
    )
    monthly: list[dict] = await safe(
        session,
        lambda: recruitment_read.monthly_application_counts(session, months=6),
        fallback=[],
    )

    return {
        "kpis": {
            "students": students,
            "partner_members": partner_members,
            "jobs": jobs,
            "applications": applications,
            "events": events,
        },
        "monthly_applications": monthly,
    }
