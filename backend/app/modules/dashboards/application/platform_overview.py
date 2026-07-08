"""Superadmin platform read model — ``GET /admin/overview``.

Composes existing per-domain read models into one landing payload:
- ``ai``                 : AI ops health from ``ai_ops_read_service.overview``.
- ``outbox``             : Notification outbox health from ``dispatch_service``.
- ``moderation_pending`` : Jobs awaiting university moderation (int).
- ``active_users``       : Platform-wide identity count (int).

Each sub-section is wrapped in :func:`safe` so one failing sub-query returns a
safe fallback (``{}`` / ``0``) instead of raising — the envelope is always
well-formed.

RBAC is enforced by the caller (the router dependency ``require_superadmin``)
BEFORE any ``safe`` call, so 401/403 are never swallowed here.

Design notes:
- No heavy live multi-domain joins; every number comes from an existing indexed
  application-layer facade or read model.
- Provider/model identity is never leaked in the response (the ``ai`` section
  comes from ``ai_ops_read_service.overview`` which never includes raw
  provider/model fields in its output).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_ops.application import ai_ops_read_service
from app.modules.dashboards.application._common import safe
from app.modules.notifications.application import dispatch_service
from app.modules.opportunities.application import dashboard_read as opportunities_read
from app.modules.users.application import user_read_facade


async def platform_overview(db: AsyncSession) -> dict[str, Any]:
    """Return the superadmin landing payload.

    Each sub-section is failure-tolerant: if the underlying read model raises,
    the section degrades to its safe fallback and the remaining sections are
    unaffected.

    Args:
        db: Async SQLAlchemy session.

    Returns:
        dict with keys ``ai``, ``outbox``, ``moderation_pending``,
        ``active_users``.
    """

    ai_section: dict[str, Any] = await safe(
        db,
        lambda: ai_ops_read_service.overview(db),
        fallback={},
    )

    now = datetime.now(tz=UTC)

    async def _outbox() -> dict[str, Any]:
        counts = await dispatch_service.status_counts(db)
        oldest = await dispatch_service.oldest_pending_age_seconds(db, now=now)
        retry = await dispatch_service.retry_scheduled_count(db, now=now)
        return {**counts, "oldest_pending_age_seconds": oldest, "retry_scheduled": retry}

    outbox_section: dict[str, Any] = await safe(
        db,
        _outbox,
        fallback={},
    )

    moderation_pending: int = await safe(
        db,
        lambda: opportunities_read.count_pending_moderation_jobs(db),
        fallback=0,
    )

    active_users: int = await safe(
        db,
        lambda: user_read_facade.count_active_identities(db),
        fallback=0,
    )

    return {
        "ai": ai_section,
        "outbox": outbox_section,
        "moderation_pending": moderation_pending,
        "active_users": active_users,
    }
