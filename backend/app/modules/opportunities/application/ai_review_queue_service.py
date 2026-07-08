"""AI human-review queue read-model + human-decision facade (B-579).

AI/rule flagging is ADVISORY. When a job or event is FLAGGED
(``moderation_status = 'flagged'`` + a structured ``moderation_reason_code``),
this facade surfaces it as a dedicated *human*-review queue and lets a university
moderator take the FINAL say: UPHOLD the flag (reject the item) or DISMISS it
(clear the flag). No model confidence / provider / model / token internal ever
leaves this layer — a flagged item carries only a user-safe reason LABEL.

Read-model, not a live multi-domain join: it reads the ``opportunities`` module's
own ``jobs`` + ``events`` tables (two small, indexed ``moderation_status``
filters) and merges them in memory. The decision actions REUSE the existing
``moderation_service`` / ``event_moderation_service`` transitions — no transition
logic is duplicated here.

RBAC (grant-gated in the service layer): a platform superadmin, or a member of a
UNIVERSITY org holding ``jobs:moderate`` and/or ``events:moderate``. The queue is
scoped by grant — a jobs-only moderator sees (and can act on) only flagged jobs,
never events, and vice-versa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.application import (
    event_moderation_service,
    moderation_service,
)
from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.shared.moderation import compute_due_by, queue_age_fields, reason_code_label
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

ITEM_TYPE_JOB = "job"
ITEM_TYPE_EVENT = "event"
ITEM_TYPES: frozenset[str] = frozenset({ITEM_TYPE_JOB, ITEM_TYPE_EVENT})


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _sla_hours() -> int:
    return get_settings().ai_review_moderation_sla_hours


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# RBAC: grant-gated to university moderators, scoped per item type            #
# --------------------------------------------------------------------------- #


async def _permitted_types(session: AsyncSession, principal: Principal) -> set[str]:
    """Item types the caller may see/act on in the AI review queue.

    Superadmin -> both. A university-org member -> whichever of ``job`` / ``event``
    they hold ``:moderate`` for. Neither grant (or a non-university org) -> denied,
    exactly like the per-type moderation services (partners can never moderate).
    """

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return {ITEM_TYPE_JOB, ITEM_TYPE_EVENT}

    can_jobs = permission_checker.can(principal, "jobs", "moderate")
    can_events = permission_checker.can(principal, "events", "moderate")
    if not (can_jobs or can_events):
        raise PermissionDeniedError(details={"reason": "moderation_grant_required"})
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})

    permitted: set[str] = set()
    if can_jobs:
        permitted.add(ITEM_TYPE_JOB)
    if can_events:
        permitted.add(ITEM_TYPE_EVENT)
    return permitted


# --------------------------------------------------------------------------- #
# Presenters (user-safe: reason LABELS only, never model internals)           #
# --------------------------------------------------------------------------- #


def _present_job(job: Job, *, locale: str, now: datetime) -> dict:
    anchor = job.moderation_flagged_at or job.updated_at
    due_by = compute_due_by(anchor, sla_hours=_sla_hours()) if anchor else None
    return {
        "item_type": ITEM_TYPE_JOB,
        "id": str(job.id),
        "title": job.title,
        "org_id": str(job.org_id),
        "status": job.status,
        "status_label": lifecycle.status_label(job.status, locale=locale),
        "moderation_status": job.moderation_status,
        "moderation_status_label": lifecycle.moderation_label(
            job.moderation_status, locale=locale
        ),
        # User-safe flag reason — the structured moderation reason code + its
        # localized label. No raw model confidence / provider / model / token.
        "flag_reason_code": job.moderation_reason_code,
        "flag_reason_label": reason_code_label(
            job.moderation_reason_code, locale=locale
        ),
        "flag_note": job.moderation_note,
        "flagged_at": _iso(job.moderation_flagged_at),
        "submitted_at": _iso(job.submitted_at),
        "created_at": _iso(job.created_at),
        # Whether a human moderator has engaged with the item (claimed it). An
        # upheld/dismissed item leaves the queue, so queued rows are undecided.
        "human_acted": job.claimed_by is not None,
        "claimed_at": _iso(job.claimed_at),
        "detail_url": f"/university/moderation/jobs/{job.id}",
        **queue_age_fields(submitted_at=anchor, due_by=due_by, now=now),
    }


def _present_event(event: Event, *, locale: str, now: datetime) -> dict:
    anchor = event.moderation_flagged_at or event.updated_at
    due_by = compute_due_by(anchor, sla_hours=_sla_hours()) if anchor else None
    return {
        "item_type": ITEM_TYPE_EVENT,
        "id": str(event.id),
        "title": event.title,
        "org_id": str(event.org_id),
        "status": event.status,
        "status_label": event_lifecycle.status_label(event.status, locale=locale),
        "moderation_status": event.moderation_status,
        "moderation_status_label": event_lifecycle.moderation_label(
            event.moderation_status, locale=locale
        ),
        "flag_reason_code": event.moderation_reason_code,
        "flag_reason_label": reason_code_label(
            event.moderation_reason_code, locale=locale
        ),
        "flag_note": event.moderation_note,
        "flagged_at": _iso(event.moderation_flagged_at),
        "submitted_at": _iso(event.submitted_at),
        "created_at": _iso(event.created_at),
        "human_acted": event.claimed_by is not None,
        "claimed_at": _iso(event.claimed_at),
        "detail_url": f"/university/moderation/events/{event.id}",
        **queue_age_fields(submitted_at=anchor, due_by=due_by, now=now),
    }


# --------------------------------------------------------------------------- #
# Read model: list + aggregate counts (queue badge)                          #
# --------------------------------------------------------------------------- #


async def _count_flagged_jobs(session: AsyncSession) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.deleted_at.is_(None), Job.moderation_status == lifecycle.MOD_FLAGGED)
        )
    ).scalar_one()


async def _count_flagged_events(session: AsyncSession) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Event)
            .where(
                Event.deleted_at.is_(None),
                Event.moderation_status == event_lifecycle.MOD_FLAGGED,
            )
        )
    ).scalar_one()


async def get_counts(
    session: AsyncSession, *, principal: Principal
) -> dict[str, int]:
    """Aggregate flagged-item counts for a queue badge (grant-scoped)."""

    permitted = await _permitted_types(session, principal)
    jobs = await _count_flagged_jobs(session) if ITEM_TYPE_JOB in permitted else 0
    events = await _count_flagged_events(session) if ITEM_TYPE_EVENT in permitted else 0
    return {"job": jobs, "event": events, "total": jobs + events}


async def list_queue(
    session: AsyncSession,
    *,
    principal: Principal,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], dict[str, int]]:
    """List flagged jobs + events for human review, oldest-flag first.

    Returns ``(items, counts)`` where ``counts`` is the grant-scoped aggregate for
    a queue badge. ``items`` is merged across permitted types and ordered by
    flag age (oldest / most SLA-pressured first).
    """

    permitted = await _permitted_types(session, principal)
    page_limit = clamp_limit(limit)
    now = _now()
    items: list[dict] = []
    job_count = 0
    event_count = 0

    if ITEM_TYPE_JOB in permitted:
        job_count = await _count_flagged_jobs(session)
        rows = list(
            (
                await session.execute(
                    select(Job)
                    .where(
                        Job.deleted_at.is_(None),
                        Job.moderation_status == lifecycle.MOD_FLAGGED,
                    )
                    .order_by(
                        Job.moderation_flagged_at.asc().nulls_last(),
                        Job.created_at.asc(),
                    )
                    .limit(page_limit)
                )
            )
            .scalars()
            .all()
        )
        items.extend(_present_job(j, locale=locale, now=now) for j in rows)

    if ITEM_TYPE_EVENT in permitted:
        event_count = await _count_flagged_events(session)
        rows_e = list(
            (
                await session.execute(
                    select(Event)
                    .where(
                        Event.deleted_at.is_(None),
                        Event.moderation_status == event_lifecycle.MOD_FLAGGED,
                    )
                    .order_by(
                        Event.moderation_flagged_at.asc().nulls_last(),
                        Event.created_at.asc(),
                    )
                    .limit(page_limit)
                )
            )
            .scalars()
            .all()
        )
        items.extend(_present_event(e, locale=locale, now=now) for e in rows_e)

    # Merge across types: oldest flag first (empty anchor sorts last).
    items.sort(key=lambda it: (it.get("flagged_at") is None, it.get("flagged_at") or ""))
    items = items[:page_limit]
    counts = {"job": job_count, "event": event_count, "total": job_count + event_count}
    return items, counts


# --------------------------------------------------------------------------- #
# Human decisions: uphold (reject) / dismiss (clear) — reuse transitions      #
# --------------------------------------------------------------------------- #


def _require_known_type(item_type: str, permitted: set[str]) -> str:
    normalized = (item_type or "").strip().lower()
    if normalized not in ITEM_TYPES:
        raise ValidationFailedError(details={"item_type": "unknown_type"})
    if normalized not in permitted:
        raise PermissionDeniedError(details={"reason": "moderation_grant_required"})
    return normalized


async def uphold(
    session: AsyncSession,
    *,
    principal: Principal,
    item_type: str,
    item_id: uuid.UUID,
    reason: str,
    reason_code: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Human UPHOLDS the flag -> reject the item (final say). Audited."""

    permitted = await _permitted_types(session, principal)
    kind = _require_known_type(item_type, permitted)
    if kind == ITEM_TYPE_JOB:
        item = await moderation_service.uphold_flag(
            session, principal=principal, job_id=item_id, reason=reason,
            reason_code=reason_code, ctx=ctx, locale=locale,
        )
    else:
        item = await event_moderation_service.uphold_flag_event(
            session, principal=principal, event_id=item_id, reason=reason,
            reason_code=reason_code, ctx=ctx, locale=locale,
        )
    return {"item_type": kind, "decision": "uphold", "item": item}


async def dismiss(
    session: AsyncSession,
    *,
    principal: Principal,
    item_type: str,
    item_id: uuid.UUID,
    reason: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Human DISMISSES the flag -> clear it, returning the item to review. Audited."""

    permitted = await _permitted_types(session, principal)
    kind = _require_known_type(item_type, permitted)
    if kind == ITEM_TYPE_JOB:
        item = await moderation_service.clear_flag(
            session, principal=principal, job_id=item_id, reason=reason,
            ctx=ctx, locale=locale,
        )
    else:
        item = await event_moderation_service.clear_flag_event(
            session, principal=principal, event_id=item_id, reason=reason,
            ctx=ctx, locale=locale,
        )
    return {"item_type": kind, "decision": "dismiss", "item": item}
