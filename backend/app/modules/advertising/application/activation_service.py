"""Activation / completion / flag-recompute — the single source shared by the
scheduler sweeps **and** the inline callers (ADR-0009 §4/§6).

The placement is the source of truth; the ``jobs/events`` flag is a projection
recomputed from **active** placements via the one ``opportunities.sponsorship_facade``
setter. Every recompute is therefore correct for overlapping placements:
``is_sponsored`` (resp. ``is_featured``) stays ON while *any* active placement still
covers the target, and only turns OFF when the last one completes/cancels.

All sweeps are status/time-gated and idempotent: a re-tick is a no-op. They are
**flush-only** — the scheduler job (or the calling service) owns the commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import notify
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import SponsoredPlacement
from app.modules.opportunities.application import sponsorship_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.permissions import Principal

# Notify the partner T-24h before a live placement's window closes.
_ENDING_WINDOW = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(actor: Principal | None, placement: SponsoredPlacement) -> AuditContext:
    return AuditContext(
        actor_id=actor.user_id if actor else None,
        actor_org_id=actor.org_id if actor else placement.org_id,
    )


# --------------------------------------------------------------------------- #
# Flag recompute (the load-bearing piece)                                     #
# --------------------------------------------------------------------------- #


async def recompute_target_flags(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    actor: Principal | None = None,
    reason: str = "advertising_recompute",
) -> bool:
    """Recompute + push the target's flags from its currently-ACTIVE placements.

    ``EXISTS active placement covering target`` per flag — so two concurrent
    placements (e.g. a ``featured`` and a ``sponsored``, or a renewal overlapping
    an expiry) are correct by construction. Returns whether a flag changed.
    """

    rows = (
        await session.execute(
            select(SponsoredPlacement.placement_type).where(
                SponsoredPlacement.target_type == target_type,
                SponsoredPlacement.target_id == target_id,
                SponsoredPlacement.status == lifecycle.ACTIVE,
                SponsoredPlacement.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    is_sponsored, is_featured = lifecycle.compute_target_flags(list(rows))
    return await sponsorship_facade.set_target_flags(
        session,
        target_type=target_type,
        target_id=target_id,
        is_sponsored=is_sponsored,
        is_featured=is_featured,
        actor=actor,
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# Inline activation (called by placement / moderation services)               #
# --------------------------------------------------------------------------- #


async def try_activate_inline(
    session: AsyncSession,
    *,
    placement: SponsoredPlacement,
    now: datetime | None = None,
    actor: Principal | None = None,
) -> bool:
    """Activate ``placement`` immediately if it is approved+paid+in-window.

    Used by ``approve``/``mark_paid`` so a placement whose window is already open
    goes live instantly (no up-to-5-min sweep lag). No-op (returns ``False``)
    otherwise. The caller owns the commit.
    """

    now = now or _now()
    if not lifecycle.can_activate(
        status=placement.status,
        paid_at=placement.paid_at,
        start_at=_aware(placement.start_at),
        end_at=_aware(placement.end_at),
        now=now,
    ):
        return False
    await _activate(session, placement, now=now, actor=actor)
    return True


async def _activate(
    session: AsyncSession,
    placement: SponsoredPlacement,
    *,
    now: datetime,
    actor: Principal | None,
) -> None:
    placement.status = lifecycle.ACTIVE
    placement.activated_at = now
    placement.version += 1
    await session.flush()
    await write_audit(
        session, action="advertising.placement_activated",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(actor, placement),
        after={"status": placement.status, "org_id": str(placement.org_id),
               "target_type": placement.target_type,
               "target_id": str(placement.target_id)},
    )
    await recompute_target_flags(
        session, target_type=placement.target_type, target_id=placement.target_id,
        actor=actor, reason="placement_activated",
    )
    await notify.notify_partner(
        session, placement=placement, template_key="advertising.live",
    )


async def _complete(
    session: AsyncSession,
    placement: SponsoredPlacement,
    *,
    now: datetime,
    actor: Principal | None,
) -> None:
    placement.status = lifecycle.COMPLETED
    placement.completed_at = now
    placement.version += 1
    await session.flush()
    await write_audit(
        session, action="advertising.placement_completed",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(actor, placement),
        after={"status": placement.status, "org_id": str(placement.org_id),
               "target_type": placement.target_type,
               "target_id": str(placement.target_id)},
    )
    # Recompute AFTER the status flip so this just-completed placement is excluded;
    # the flag stays ON only if ANOTHER active placement still covers the target.
    await recompute_target_flags(
        session, target_type=placement.target_type, target_id=placement.target_id,
        actor=actor, reason="placement_completed",
    )


# --------------------------------------------------------------------------- #
# Scheduler sweeps                                                            #
# --------------------------------------------------------------------------- #


def _aware(dt: datetime) -> datetime:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparison."""

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def activation_sweep(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Activate every approved+paid placement whose window has opened.

    ``status=approved AND paid_at IS NOT NULL AND start_at <= now < end_at`` ->
    ``active`` + recompute flags ON. Status/paid/window-gated + idempotent.
    Flush-only — the scheduler job owns the commit.
    """

    now = now or _now()
    rows = (
        await session.execute(
            select(SponsoredPlacement).where(
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.status == lifecycle.APPROVED,
                SponsoredPlacement.paid_at.isnot(None),
                SponsoredPlacement.start_at <= now,
                SponsoredPlacement.end_at > now,
            )
        )
    ).scalars().all()
    count = 0
    for placement in rows:
        # Defensive re-check against the (possibly naive) stored window bounds.
        if lifecycle.can_activate(
            status=placement.status, paid_at=placement.paid_at,
            start_at=_aware(placement.start_at), end_at=_aware(placement.end_at),
            now=now,
        ):
            await _activate(session, placement, now=now, actor=None)
            count += 1
    await session.flush()
    return {"activated": count}


async def completion_sweep(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Complete every active/approved placement whose window has closed + warn
    of imminent endings.

    ``status IN (active, approved) AND end_at <= now`` -> ``completed`` + recompute
    flags (OFF unless another active placement still covers the target). Also
    enqueues a deduped ``advertising.ending`` notice for active placements ending
    within the next 24h. Status/end_at-gated + idempotent. Flush-only.
    """

    now = now or _now()
    ending = list(
        (
            await session.execute(
                select(SponsoredPlacement).where(
                    SponsoredPlacement.deleted_at.is_(None),
                    SponsoredPlacement.status.in_(
                        [lifecycle.ACTIVE, lifecycle.APPROVED]
                    ),
                    SponsoredPlacement.end_at <= now,
                )
            )
        ).scalars().all()
    )
    completed = 0
    for placement in ending:
        if _aware(placement.end_at) <= now:
            await _complete(session, placement, now=now, actor=None)
            completed += 1

    # T-24h "ending soon" notice (active only; deduped on ending_notified_at).
    soon = (
        await session.execute(
            select(SponsoredPlacement).where(
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.status == lifecycle.ACTIVE,
                SponsoredPlacement.end_at > now,
                SponsoredPlacement.end_at <= now + _ENDING_WINDOW,
                SponsoredPlacement.ending_notified_at.is_(None),
            )
        )
    ).scalars().all()
    notified = 0
    for placement in soon:
        placement.ending_notified_at = now
        placement.version += 1
        await notify.notify_partner(
            session, placement=placement, template_key="advertising.ending",
        )
        notified += 1

    await session.flush()
    return {"completed": completed, "ending_notices": notified}


async def flag_reconcile(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Recompute flags for every target that has >= 1 placement (drift guard).

    Pure recompute; idempotent. Self-heals manual/seed drift. Targets with no
    placement row are left untouched (transitional). Flush-only.
    """

    targets = (
        await session.execute(
            select(
                SponsoredPlacement.target_type, SponsoredPlacement.target_id
            )
            .where(SponsoredPlacement.deleted_at.is_(None))
            .distinct()
        )
    ).all()
    changed = 0
    for target_type, target_id in targets:
        if await recompute_target_flags(
            session, target_type=target_type, target_id=target_id,
            reason="flag_reconcile",
        ):
            changed += 1
    await session.flush()
    return {"reconciled_targets": len(targets), "changed": changed}
