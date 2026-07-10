"""Own-org events export rows (assistant ``export_events`` tool).

Aggregate-only by design: each row is the event plus ATTENDEE COUNTS (confirmed
registrations, waitlist, attended check-ins) — never a registrant identity,
email, or any other attendee PII. RBAC: ``events:export`` at org scope, enforced
here in the application layer. Org-scoped to ``principal.org_id`` only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import event_lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "events"
MAX_EXPORT_ROWS = 5000


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


async def export_event_rows(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    """All of the caller org's events as flat export rows (newest first, capped).

    ``status`` matches the raw code OR the localized label, case-insensitively.
    Attendee data is aggregate counts only (no PII, ever).
    """

    org_id = principal.org_id
    permission_checker.require(principal, _RESOURCE, "export", resource_org_id=org_id)
    if org_id is None:
        return []

    stmt = (
        select(Event)
        .where(Event.org_id == org_id, Event.deleted_at.is_(None))
        .order_by(Event.starts_at.desc(), Event.id.desc())
        .limit(MAX_EXPORT_ROWS)
    )
    events = list((await session.execute(stmt)).scalars().all())

    status_q = (status or "").strip().lower()
    if status_q:
        events = [
            e
            for e in events
            if status_q in e.status.lower()
            or status_q in event_lifecycle.status_label(e.status, locale=locale).lower()
        ]

    # ONE grouped aggregate over registrations for the whole page (no N+1, no PII).
    counts: dict[tuple[uuid.UUID, str], int] = {}
    if events:
        rows = (
            await session.execute(
                select(
                    EventRegistration.event_id,
                    EventRegistration.status,
                    func.count(EventRegistration.id),
                )
                .where(EventRegistration.event_id.in_([e.id for e in events]))
                .group_by(EventRegistration.event_id, EventRegistration.status)
            )
        ).all()
        counts = {(event_id, st): int(n) for event_id, st, n in rows}

    def _count(event_id: uuid.UUID, *statuses: str) -> int:
        return sum(counts.get((event_id, st), 0) for st in statuses)

    return [
        {
            "title": e.title,
            "event_type": event_lifecycle.event_type_label(e.event_type, locale=locale),
            "format": event_lifecycle.format_label(e.format, locale=locale),
            "status": event_lifecycle.status_label(e.status, locale=locale),
            "starts_at": _iso(e.starts_at),
            "ends_at": _iso(e.ends_at),
            "capacity": e.capacity if e.capacity is not None else "",
            # Aggregate attendee signals only — never a registrant identity.
            "registered": _count(e.id, "confirmed", "attended"),
            "waitlisted": _count(e.id, "waitlisted"),
            "attended": _count(e.id, "attended"),
            "created_at": _iso(e.created_at),
        }
        for e in events
    ]
