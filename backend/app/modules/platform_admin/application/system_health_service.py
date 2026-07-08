"""Platform admin system-health read service (P3).

Three independent snapshots — all superadmin-only, all best-effort so a single
infra outage never raises a 500:

- ``jobs_health``   — latest run per REGISTRY job (+ never-run sentinel).
- ``queues_health`` — Redis reachability + best-effort Celery default-queue depth.
- ``services_health`` — DB, Redis, and notification-outbox counts.

No secrets, model names, provider internals, or raw enum codes are returned.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import ping_database
from app.modules.automation.scheduler.jobs import REGISTRY
from app.modules.notifications.application import dispatch_service
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

# Name of the Celery default queue; must match celery_app configuration.
_CELERY_DEFAULT_QUEUE = "celery"


def _require_superadmin(principal: Principal) -> None:
    """Service-layer RBAC guard (defence-in-depth — router already checks)."""
    if not principal.is_superadmin:
        raise PermissionDeniedError()


# ---------------------------------------------------------------------------
# Internal Redis helper (reuse pattern from app.api.health._ping_redis)
# ---------------------------------------------------------------------------


async def _ping_redis() -> bool:
    settings = get_settings()
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
        try:
            await client.ping()
            return True
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001
        return False


async def _celery_queue_depth() -> int | None:
    """Best-effort LLEN on the Celery default queue. Returns None on failure."""
    settings = get_settings()
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
        try:
            depth = await client.llen(_CELERY_DEFAULT_QUEUE)
            return depth
        finally:
            await client.aclose()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def jobs_health(session: AsyncSession, *, principal: Principal) -> list[dict[str, Any]]:
    """Return latest run metadata for every REGISTRY job.

    Jobs that have never run carry ``never_run: true`` and null timing fields.
    """
    _require_superadmin(principal)

    from sqlalchemy import func, select  # noqa: PLC0415

    from app.modules.automation.scheduler.models import SchedulerJobRun  # noqa: PLC0415

    # Fetch the single most-recent run for each distinct job_name.
    # ROW_NUMBER() OVER (PARTITION BY job_name ORDER BY started_at DESC) works
    # on both PostgreSQL and SQLite (3.25+, which ships with Python 3.12).
    rn = (
        func.row_number()
        .over(
            partition_by=SchedulerJobRun.job_name,
            order_by=SchedulerJobRun.started_at.desc(),
        )
        .label("rn")
    )
    inner = (
        select(
            SchedulerJobRun.job_name,
            SchedulerJobRun.started_at,
            SchedulerJobRun.finished_at,
            SchedulerJobRun.duration_ms,
            SchedulerJobRun.status,
            SchedulerJobRun.result,
            rn,
        )
    ).subquery()

    stmt = select(inner).where(inner.c.rn == 1)
    rows = (await session.execute(stmt)).all()
    latest: dict[str, Any] = {r.job_name: r for r in rows}

    result: list[dict[str, Any]] = []
    for job in REGISTRY:
        run = latest.get(job.name)
        if run is None:
            result.append(
                {
                    "name": job.name,
                    "interval_seconds": job.interval_seconds,
                    "never_run": True,
                    "last_started_at": None,
                    "last_finished_at": None,
                    "last_duration_ms": None,
                    "last_status": None,
                    "last_result": None,
                }
            )
        else:
            result.append(
                {
                    "name": job.name,
                    "interval_seconds": job.interval_seconds,
                    "never_run": False,
                    "last_started_at": run.started_at.isoformat() if run.started_at else None,
                    "last_finished_at": run.finished_at.isoformat() if run.finished_at else None,
                    "last_duration_ms": run.duration_ms,
                    "last_status": run.status,
                    "last_result": run.result,
                }
            )
    return result


async def queues_health(*, principal: Principal) -> dict[str, Any]:
    """Return Redis reachability and best-effort Celery default-queue depth."""
    _require_superadmin(principal)

    settings = get_settings()
    redis_ok = await _ping_redis()
    queue_depth: int | None = None
    if redis_ok:
        queue_depth = await _celery_queue_depth()

    broker_configured = bool(
        getattr(settings, "redis_url", None)
    )

    return {
        "redis": "ok" if redis_ok else "down",
        "celery_default_queue_depth": queue_depth,
        "broker_configured": broker_configured,
    }


async def services_health(session: AsyncSession, *, principal: Principal) -> dict[str, Any]:
    """Return database, Redis, and outbox health — each sub-check is best-effort."""
    _require_superadmin(principal)

    # Database check
    try:
        db_ok = await ping_database()
        database_status = "ok" if db_ok else "down"
    except Exception:  # noqa: BLE001
        database_status = "down"

    # Redis check
    try:
        redis_ok = await _ping_redis()
        redis_status = "ok" if redis_ok else "down"
    except Exception:  # noqa: BLE001
        redis_status = "down"

    # Outbox counts — call dispatch_service directly (no support-gate principal needed)
    outbox: dict[str, Any] = {
        "pending": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "dead": 0,
        "oldest_pending_age_seconds": None,
        "retry_scheduled": 0,
    }
    try:
        counts = await dispatch_service.status_counts(session)
        now = datetime.now(tz=UTC)
        age = await dispatch_service.oldest_pending_age_seconds(session, now=now)
        retry = await dispatch_service.retry_scheduled_count(session, now=now)
        outbox = {
            **counts,
            "oldest_pending_age_seconds": age,
            "retry_scheduled": retry,
        }
    except Exception:  # noqa: BLE001
        logger.warning("system_health.outbox_check_failed", exc_info=True)

    return {
        "database": database_status,
        "redis": redis_status,
        "outbox": outbox,
    }
