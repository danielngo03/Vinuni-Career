"""University Operations command-center read model.

``GET /dashboards/university/operations`` — the single operational surface a
university staffer opens to run the platform: every moderation/approval queue's
SLA health in one place, the SLA-breach roll-up, the moderation-risk mix, who is
carrying the workload, the upcoming-events glance, and a breach-first list of
actionable tasks.

RBAC mirrors :func:`university_dashboard._require_university` (superadmin, or a
member of a **university** org holding ``jobs:moderate``). The scope is
platform-wide by design — this is the governance surface, not a tenant view.

Every widget runs through :func:`_common.safe`, so one failing sub-query degrades
to an empty/zero widget instead of 500-ing the whole page. The gate runs first,
outside ``safe``, so a 401/403 is never swallowed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import ops_queue_read as ads_read
from app.modules.dashboards.application._common import empty_rows, safe
from app.modules.dashboards.application.university_dashboard import _require_university
from app.modules.moderation.application import ops_queue_read as review_read
from app.modules.opportunities.application import ops_queue_read as opp_read
from app.modules.organization.application import ops_queue_read as org_read
from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_read_facade
from app.shared.moderation import HEALTH_ON_TRACK
from app.shared.permissions import Principal

# Queue key -> operator-facing frontend route (locale prefix added client-side).
_QUEUE_HREFS: dict[str, str] = {
    "jobs": "/university/moderation/jobs",
    "events": "/university/moderation/events",
    "ads": "/university/advertising",
    "partner_registrations": "/university/partners",
    "ai_review": "/university/abuse",
}


def _empty_stats() -> dict:
    return {
        "pending": 0,
        "overdue": 0,
        "due_soon": 0,
        "oldest_age_hours": None,
        "sla_hours": None,
        "next_due_at": None,
        "health": HEALTH_ON_TRACK,
    }


async def get_university_operations(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    await _require_university(session, principal)
    now = datetime.now(tz=UTC)

    # --- per-queue SLA stats -------------------------------------------------
    jobs = await safe(
        session, lambda: opp_read.job_queue_stats(session, now=now), fallback=_empty_stats()
    )
    events = await safe(
        session, lambda: opp_read.event_queue_stats(session, now=now), fallback=_empty_stats()
    )
    ads = await safe(
        session, lambda: ads_read.ad_queue_stats(session, now=now), fallback=_empty_stats()
    )
    partners = await safe(
        session,
        lambda: org_read.partner_registration_stats(session, now=now),
        fallback=_empty_stats(),
    )
    ai_review = await safe(
        session, lambda: review_read.ai_review_stats(session, now=now), fallback=_empty_stats()
    )

    queues = [
        {"key": key, "href": _QUEUE_HREFS[key], **stats}
        for key, stats in (
            ("jobs", jobs),
            ("events", events),
            ("ads", ads),
            ("partner_registrations", partners),
            ("ai_review", ai_review),
        )
    ]

    # --- SLA roll-up ---------------------------------------------------------
    total_pending = sum(q["pending"] for q in queues)
    total_overdue = sum(q["overdue"] for q in queues)
    total_due_soon = sum(q["due_soon"] for q in queues)
    breach_rate = round(total_overdue / total_pending, 3) if total_pending else 0.0
    sla = {
        "total_pending": total_pending,
        "total_overdue": total_overdue,
        "total_due_soon": total_due_soon,
        "breach_rate": breach_rate,
    }

    # --- moderation risk mix -------------------------------------------------
    severity = await safe(
        session,
        lambda: review_read.severity_mix(session),
        fallback={"high": 0, "medium": 0, "low": 0},
    )
    flagged = await safe(
        session,
        lambda: opp_read.flagged_risk_counts(session),
        fallback={"jobs_flagged": 0, "events_flagged": 0},
    )
    risk = {
        "high": severity["high"],
        "medium": severity["medium"],
        "low": severity["low"],
        "flagged_listings": flagged["jobs_flagged"] + flagged["events_flagged"],
    }

    # --- workload (by moderator + by department + unassigned) ----------------
    workload = await safe(
        session,
        lambda: _build_workload(session, principal=principal),
        fallback={"by_moderator": empty_rows(), "by_department": empty_rows(), "unassigned": 0},
    )

    # --- upcoming events -----------------------------------------------------
    upcoming = await safe(
        session,
        lambda: opp_read.upcoming_events(session, now=now, limit=5),
        fallback=empty_rows(),
    )

    # --- actionable tasks (breach-first) -------------------------------------
    tasks = _actionable_tasks(queues)

    return {
        "generated_at": now.isoformat(),
        "queues": queues,
        "sla": sla,
        "risk": risk,
        "workload": workload,
        "upcoming_events": upcoming,
        "actionable_tasks": tasks,
    }


async def _build_workload(session: AsyncSession, *, principal: Principal) -> dict:
    """Aggregate claimed pending items across content queues into a workload view.

    Sums per-moderator claim counts from jobs/events/ads; resolves display names;
    and, when the acting principal is a university staffer (has an ``org_id``),
    resolves each moderator's primary department for the department roll-up.
    Superadmins (no single org) get the by-moderator view without departments.
    """

    counts: dict[uuid.UUID | None, int] = {}
    for rows in (
        await opp_read.pending_claimant_counts(session),
        await ads_read.pending_claimant_counts(session),
    ):
        for claimant, count in rows:
            counts[claimant] = counts.get(claimant, 0) + count

    unassigned = counts.pop(None, 0)
    moderator_ids: list[uuid.UUID] = [uid for uid in counts if uid is not None]

    names = (
        await user_read_facade.get_full_names(session, moderator_ids) if moderator_ids else {}
    )
    departments: dict[uuid.UUID, str] = {}
    if moderator_ids and principal.org_id is not None:
        departments = await org_reporting_facade.primary_department_names_for_users(
            session, org_id=principal.org_id, user_ids=moderator_ids
        )

    # Sort typed tuples (int count key), then materialise the payload dicts.
    ranked: list[tuple[uuid.UUID, str, str | None, int]] = sorted(
        (
            (uid, names.get(uid) or "—", departments.get(uid), counts[uid])
            for uid in moderator_ids
        ),
        key=lambda r: r[3],
        reverse=True,
    )
    by_moderator = [
        {"moderator_id": str(uid), "name": name, "department": dept, "count": count}
        for uid, name, dept, count in ranked
    ]

    dept_totals: dict[str, int] = {}
    for _uid, _name, dept, count in ranked:
        label = dept or "unassigned"
        dept_totals[label] = dept_totals.get(label, 0) + count
    by_department = [
        {"department": name, "count": count}
        for name, count in sorted(dept_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "by_moderator": by_moderator,
        "by_department": by_department,
        "unassigned": unassigned,
    }


def _actionable_tasks(queues: list[dict]) -> list[dict]:
    """One task per non-empty queue, sorted breach-first then age.

    Priority: any overdue item outranks amber, which outranks plain pending. Ties
    break on overdue count, then total pending, then oldest age.
    """

    tasks: list[dict] = []
    for q in queues:
        if q["pending"] <= 0:
            continue
        if q["overdue"] > 0:
            priority = "breach"
        elif q["due_soon"] > 0:
            priority = "due_soon"
        else:
            priority = "normal"
        tasks.append(
            {
                "queue": q["key"],
                "href": q["href"],
                "pending": q["pending"],
                "overdue": q["overdue"],
                "due_soon": q["due_soon"],
                "priority": priority,
                "oldest_age_hours": q["oldest_age_hours"],
            }
        )

    _rank = {"breach": 0, "due_soon": 1, "normal": 2}
    tasks.sort(
        key=lambda t: (
            _rank[t["priority"]],
            -t["overdue"],
            -t["pending"],
            -(t["oldest_age_hours"] or 0),
        )
    )
    return tasks
