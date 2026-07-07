"""AI observability maintenance jobs.

Two idempotent maintenance operations called by the scheduler:

1. ``reconcile_ai_usage_daily`` — recompute ``ai_usage_daily`` rollup rows for a
   given calendar day from ``ai_ops_event`` source rows.  Self-heals any gaps
   caused by ledger-write failures during the original recording path.

2. ``prune_ai_ops_events`` — delete ``ai_ops_event`` rows older than the
   configured retention window.  ``ai_usage_daily`` rollup rows are never
   touched.

Both functions are idempotent: running them multiple times produces the same
result, never doubled counters or double-deletes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiOpsEvent, AiUsageDaily

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _day_window(day: datetime) -> tuple[datetime, datetime]:
    """Return the half-open UTC window ``[day_start, day_start + 1 day)``.

    The caller may pass any datetime within the target day; the function
    normalises it to midnight UTC.
    """
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return day_start, day_start + timedelta(days=1)


# Grain key: (task_type, provider, model, org_id)
_GrainKey = tuple[str, str, str, uuid.UUID | None]


@dataclass
class _GrainAgg:
    """Typed accumulator for one rollup grain during a reconcile pass."""

    requests: int = 0
    errors: int = 0
    fallbacks: int = 0
    blocked: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms_sum: int = 0
    latency_ms_count: int = 0

    def absorb(self, ev: AiOpsEvent) -> None:
        self.requests += 1
        self.errors += 1 if ev.status == "error" else 0
        self.fallbacks += 1 if ev.fallback_used else 0
        self.blocked += 1 if ev.status == "blocked" else 0
        self.prompt_tokens += ev.prompt_tokens or 0
        self.completion_tokens += ev.completion_tokens or 0
        self.cost_usd += float(ev.cost_usd or 0)
        if ev.latency_ms is not None:
            self.latency_ms_sum += ev.latency_ms
            self.latency_ms_count += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def reconcile_ai_usage_daily(db: AsyncSession, day: datetime) -> int:
    """Recompute ``ai_usage_daily`` rows for *day* from ``ai_ops_event`` rows.

    Groups all ``ai_ops_event`` rows whose ``created_at`` falls in
    ``[day_start, day_start + 1 day)`` by the rollup grain
    ``(task_type, provider, model, org_id)`` and upserts one
    ``AiUsageDaily`` row per group.

    Idempotent: calling this function twice with the same *day* produces
    the same totals, not doubled ones.  Pre-existing rows with wrong values
    are overwritten with the recomputed truth.

    Parameters
    ----------
    db:
        An open ``AsyncSession``; the caller is responsible for committing.
    day:
        Any ``datetime`` within the target calendar day (timezone-aware or
        naive — normalised to midnight UTC internally).

    Returns
    -------
    int
        Number of ``ai_usage_daily`` rows written or updated.
    """
    day_start, day_end = _day_window(day)

    # ------------------------------------------------------------------
    # 1. Fetch all ai_ops_event rows for the target day.
    #    Python-side GROUP BY keeps the code cross-database safe (SQLite
    #    does not support all server-side aggregate expressions in the same
    #    way PostgreSQL does).
    # ------------------------------------------------------------------
    events = (
        await db.scalars(
            select(AiOpsEvent).where(
                AiOpsEvent.created_at >= day_start,
                AiOpsEvent.created_at < day_end,
            )
        )
    ).all()

    if not events:
        _log.debug(
            "reconcile_ai_usage_daily: no events for %s, nothing to write",
            day_start.date(),
        )
        return 0

    # ------------------------------------------------------------------
    # 2. Accumulate into per-grain aggregates.
    # ------------------------------------------------------------------
    aggregates: dict[_GrainKey, _GrainAgg] = {}
    for ev in events:
        grain: _GrainKey = (ev.task_type, ev.provider or "", ev.model or "", ev.org_id)
        if grain not in aggregates:
            aggregates[grain] = _GrainAgg()
        aggregates[grain].absorb(ev)

    # ------------------------------------------------------------------
    # 3. Upsert one AiUsageDaily row per grain (idempotent overwrite).
    # ------------------------------------------------------------------
    written = 0
    for (task_type, provider_key, model_key, org_id), agg in aggregates.items():
        row = await db.scalar(
            select(AiUsageDaily).where(
                AiUsageDaily.day == day_start,
                AiUsageDaily.task_type == task_type,
                AiUsageDaily.provider == provider_key,
                AiUsageDaily.model == model_key,
                AiUsageDaily.org_id == org_id,
            )
        )

        if row is None:
            row = AiUsageDaily(
                day=day_start,
                task_type=task_type,
                provider=provider_key,
                model=model_key,
                org_id=org_id,
                requests=0,
                errors=0,
                fallbacks=0,
                blocked=0,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                latency_ms_sum=0,
                latency_ms_count=0,
            )
            db.add(row)

        # Always overwrite with the recomputed truth (self-healing).
        row.requests = agg.requests
        row.errors = agg.errors
        row.fallbacks = agg.fallbacks
        row.blocked = agg.blocked
        row.prompt_tokens = agg.prompt_tokens
        row.completion_tokens = agg.completion_tokens
        row.cost_usd = agg.cost_usd
        row.latency_ms_sum = agg.latency_ms_sum
        row.latency_ms_count = agg.latency_ms_count
        written += 1

    _log.info(
        "reconcile_ai_usage_daily: day=%s events=%d grains=%d",
        day_start.date(),
        len(events),
        written,
    )
    return written


async def prune_ai_ops_events(
    db: AsyncSession,
    older_than_days: int = 90,
    *,
    _now: datetime | None = None,
) -> int:
    """Delete ``ai_ops_event`` rows older than *older_than_days*.

    The retention cutoff is ``now - older_than_days`` (strict less-than, so a
    row timestamped exactly at the cutoff is NOT deleted).

    ``ai_usage_daily`` rollup rows and ``ai_usage_log`` rows are never touched.

    Parameters
    ----------
    db:
        An open ``AsyncSession``; the caller is responsible for committing.
    older_than_days:
        Retention window in calendar days.  Default is 90.
    _now:
        Override the current time (keyword-only, for deterministic tests).

    Returns
    -------
    int
        Number of ``ai_ops_event`` rows deleted.
    """
    now = _now if _now is not None else datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days)

    cursor: CursorResult[tuple[()]] = await db.execute(  # type: ignore[assignment]
        delete(AiOpsEvent).where(AiOpsEvent.created_at < cutoff)
    )
    deleted: int = cursor.rowcount

    _log.info(
        "prune_ai_ops_events: cutoff=%s deleted=%d",
        cutoff.isoformat(),
        deleted,
    )
    return deleted


# ---------------------------------------------------------------------------
# Scheduler entrypoint coros (match JobCoro signature: session, now → dict)
# ---------------------------------------------------------------------------


async def _reconcile_entrypoint(db: AsyncSession, now: datetime) -> dict[str, int]:
    """Scheduler coro: reconcile yesterday and today.

    Running for two days ensures any events that landed just before midnight
    are captured even if the scheduler tick was slightly late.
    """
    yesterday = now - timedelta(days=1)
    written_yesterday = await reconcile_ai_usage_daily(db, yesterday)
    written_today = await reconcile_ai_usage_daily(db, now)
    await db.commit()
    return {"written_yesterday": written_yesterday, "written_today": written_today}


async def _prune_entrypoint(db: AsyncSession, now: datetime) -> dict[str, int]:
    """Scheduler coro: prune ai_ops_event rows older than 90 days."""
    deleted = await prune_ai_ops_events(db, older_than_days=90, _now=now)
    await db.commit()
    return {"deleted": deleted}
