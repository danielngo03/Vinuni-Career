"""Standalone asyncio scheduler loop + single-tick entrypoint (ADR-0003 §1/§5).

No business logic lives here. ``run_forever`` decides which registered jobs are
*due* (by interval vs last-run) and delegates to :func:`tick`; ``tick`` runs each
selected job exactly once, each in its **own** :class:`AsyncSession` (so one job's
failure never rolls back another), commits, and returns a ``{job_name: result}``
map. The API process never imports or starts this loop — only ``app.worker`` does,
and only when ``BACKGROUND_WORKER_MODE=scheduler``.

Tests drive scheduling through :func:`tick` / :func:`run_job` (never the domain
``process_outbox`` / ``sweep_*`` functions directly), proving each job *as
scheduled*. The PostgreSQL-only ``FOR UPDATE SKIP LOCKED`` claim in the outbox
service is dialect-guarded, so the SQLite test path is inert.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import jobs as job_registry
from app.modules.automation.scheduler.jobs import ScheduledJob

logger = logging.getLogger(__name__)

# A zero-arg callable returning an async-context-manager session (the app's
# ``async_sessionmaker``). Injected in tests; defaults to the process sessionmaker.
SessionFactory = Callable[[], AsyncSession]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _factory(session_factory: SessionFactory | None) -> SessionFactory:
    return session_factory if session_factory is not None else get_sessionmaker()


async def _persist_run(
    factory: SessionFactory,
    job_name: str,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    result: dict[str, Any],
) -> None:
    """Best-effort persistence of a SchedulerJobRun row.

    Runs in its own session so a DB write failure here never affects the job
    result already committed by :func:`run_job`. Mirrors the never-raise
    telemetry pattern from ``ai_ops``.
    """
    # Import lazily to avoid a circular import at module load time.
    from app.modules.automation.scheduler.models import SchedulerJobRun  # noqa: PLC0415

    try:
        async with factory() as session:
            session.add(
                SchedulerJobRun(
                    job_name=job_name,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    status=status,
                    result=result,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning(
            "scheduler.persist_run_failed",
            extra={"job": job_name},
            exc_info=True,
        )


async def run_job(
    job: ScheduledJob | str,
    *,
    session_factory: SessionFactory | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run one registered job in its own session and commit. Never raises.

    A job that raises is rolled back and logged (PII-safe) and reported as
    ``{"error": 1}`` so a single bad tick never takes the loop down.

    After each run (success or failure) a ``SchedulerJobRun`` row is written
    best-effort; a persistence failure is logged but never propagates.
    """

    if isinstance(job, str):
        job = job_registry.by_name(job)
    factory = _factory(session_factory)
    now = now or _now()
    started_at = now
    t0 = time.monotonic()
    async with factory() as session:
        try:
            result = await job.run(session, now)
            await session.commit()
            result_dict = dict(result)
            status = "ok"
        except Exception:  # noqa: BLE001 - one job must not crash the scheduler
            await session.rollback()
            logger.warning("scheduler.job_failed", extra={"job": job.name}, exc_info=True)
            result_dict = {"error": 1}
            status = "error"

    finished_at = _now()
    duration_ms = int((time.monotonic() - t0) * 1000)
    try:
        await _persist_run(
            factory,
            job_name=job.name,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status,
            result=result_dict,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "scheduler.persist_run_outer_failed",
            extra={"job": job.name},
            exc_info=True,
        )
    return result_dict


async def tick(
    now: datetime | None = None,
    *,
    session_factory: SessionFactory | None = None,
    only: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run the selected due jobs once; return ``{job_name: result}``.

    ``only`` restricts the run to a subset of job names (used by ``run_forever`` to
    fire only the jobs whose interval elapsed). When ``None`` every registered job
    runs once — the entrypoint tests call.
    """

    now = now or _now()
    factory = _factory(session_factory)
    wanted = None if only is None else set(only)
    results: dict[str, dict[str, Any]] = {}
    for job in job_registry.REGISTRY:
        if wanted is not None and job.name not in wanted:
            continue
        results[job.name] = await run_job(job, session_factory=factory, now=now)
    return results


async def run_forever(*, session_factory: SessionFactory | None = None) -> None:
    """Tick loop: fire each registered job at its cadence, forever.

    State is the per-job last-run wall clock; a job is due when
    ``now - last_run >= interval``. On the first iteration every job is due. The
    loop sleeps ``scheduler_base_tick_seconds`` between iterations.
    """

    settings = get_settings()
    base = max(settings.scheduler_base_tick_seconds, 1)
    factory = _factory(session_factory)
    last_run: dict[str, float] = {}
    logger.info("scheduler.loop_start", extra={"base_tick_seconds": base})
    while True:
        now = _now()
        ts = now.timestamp()
        due = [
            job.name
            for job in job_registry.REGISTRY
            if ts - last_run.get(job.name, 0.0) >= job.interval_seconds
        ]
        if due:
            results = await tick(now, session_factory=factory, only=due)
            for name in due:
                last_run[name] = ts
            logger.info("scheduler.tick", extra={"jobs": due, "results": results})
        await asyncio.sleep(base)
