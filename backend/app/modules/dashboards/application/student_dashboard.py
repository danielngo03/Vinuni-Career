"""Student command-center read model (``GET /dashboards/student``).

RBAC: the acting principal must be a ``student`` (wrong persona -> ``403``). All
data is scoped to the acting student's own ``user_id`` — a student never sees
another student's applications, CVs, or reveals. The gate runs before any widget
so it is never swallowed by the failure-tolerant widget wrapper.

The profile is identity-only (owner decision 2026-07-06): there is no
profile-completion metric anymore. The dashboard's "get set up" nudge is now
CV-first — it points the student at building a CV, where all career content lives.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain import personas
from app.modules.dashboards.application._common import (
    RECENT_CAP,
    RECOMMENDED_CAP,
    empty_rows,
    safe,
)
from app.modules.discovery.application import ranking_service
from app.modules.documents.application import cv_service
from app.modules.opportunities.application import job_alert_service, job_read_facade
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal


def _require_student(principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.STUDENT:
        raise PermissionDeniedError()


async def get_student_dashboard(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    _require_student(principal)
    user_id = principal.user_id
    assert user_id is not None

    counts = await safe(
        session,
        lambda: recruitment_read.count_student_applications(session, user_id=user_id),
        fallback={"total": 0, "active": 0},
    )
    cv_count = await safe(
        session,
        lambda: cv_service.count_cvs(session, principal=principal),
        fallback=0,
    )
    pending_reveals = await safe(
        session,
        lambda: recruitment_read.count_pending_reveals_for_student(
            session, user_id=user_id
        ),
        fallback=0,
    )
    alert_count = await safe(
        session,
        lambda: job_alert_service.count_alerts_for_user(session, user_id=user_id),
        fallback=0,
    )

    metrics = {
        "applications_total": counts["total"],
        "applications_active": counts["active"],
        "cv_count": cv_count,
        "alert_count": alert_count,
    }

    next_actions: list[dict] = []
    if cv_count == 0:
        next_actions.append(
            {"key": "build_cv", "href": "/student/cv", "count": None}
        )
    if pending_reveals > 0:
        next_actions.append(
            {
                "key": "respond_reveal",
                "href": "/student/applications",
                "count": pending_reveals,
            }
        )
    if alert_count == 0:
        next_actions.append(
            {"key": "create_alert", "href": "/student/alerts", "count": None}
        )

    applications_recent = await safe(
        session,
        lambda: recruitment_read.list_recent_student_applications(
            session, user_id=user_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )
    reveal_requests_pending = await safe(
        session,
        lambda: recruitment_read.list_pending_reveals_for_student(
            session, user_id=user_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )
    upcoming_interviews = await safe(
        session,
        lambda: recruitment_read.list_upcoming_student_interviews(
            session, user_id=user_id, limit=RECENT_CAP, locale=locale
        ),
        fallback=empty_rows(),
    )
    # Honest recommendations: if the student has a CV (and/or confirmed
    # preferences), the ranker returns REAL recommendations (reason codes + score +
    # ``source=recommended``); otherwise it honestly falls back to ``source=recent``
    # / ``popular``. The frontend labels the rail by ``source`` — a recent list is
    # never mislabelled "recommended". Sponsored inventory is delivered elsewhere
    # (``with_sponsored=False``), so it can never reorder this organic rail.
    recommended_jobs = await safe(
        session,
        lambda: ranking_service.recommend_jobs(
            session,
            principal=principal,
            limit=RECOMMENDED_CAP,
            locale=locale,
            with_sponsored=False,
        ),
        fallback={"source": "recent", "personalized": False, "items": []},
    )
    upcoming_events: list[dict] = await safe(
        session,
        lambda: job_read_facade.list_upcoming_registered_events(
            session, user_id=user_id, locale=locale
        ),
        fallback=[],
    )

    return {
        "metrics": metrics,
        "next_actions": next_actions,
        "applications_recent": applications_recent,
        "reveal_requests_pending": reveal_requests_pending,
        "upcoming_interviews": upcoming_interviews,
        "upcoming_events": upcoming_events,
        "recommended_jobs": recommended_jobs,
    }
