"""Ops command-center queue counts for opportunities (jobs + events moderation).

Application-layer read seam consumed by the university ops command-center read
model (:mod:`app.modules.dashboards.application.ops_read`). RBAC-free by design —
the ops read-model owns the university gate before it calls any facade here,
exactly like :mod:`dashboard_read` / :mod:`public_read`. Returns only light
``{"open": int, "overdue": int}`` COUNTs, never rows or PII.

Overdue uses the stored ``due_by`` SLA deadline (set at submit by
``job_write_service`` / ``event_service`` from ``app.shared.moderation``), so
jobs/events do not re-derive the window from ``created_at`` here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application import dashboard_read
from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.shared.moderation import QUEUE_EVENT, QUEUE_JOB_POSTING


async def queue_counts(session: AsyncSession, *, kind: str, now: datetime) -> dict[str, int]:
    """Open + overdue counts for one opportunities moderation queue ``kind``."""

    if kind == QUEUE_JOB_POSTING:
        # Reuse the existing pending-jobs count for the "open" figure.
        open_count = int(await dashboard_read.count_pending_moderation_jobs(session))
        overdue_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.deleted_at.is_(None),
                        Job.status == lifecycle.PENDING_REVIEW,
                        Job.due_by < now,
                    )
                )
            ).scalar_one()
        )
        return {"open": open_count, "overdue": overdue_count}

    if kind == QUEUE_EVENT:
        open_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Event)
                    .where(
                        Event.deleted_at.is_(None),
                        Event.status == event_lifecycle.PENDING_REVIEW,
                    )
                )
            ).scalar_one()
        )
        overdue_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(Event)
                    .where(
                        Event.deleted_at.is_(None),
                        Event.status == event_lifecycle.PENDING_REVIEW,
                        Event.due_by < now,
                    )
                )
            ).scalar_one()
        )
        return {"open": open_count, "overdue": overdue_count}

    raise ValueError(f"unknown opportunities queue kind: {kind}")
