"""AI ops read service — aggregated telemetry for the superadmin dashboard.

Queries:
- ``overview``   : one-number summary: spend today, budget, error rate, requests.
- ``spend``      : time-series / breakdown of cost from ``ai_usage_daily``.
- ``reliability``: error-rate / fallback-rate / circuit-breaker state.
- ``volume``     : request/token counts from ``ai_usage_daily``.
- ``events``     : cursor-paginated ``ai_ops_event`` rows.

Design notes:
- Every aggregate is wrapped in ``_safe()`` so one failing sub-query returns a
  safe default without surfacing a 500 to the caller.  RBAC decisions are made
  by the caller (router) BEFORE any ``_safe`` call so 401/403 are never swallowed.
- Provider and model identity is masked when ``reveal_identity=False``: those
  fields are returned as ``None`` (never the raw DB value).
- Circuit-breaker state is read-only from the in-process
  ``app.ai.gateway.factory._circuit_states`` dict via the public
  ``get_circuit_state`` accessor; it is never mutated here.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import runtime_config
from app.ai.gateway.factory import get_circuit_state
from app.ai.observability.models import AiOpsEvent, AiUsageDaily

# ---------------------------------------------------------------------------
# Internal: failure-tolerant widget helper (mirrors dashboards._common.safe)
# ---------------------------------------------------------------------------


async def _safe[T](
    session: AsyncSession,
    factory: Callable[[], Awaitable[T]],
    *,
    fallback: T,
) -> T:
    """Run one sub-query; degrade to ``fallback`` on any failure.

    Rolls back a poisoned read transaction before returning the fallback so
    subsequent queries in the same request are unaffected.  RBAC checks must
    happen BEFORE any ``_safe`` call — 401/403 exceptions are never swallowed.
    """
    try:
        return await factory()
    except Exception:  # noqa: BLE001 — intentional: degrade one widget
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        return fallback


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _today_utc() -> date:
    return datetime.now(tz=UTC).date()


def _range_start(range_days: int) -> datetime:
    """Return midnight UTC ``range_days`` ago (inclusive lower bound)."""
    return datetime.combine(
        _today_utc() - timedelta(days=range_days - 1),
        datetime.min.time(),
        tzinfo=UTC,
    )


def _today_start() -> datetime:
    return datetime.combine(_today_utc(), datetime.min.time(), tzinfo=UTC)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def _p95_nearest_rank(vals: list[int]) -> int | None:
    """Return nearest-rank p95 of a sorted (ascending) list of ints.

    Reusable helper — used by ``overview`` and ``timeseries``.
    Cross-DB safe: no PG percentile function; computes entirely in Python.
    Returns ``None`` for an empty list.
    """
    if not vals:
        return None
    idx = min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)
    return vals[idx]


async def overview(
    db: AsyncSession,
    range_days: int = 7,
) -> dict[str, Any]:
    """Return high-level platform AI health: spend, budget, error rate, requests.

    ``range_days`` controls the aggregation window: ``1`` = today only,
    ``7`` = last 7 days, etc.  The window always starts at midnight UTC
    ``range_days`` ago (inclusive) through the end of today.
    """

    window_start = _range_start(range_days)

    async def _spend_today() -> float:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.cost_usd), 0.0)).where(
                AiUsageDaily.day >= window_start
            )
        )
        return float(result.scalar_one())

    async def _requests_today() -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.requests), 0)).where(
                AiUsageDaily.day >= window_start
            )
        )
        return int(result.scalar_one())

    async def _errors_today() -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.errors), 0)).where(
                AiUsageDaily.day >= window_start
            )
        )
        return int(result.scalar_one())

    async def _p95_latency_ms() -> int | None:
        """Compute nearest-rank p95 latency from per-request ai_ops_event rows.

        SQLite (used in tests) has no PERCENTILE_CONT, so we sort in Python.
        Capped at 200 000 rows — sufficient for any realistic daily window.
        """
        result = await db.execute(
            select(AiOpsEvent.latency_ms)
            .where(
                AiOpsEvent.created_at >= window_start,
                AiOpsEvent.latency_ms.is_not(None),
            )
            .order_by(AiOpsEvent.latency_ms)
            .limit(200_000)
        )
        vals = [int(row[0]) for row in result.all()]
        return _p95_nearest_rank(vals)

    spend_today = await _safe(db, _spend_today, fallback=0.0)
    requests_today = await _safe(db, _requests_today, fallback=0)
    errors_today = await _safe(db, _errors_today, fallback=0)
    p95_latency_ms = await _safe(db, _p95_latency_ms, fallback=None)

    budget = runtime_config.current().daily_budget_usd
    error_rate = (errors_today / requests_today) if requests_today > 0 else 0.0

    return {
        "spend_today": spend_today,
        "budget": budget,
        "error_rate": error_rate,
        "requests": requests_today,
        "p95_latency_ms": p95_latency_ms,
    }


async def spend(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",
    reveal_identity: bool = False,
) -> list[dict[str, Any]]:
    """Return aggregated spend from ``ai_usage_daily``.

    ``group_by`` controls the SQL aggregation grain:
    - ``"feature"``  — group by task_type (sums across all days/providers/models).
    - ``"model"``    — group by model (sums across all days/task_types/providers).
    - ``"provider"`` — group by provider (sums across all days/task_types/models).
    - anything else  — default day × task_type × provider × model grain.

    When ``reveal_identity=False``, ``provider`` and ``model`` in every returned
    row are set to ``None`` regardless of what is stored.
    """

    async def _query() -> list[dict[str, Any]]:
        since = _range_start(range_days)

        if group_by == "feature":
            stmt = (
                select(
                    AiUsageDaily.task_type,
                    func.sum(AiUsageDaily.cost_usd).label("cost_usd"),
                    func.sum(AiUsageDaily.requests).label("requests"),
                    func.sum(AiUsageDaily.errors).label("errors"),
                )
                .where(AiUsageDaily.day >= since)
                .group_by(AiUsageDaily.task_type)
                .order_by(AiUsageDaily.task_type.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [
                {
                    "day": None,
                    "task_type": r.task_type,
                    "provider": None,
                    "model": None,
                    "cost_usd": float(r.cost_usd or 0.0),
                    "requests": int(r.requests or 0),
                    "errors": int(r.errors or 0),
                }
                for r in rows
            ]

        if group_by == "model":
            stmt = (
                select(
                    AiUsageDaily.model,
                    func.sum(AiUsageDaily.cost_usd).label("cost_usd"),
                    func.sum(AiUsageDaily.requests).label("requests"),
                    func.sum(AiUsageDaily.errors).label("errors"),
                )
                .where(AiUsageDaily.day >= since)
                .group_by(AiUsageDaily.model)
                .order_by(AiUsageDaily.model.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [
                {
                    "day": None,
                    "task_type": None,
                    "provider": None,
                    "model": r.model if reveal_identity else None,
                    "cost_usd": float(r.cost_usd or 0.0),
                    "requests": int(r.requests or 0),
                    "errors": int(r.errors or 0),
                }
                for r in rows
            ]

        if group_by == "provider":
            stmt = (
                select(
                    AiUsageDaily.provider,
                    func.sum(AiUsageDaily.cost_usd).label("cost_usd"),
                    func.sum(AiUsageDaily.requests).label("requests"),
                    func.sum(AiUsageDaily.errors).label("errors"),
                )
                .where(AiUsageDaily.day >= since)
                .group_by(AiUsageDaily.provider)
                .order_by(AiUsageDaily.provider.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [
                {
                    "day": None,
                    "task_type": None,
                    "provider": r.provider if reveal_identity else None,
                    "model": None,
                    "cost_usd": float(r.cost_usd or 0.0),
                    "requests": int(r.requests or 0),
                    "errors": int(r.errors or 0),
                }
                for r in rows
            ]

        # Default: full day × task_type × provider × model grain.
        default_stmt = (
            select(
                AiUsageDaily.day,
                AiUsageDaily.task_type,
                AiUsageDaily.provider,
                AiUsageDaily.model,
                func.sum(AiUsageDaily.cost_usd).label("cost_usd"),
                func.sum(AiUsageDaily.requests).label("requests"),
                func.sum(AiUsageDaily.errors).label("errors"),
            )
            .where(AiUsageDaily.day >= since)
            .group_by(
                AiUsageDaily.day,
                AiUsageDaily.task_type,
                AiUsageDaily.provider,
                AiUsageDaily.model,
            )
            .order_by(AiUsageDaily.day.asc())
        )
        default_rows = (await db.execute(default_stmt)).all()
        return [
            {
                "day": r.day.date().isoformat() if r.day else None,
                "task_type": r.task_type,
                "provider": (r.provider or None) if reveal_identity else None,
                "model": (r.model or None) if reveal_identity else None,
                "cost_usd": float(r.cost_usd or 0.0),
                "requests": int(r.requests or 0),
                "errors": int(r.errors or 0),
            }
            for r in default_rows
        ]

    return await _safe(db, _query, fallback=[])


async def reliability(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",  # noqa: ARG001 — reserved for future per-day breakdown
    reveal_identity: bool = False,
) -> dict[str, Any]:
    """Return error rates, fallback rates, and circuit-breaker states.

    When ``reveal_identity=False``, the ``circuit_states`` map keys are replaced
    with stable positional placeholders (``"provider_1"``, ``"provider_2"``, …)
    so no concrete provider names leak.  The factory ``_circuit_states`` dict is
    never mutated — we build a fresh masked copy.
    """

    _RELIABILITY_FALLBACK: dict[str, Any] = {
        "requests": 0,
        "errors": 0,
        "fallbacks": 0,
        "error_rate": 0.0,
        "fallback_rate": 0.0,
    }

    async def _query() -> dict[str, Any]:
        since = _range_start(range_days)
        stmt = select(
            func.coalesce(func.sum(AiUsageDaily.requests), 0).label("requests"),
            func.coalesce(func.sum(AiUsageDaily.errors), 0).label("errors"),
            func.coalesce(func.sum(AiUsageDaily.fallbacks), 0).label("fallbacks"),
        ).where(AiUsageDaily.day >= since)
        row = (await db.execute(stmt)).one()
        requests = int(row.requests)
        errors = int(row.errors)
        fallbacks = int(row.fallbacks)
        error_rate = errors / requests if requests > 0 else 0.0
        fallback_rate = fallbacks / requests if requests > 0 else 0.0
        return {
            "requests": requests,
            "errors": errors,
            "fallbacks": fallbacks,
            "error_rate": error_rate,
            "fallback_rate": fallback_rate,
        }

    agg = await _safe(db, _query, fallback=_RELIABILITY_FALLBACK)

    # Read-only circuit-breaker states from the in-process factory dict.
    cfg = runtime_config.current()
    provider_names = sorted({route[0] for route in cfg.provider_routes.values() if route})
    raw_circuit_states = {name: get_circuit_state(name) for name in provider_names}

    if reveal_identity:
        circuit_states: dict[str, Any] = raw_circuit_states
    else:
        # Mask provider names to stable positional placeholders.
        circuit_states = {
            f"provider_{i + 1}": state for i, (_, state) in enumerate(raw_circuit_states.items())
        }

    return {**agg, "circuit_states": circuit_states}


async def volume(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",
) -> list[dict[str, Any]]:
    """Return request/token volume from ``ai_usage_daily``.

    ``group_by`` controls the aggregation grain:
    - ``"feature"``  — group by task_type.
    - ``"model"``    — group by model (identity not exposed here; no masking needed
                       because volume rows never carry provider/model labels in the
                       response schema).
    - ``"provider"`` — group by provider (same note).
    - anything else  — default day × task_type grain (time-series).
    """

    async def _query() -> list[dict[str, Any]]:
        since = _range_start(range_days)

        if group_by == "feature":
            stmt = (
                select(
                    AiUsageDaily.task_type,
                    func.sum(AiUsageDaily.requests).label("requests"),
                    func.sum(AiUsageDaily.prompt_tokens).label("prompt_tokens"),
                    func.sum(AiUsageDaily.completion_tokens).label("completion_tokens"),
                )
                .where(AiUsageDaily.day >= since)
                .group_by(AiUsageDaily.task_type)
                .order_by(AiUsageDaily.task_type.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [
                {
                    "day": None,
                    "task_type": r.task_type,
                    "requests": int(r.requests or 0),
                    "prompt_tokens": int(r.prompt_tokens or 0),
                    "completion_tokens": int(r.completion_tokens or 0),
                }
                for r in rows
            ]

        # Default: day × task_type time-series grain.
        default_stmt = (
            select(
                AiUsageDaily.day,
                AiUsageDaily.task_type,
                func.sum(AiUsageDaily.requests).label("requests"),
                func.sum(AiUsageDaily.prompt_tokens).label("prompt_tokens"),
                func.sum(AiUsageDaily.completion_tokens).label("completion_tokens"),
            )
            .where(AiUsageDaily.day >= since)
            .group_by(AiUsageDaily.day, AiUsageDaily.task_type)
            .order_by(AiUsageDaily.day.asc())
        )
        default_rows = (await db.execute(default_stmt)).all()
        return [
            {
                "day": r.day.date().isoformat() if r.day else None,
                "task_type": r.task_type,
                "requests": int(r.requests or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in default_rows
        ]

    return await _safe(db, _query, fallback=[])


async def events(
    db: AsyncSession,
    cursor: str | None,
    filters: dict[str, Any],
    *,
    reveal_identity: bool,
    limit: int = 50,
) -> dict[str, Any]:
    """Return cursor-paginated ``ai_ops_event`` rows (newest first).

    Cursor is an opaque ``"{created_at_iso}:{id}"`` string.  Returns at most
    ``limit`` rows plus a ``next_cursor`` for subsequent pages.

    When ``reveal_identity=False``, ``provider`` and ``model`` are masked to
    ``None`` in every returned row.
    """

    async def _query() -> dict[str, Any]:
        stmt = select(AiOpsEvent).order_by(AiOpsEvent.created_at.desc(), AiOpsEvent.id.desc())

        # Cursor-based pagination: (created_at, id) desc.
        if cursor:
            try:
                ts_str, id_str = cursor.rsplit(":", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (AiOpsEvent.created_at < cursor_ts)
                    | ((AiOpsEvent.created_at == cursor_ts) & (AiOpsEvent.id < cursor_id))
                )
            except (ValueError, AttributeError):
                # Invalid cursor: ignore and start from the beginning.
                pass

        # Optional filters.
        task_type = filters.get("task_type")
        if task_type:
            stmt = stmt.where(AiOpsEvent.task_type == task_type)
        status = filters.get("status")
        if status:
            stmt = stmt.where(AiOpsEvent.status == status)
        org_id = filters.get("org_id")
        if org_id:
            stmt = stmt.where(AiOpsEvent.org_id == org_id)

        stmt = stmt.limit(limit + 1)
        rows = (await db.execute(stmt)).scalars().all()

        has_more = len(rows) > limit
        page_rows = rows[:limit]

        next_cursor: str | None = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = f"{last.created_at.isoformat()}:{last.id}"

        items: list[dict[str, Any]] = []
        for row in page_rows:
            cost = row.cost_usd
            items.append(
                {
                    "id": str(row.id),
                    "created_at": row.created_at.isoformat(),
                    "task_type": row.task_type,
                    "alias": row.alias,
                    "provider": row.provider if reveal_identity else None,
                    "model": row.model if reveal_identity else None,
                    "prompt_tokens": row.prompt_tokens,
                    "completion_tokens": row.completion_tokens,
                    "latency_ms": row.latency_ms,
                    "status": row.status,
                    "fallback_used": row.fallback_used,
                    "circuit_open": row.circuit_open,
                    # SQLAlchemy Numeric returns Decimal at runtime; convert explicitly.
                    "cost_usd": float(cost) if cost is not None else None,
                    "unpriced": row.unpriced,
                    "langfuse_trace_id": row.langfuse_trace_id,
                }
            )

        return {"items": items, "next_cursor": next_cursor}

    return await _safe(db, _query, fallback={"items": [], "next_cursor": None})


# ---------------------------------------------------------------------------
# timeseries — per-day aggregates for line/area charts
# ---------------------------------------------------------------------------


async def timeseries(
    db: AsyncSession,
    range_days: int = 7,
) -> dict[str, Any]:
    """Return one row per calendar day in the window for line/area charts.

    Aggregates cost, requests, errors, tokens, avg_latency_ms from
    ``ai_usage_daily`` grouped by day.  Per-day p95_latency_ms is computed
    from ``ai_ops_event`` rows (Python nearest-rank — cross-DB safe).

    Gap days (days with no ``ai_usage_daily`` activity) are filled with zero
    rows so the frontend chart has a continuous axis.  p95_latency_ms is
    ``None`` when no ``ai_ops_event`` rows exist for that day.

    No provider/model identity is returned — these are aggregate-only rows.
    """

    window_start = _range_start(range_days)
    today = _today_utc()

    # Build the ordered list of calendar days in the window (ascending).
    n_days = (today - window_start.date()).days + 1
    all_days = [(window_start.date() + timedelta(days=i)).isoformat() for i in range(n_days)]

    async def _query() -> dict[str, Any]:
        # --- Aggregate from ai_usage_daily per day --------------------------
        stmt = (
            select(
                AiUsageDaily.day,
                func.sum(AiUsageDaily.cost_usd).label("cost_usd"),
                func.sum(AiUsageDaily.requests).label("requests"),
                func.sum(AiUsageDaily.errors).label("errors"),
                func.sum(AiUsageDaily.prompt_tokens).label("prompt_tokens"),
                func.sum(AiUsageDaily.completion_tokens).label("completion_tokens"),
                func.sum(AiUsageDaily.latency_ms_sum).label("latency_ms_sum"),
                func.sum(AiUsageDaily.latency_ms_count).label("latency_ms_count"),
            )
            .where(AiUsageDaily.day >= window_start)
            .group_by(AiUsageDaily.day)
            .order_by(AiUsageDaily.day.asc())
        )
        rows = (await db.execute(stmt)).all()

        # Index daily rows by ISO date string.
        daily: dict[str, dict[str, Any]] = {}
        for r in rows:
            day_iso = r.day.date().isoformat() if r.day else None
            if day_iso is None:
                continue
            requests = int(r.requests or 0)
            errors = int(r.errors or 0)
            latency_sum = int(r.latency_ms_sum or 0)
            latency_count = int(r.latency_ms_count or 0)
            daily[day_iso] = {
                "cost_usd": float(r.cost_usd or 0.0),
                "requests": requests,
                "errors": errors,
                "error_rate": (errors / requests) if requests > 0 else 0.0,
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "avg_latency_ms": (latency_sum / latency_count if latency_count > 0 else None),
            }

        # --- Per-day p95 from ai_ops_event ----------------------------------
        # Fetch all events in the window once; partition by day in Python.
        # Capped at 200k rows per the same convention as overview.
        events_stmt = (
            select(AiOpsEvent.created_at, AiOpsEvent.latency_ms)
            .where(
                AiOpsEvent.created_at >= window_start,
                AiOpsEvent.latency_ms.is_not(None),
            )
            .order_by(AiOpsEvent.created_at.asc(), AiOpsEvent.latency_ms.asc())
            .limit(200_000)
        )
        event_rows = (await db.execute(events_stmt)).all()

        # Group latency values by ISO day.
        day_latencies: dict[str, list[int]] = {}
        for ev_created_at, ev_latency_ms in event_rows:
            ev_day = ev_created_at.date().isoformat()
            day_latencies.setdefault(ev_day, [])
            day_latencies[ev_day].append(int(ev_latency_ms))

        # Sort each day's latency list so _p95_nearest_rank can index directly.
        for d in day_latencies:
            day_latencies[d].sort()

        # --- Assemble the series, filling gap days --------------------------
        series: list[dict[str, Any]] = []
        for day_iso in all_days:
            agg = daily.get(day_iso)
            p95 = _p95_nearest_rank(day_latencies.get(day_iso, []))
            if agg is None:
                series.append(
                    {
                        "day": day_iso,
                        "cost_usd": 0.0,
                        "requests": 0,
                        "errors": 0,
                        "error_rate": 0.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "avg_latency_ms": None,
                        # p95 may be non-None even on gap days if ai_ops_event rows
                        # exist for that day without a corresponding ai_usage_daily row.
                        "p95_latency_ms": p95,
                    }
                )
            else:
                series.append(
                    {
                        "day": day_iso,
                        **agg,
                        "p95_latency_ms": p95,
                    }
                )

        return {"series": series}

    return await _safe(db, _query, fallback={"series": []})


# ---------------------------------------------------------------------------
# error_heatmap — per (day × hour) error counts for heatmap charts
# ---------------------------------------------------------------------------


async def error_heatmap(
    db: AsyncSession,
    range_days: int = 7,
) -> dict[str, Any]:
    """Return sparse (day × hour) cells of request/error counts for heatmap charts.

    Groups ``ai_ops_event`` rows by UTC date and hour-of-day within the window.
    Only cells that have activity are returned (sparse is fine for a heatmap).

    No provider/model identity is returned — aggregate-only.
    Bounded at 500k event rows to guard against runaway full-table scans.
    """

    window_start = _range_start(range_days)

    async def _query() -> dict[str, Any]:
        # Pull (created_at, status) from ai_ops_event within the window.
        # We compute day + hour in Python to stay cross-DB safe (no DATE_TRUNC
        # or strftime in the GROUP BY since SQLite handles them differently from PG).
        stmt = (
            select(AiOpsEvent.created_at, AiOpsEvent.status)
            .where(AiOpsEvent.created_at >= window_start)
            .order_by(AiOpsEvent.created_at.asc())
            .limit(500_000)
        )
        rows = (await db.execute(stmt)).all()

        # Aggregate into (day_iso, hour) buckets.
        # Key: (day_iso, hour_int) → {"requests": int, "errors": int}
        buckets: dict[tuple[str, int], dict[str, int]] = {}
        for ev_created_at, ev_status in rows:
            day_iso = ev_created_at.date().isoformat()
            hour = ev_created_at.hour  # UTC hour
            key = (day_iso, hour)
            if key not in buckets:
                buckets[key] = {"requests": 0, "errors": 0}
            buckets[key]["requests"] += 1
            if ev_status not in ("ok", "success"):
                buckets[key]["errors"] += 1

        # Emit cells sorted by day then hour for deterministic output.
        cells: list[dict[str, Any]] = [
            {
                "day": day_iso,
                "hour": hour,
                "requests": bucket["requests"],
                "errors": bucket["errors"],
            }
            for (day_iso, hour), bucket in sorted(buckets.items())
        ]
        return {"cells": cells}

    return await _safe(db, _query, fallback={"cells": []})
