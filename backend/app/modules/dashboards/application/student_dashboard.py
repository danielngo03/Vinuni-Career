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
from app.modules.messaging.application import message_service as messaging_read
from app.modules.onboarding.application import onboarding_read_facade
from app.modules.opportunities.application import job_alert_service, job_read_facade
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.modules.recruitment.application import offer_service
from app.modules.student_profiles.application import affiliation_facade
from app.modules.users.application import user_read_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal

# Affiliations that represent a student who benefits from verifying — a general
# working professional is not nagged to verify a student status they don't hold.
_VERIFIABLE_AFFILIATIONS = frozenset(
    {
        affiliation_facade.AFFILIATION_VINUNI_STUDENT,
        affiliation_facade.AFFILIATION_EXTERNAL,
    }
)


def _require_student(principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.STUDENT:
        raise PermissionDeniedError()


async def _resolve_affiliation(
    session: AsyncSession, *, principal: Principal, user_id
) -> dict:
    """Resolve the student's affiliation badge for the dashboard (verified fact when
    present, else a provisional label from login email + onboarding seeker type)."""

    email = await user_read_facade.get_email(session, user_id)
    seeker_type = await onboarding_read_facade.get_seeker_type(
        session, user_id=user_id
    )
    return await affiliation_facade.resolve_display(
        session,
        user_id=user_id,
        login_email=email,
        seeker_type=seeker_type,
        persona=principal.persona,
    )


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
    actionable_offers = await safe(
        session,
        lambda: offer_service.count_actionable_offers_for_student(
            session, user_id=user_id
        ),
        fallback=0,
    )
    interviews_awaiting = await safe(
        session,
        lambda: recruitment_read.count_interviews_awaiting_response(
            session, user_id=user_id
        ),
        fallback=0,
    )
    unread_messages = await safe(
        session,
        lambda: messaging_read.unread_count(session, principal=principal),
        fallback=0,
    )
    # Persona-aware verify-account prompt: only nudge a still-unverified student
    # (VinUni / external), never a general working professional. The affiliation is
    # the verified fact when present, else a provisional label from login email +
    # onboarding seeker type.
    affiliation_info = await safe(
        session,
        lambda: _resolve_affiliation(session, principal=principal, user_id=user_id),
        fallback={"affiliation": affiliation_facade.AFFILIATION_GENERAL, "verified": True},
    )

    metrics = {
        "applications_total": counts["total"],
        "applications_active": counts["active"],
        "cv_count": cv_count,
        "alert_count": alert_count,
        "unread_messages": unread_messages,
        # Surfaced so the frontend can render a persona badge + verified check.
        "affiliation": affiliation_info["affiliation"],
        "verified": affiliation_info["verified"],
    }

    # Ordered by urgency: time-sensitive responses first, setup nudges last. Each
    # todo is real (backed by a live count/flag) — never a decorative placeholder.
    next_actions: list[dict] = []
    if actionable_offers > 0:
        next_actions.append(
            {
                "key": "respond_offer",
                "href": "/student/applications",
                "count": actionable_offers,
            }
        )
    if interviews_awaiting > 0:
        next_actions.append(
            {
                "key": "respond_interview",
                "href": "/student/applications",
                "count": interviews_awaiting,
            }
        )
    if pending_reveals > 0:
        next_actions.append(
            {
                "key": "respond_reveal",
                "href": "/student/applications",
                "count": pending_reveals,
            }
        )
    if (
        not affiliation_info["verified"]
        and affiliation_info["affiliation"] in _VERIFIABLE_AFFILIATIONS
    ):
        next_actions.append(
            {
                "key": "verify_account",
                "href": "/onboarding/student-verify",
                "count": None,
            }
        )
    if unread_messages > 0:
        next_actions.append(
            {
                "key": "unread_messages",
                "href": "/student/messages",
                "count": unread_messages,
            }
        )
    if cv_count == 0:
        next_actions.append(
            {"key": "build_cv", "href": "/student/cv", "count": None}
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
