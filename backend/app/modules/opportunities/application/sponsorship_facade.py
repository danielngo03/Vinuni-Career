"""Sponsorship facade — the **sole production writer** of the sponsored/featured
flags on ``jobs``/``events`` (ADR-0009 §4).

Cross-module law (ARCHITECTURE §8): ``advertising`` owns placements; ``opportunities``
owns the ``jobs``/``events`` flag columns. The dependency is **one-way**
``advertising → opportunities`` through this thin facade — ``opportunities`` never
imports ``advertising``. ``advertising`` *computes* the desired booleans from its
own active placements and *calls* :func:`set_target_flags`; this module loads the
target ``FOR UPDATE``, sets the two booleans, bumps ``version``, and writes the
audit row. ``opportunities`` therefore stays the owner+auditor of its columns while
``advertising`` is the decider.

:func:`load_target` lets ``advertising`` validate target ownership at placement
create time without deep-importing the ``Job``/``Event`` ORM — it returns a small,
PII-free descriptor (or ``None`` for missing/soft-deleted), so a cross-org or
unknown target maps to a ``404`` in the caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.shared.audit import AuditContext, write_audit
from app.shared.permissions import Principal

_JOB = "job"
_EVENT = "event"


@dataclass(frozen=True, slots=True)
class TargetRef:
    """A PII-free descriptor of a sponsorship target (a job or an event)."""

    target_type: str
    target_id: uuid.UUID
    org_id: uuid.UUID
    title: str
    is_sponsored: bool
    is_featured: bool


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def _load_row(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    lock: bool = False,
) -> Job | Event | None:
    """Load the concrete ``Job``/``Event`` ORM row (or ``None``).

    Branches on ``target_type`` with concrete model types so the two boolean
    columns + ``version`` stay typed; the polymorphic ``target_id`` has no DB FK.
    """

    if target_type == _JOB:
        job_stmt = select(Job).where(Job.id == target_id, Job.deleted_at.is_(None))
        if lock and _use_for_update():
            job_stmt = job_stmt.with_for_update()
        return (await session.execute(job_stmt)).scalar_one_or_none()
    if target_type == _EVENT:
        event_stmt = select(Event).where(Event.id == target_id, Event.deleted_at.is_(None))
        if lock and _use_for_update():
            event_stmt = event_stmt.with_for_update()
        return (await session.execute(event_stmt)).scalar_one_or_none()
    raise ValueError(f"unknown target_type: {target_type}")


async def load_target(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    lock: bool = False,
) -> TargetRef | None:
    """Load a non-deleted ``job``/``event`` as a :class:`TargetRef`, else ``None``.

    Ownership is *not* checked here — the caller compares ``ref.org_id`` to the
    acting org and maps a mismatch to ``404`` (enumeration hiding). Returns ``None``
    for a missing or soft-deleted target.
    """

    row = await _load_row(session, target_type=target_type, target_id=target_id, lock=lock)
    if row is None:
        return None
    return TargetRef(
        target_type=target_type,
        target_id=row.id,
        org_id=row.org_id,
        title=row.title,
        is_sponsored=row.is_sponsored,
        is_featured=row.is_featured,
    )


async def set_target_flags(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    is_sponsored: bool,
    is_featured: bool,
    actor: Principal | None = None,
    reason: str = "advertising_recompute",
) -> bool:
    """Set ``is_sponsored``/``is_featured`` on one target; audit + bump version.

    Loads the row ``FOR UPDATE`` (Postgres), applies the two booleans, and — only
    when something actually changed — bumps ``version`` and writes a
    ``job.sponsorship_changed`` / ``event.sponsorship_changed`` audit row (the flag
    flip is itself an audited write). A no-op recompute (flags already match) writes
    no audit row and does not bump ``version``, so re-running a sweep is idempotent.
    Returns ``True`` when a change was applied. Flush-only — the caller owns the
    commit (so the placement transition and the flag flip commit atomically).
    """

    row = await _load_row(session, target_type=target_type, target_id=target_id, lock=True)
    if row is None:
        return False
    if row.is_sponsored == is_sponsored and row.is_featured == is_featured:
        return False

    row.is_sponsored = is_sponsored
    row.is_featured = is_featured
    row.version += 1
    await session.flush()

    await write_audit(
        session,
        action=f"{target_type}.sponsorship_changed",
        resource_type=target_type,
        resource_id=row.id,
        context=AuditContext(
            actor_id=actor.user_id if actor else None,
            actor_org_id=actor.org_id if actor else row.org_id,
        ),
        after={
            "is_sponsored": is_sponsored,
            "is_featured": is_featured,
            "reason": reason,
        },
    )
    return True
