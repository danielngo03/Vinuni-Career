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


async def overview(
    db: AsyncSession,
    range_days: int = 7,  # noqa: ARG001 — reserved for future "today vs N-day context"
) -> dict[str, Any]:
    """Return high-level platform AI health: spend today, budget, error rate, requests."""

    async def _spend_today() -> float:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.cost_usd), 0.0)).where(
                AiUsageDaily.day >= _today_start()
            )
        )
        return float(result.scalar_one())

    async def _requests_today() -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.requests), 0)).where(
                AiUsageDaily.day >= _today_start()
            )
        )
        return int(result.scalar_one())

    async def _errors_today() -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageDaily.errors), 0)).where(
                AiUsageDaily.day >= _today_start()
            )
        )
        return int(result.scalar_one())

    spend_today = await _safe(db, _spend_today, fallback=0.0)
    requests_today = await _safe(db, _requests_today, fallback=0)
    errors_today = await _safe(db, _errors_today, fallback=0)

    budget = runtime_config.current().daily_budget_usd
    error_rate = (errors_today / requests_today) if requests_today > 0 else 0.0

    return {
        "spend_today": spend_today,
        "budget": budget,
        "error_rate": error_rate,
        "requests": requests_today,
    }


async def spend(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",  # noqa: ARG001 — grouping applied via SQL grain; exposed for future use
) -> list[dict[str, Any]]:
    """Return aggregated spend from ``ai_usage_daily``.

    The full (day × task_type × provider × model) grain is always returned;
    ``group_by`` is accepted for API forward-compatibility and reserved for
    server-side aggregation in a future iteration.
    """

    async def _query() -> list[dict[str, Any]]:
        since = _range_start(range_days)
        stmt = (
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
        rows = (await db.execute(stmt)).all()
        return [
            {
                "day": r.day.date().isoformat() if r.day else None,
                "task_type": r.task_type,
                "provider": r.provider or None,
                "model": r.model or None,
                "cost_usd": float(r.cost_usd or 0.0),
                "requests": int(r.requests or 0),
                "errors": int(r.errors or 0),
            }
            for r in rows
        ]

    return await _safe(db, _query, fallback=[])


async def reliability(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",  # noqa: ARG001 — reserved for future per-day breakdown
) -> dict[str, Any]:
    """Return error rates, fallback rates, and circuit-breaker states."""

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
    provider_names = {route[0] for route in cfg.provider_routes.values() if route}
    circuit_states = {name: get_circuit_state(name) for name in sorted(provider_names)}

    return {**agg, "circuit_states": circuit_states}


async def volume(
    db: AsyncSession,
    range_days: int = 7,
    group_by: str = "day",  # noqa: ARG001 — reserved for future per-provider breakdown
) -> list[dict[str, Any]]:
    """Return request/token volume from ``ai_usage_daily``."""

    async def _query() -> list[dict[str, Any]]:
        since = _range_start(range_days)
        stmt = (
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
        rows = (await db.execute(stmt)).all()
        return [
            {
                "day": r.day.date().isoformat() if r.day else None,
                "task_type": r.task_type,
                "requests": int(r.requests or 0),
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
            }
            for r in rows
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
        stmt = select(AiOpsEvent).order_by(
            AiOpsEvent.created_at.desc(), AiOpsEvent.id.desc()
        )

        # Cursor-based pagination: (created_at, id) desc.
        if cursor:
            try:
                ts_str, id_str = cursor.rsplit(":", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                cursor_id = uuid.UUID(id_str)
                stmt = stmt.where(
                    (AiOpsEvent.created_at < cursor_ts)
                    | (
                        (AiOpsEvent.created_at == cursor_ts)
                        & (AiOpsEvent.id < cursor_id)
                    )
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
            items.append({
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
            })

        return {"items": items, "next_cursor": next_cursor}

    return await _safe(db, _query, fallback={"items": [], "next_cursor": None})
