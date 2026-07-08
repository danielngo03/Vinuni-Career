"""Per-day AI budget enforcement (AI_PRODUCT_SPEC §11.2).

Two layers:
- ``check()`` — sync fast-path using an in-memory accumulator (V1: no-op for
  offline calls). Kept for backward compat and sync contexts.
- ``check_async()`` — async hard-stop that queries today's real spend from
  ``ai_usage_log``. Called in the AI gateway before every real provider call.
  Raises ``402 BUDGET_EXCEEDED`` (PaymentRequiredError) when the day's
  estimated spend would exceed ``daily_budget_usd`` from the runtime snapshot.

Admin PATCH to ``daily_budget_usd`` takes effect immediately via the snapshot.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from app.ai.gateway import runtime_config
from app.shared.exceptions import PaymentRequiredError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SpendAccumulator(Protocol):
    """Returns today's accrued spend in USD for the current budget scope."""

    def spent_today_usd(self) -> float: ...


class _NoOpAccumulator:
    """Offline / test default: no real cost, so accrued spend is always 0."""

    def spent_today_usd(self) -> float:
        return 0.0


_accumulator: SpendAccumulator = _NoOpAccumulator()


def set_accumulator(accumulator: SpendAccumulator) -> None:
    """Wire a custom accumulator (e.g., Redis-backed for multi-process)."""
    global _accumulator
    _accumulator = accumulator


def check(estimated_cost_usd: float = 0.0) -> None:
    """Sync budget check using the in-memory accumulator.

    V1: no-op when the offline accumulator is active (offline calls cost 0).
    Upgraded to the DB-backed async path when real calls are enabled.
    """
    budget = runtime_config.current().daily_budget_usd
    if budget <= 0:
        return
    spent = _accumulator.spent_today_usd()
    if spent + max(0.0, estimated_cost_usd) > float(budget):
        raise PaymentRequiredError(
            "Đã đạt giới hạn chi phí AI trong ngày. Vui lòng thử lại sau.",
            details={"reason": "BUDGET_EXCEEDED"},
        )


async def _fetch_org_spend_today(
    db: AsyncSession,
    org_id: uuid.UUID,
    day_start: datetime,
) -> float:
    """Sum today's cost_usd from ai_usage_daily for the given org.

    Extracted as a separate function so tests can patch it for the
    silent-degrade infra-error path.
    """
    from sqlalchemy import func, select

    from app.ai.observability.models import AiUsageDaily

    result = await db.execute(
        select(func.coalesce(func.sum(AiUsageDaily.cost_usd), 0)).where(
            AiUsageDaily.org_id == org_id,
            AiUsageDaily.day >= day_start,
            AiUsageDaily.day < day_start + timedelta(days=1),
        )
    )
    return float(result.scalar() or 0.0)  # type: ignore[arg-type]


async def check_async(
    db: AsyncSession,
    *,
    alias: str,
    estimated_cost_usd: float = 0.0,
    user_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> None:
    """Async hard-stop: query today's real spend from ``ai_usage_log``.

    Raises ``402 PaymentRequiredError`` (code ``BUDGET_EXCEEDED``) if adding
    ``estimated_cost_usd`` to today's total would exceed any configured daily
    budget. Two layered checks (both degrade silently on DB errors — only
    policy violations block):

    1. Platform daily budget (``ai_settings.daily_budget_usd``).
    2. Per-org daily budget (``ai_settings.per_org_daily_budget_usd``,
       queried from the ``ai_usage_daily`` rollup for speed).

    The per-user student USD-daily quota gate was removed (WS-1): fine-grained,
    cost-weighted per-student metering is now the masked-energy account
    (:mod:`app.modules.billing.application.energy_service`). Only the platform /
    per-org USD ceilings remain here as superadmin safety nets.

    Pass ``org_id=None`` (default) to skip check 2 (backward compatible).
    This is called BEFORE the real provider call so the request is rejected
    before tokens are consumed.
    """
    budget = runtime_config.current().daily_budget_usd
    if budget <= 0:
        return  # unlimited

    from datetime import UTC, datetime, time

    from sqlalchemy import func, select

    from app.ai.observability.models import AiUsageLog

    # ``AiUsageLog.created_at`` is always written with ``datetime.now(tz=UTC)``
    # (and read back naive-UTC on drivers that drop tzinfo). The "today" window
    # must therefore be the UTC calendar day, not the local calendar day —
    # ``date.today()`` uses local time and drifts a day off from UTC-stored
    # rows whenever the local timezone offset crosses midnight relative to UTC.
    day_start = datetime.combine(datetime.now(tz=UTC).date(), time.min, tzinfo=UTC)

    nested = None
    try:
        nested = await db.begin_nested()
        result = await db.execute(
            select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                AiUsageLog.cost_usd.is_not(None),
                AiUsageLog.created_at >= day_start,
            )
        )
        spent_today = float(result.scalar() or 0.0)
        await nested.commit()
    except Exception:
        if nested is not None and nested.is_active:
            await nested.rollback()
        # DB unavailable — don't block; log and continue
        return

    if spent_today + estimated_cost_usd > float(budget):
        raise PaymentRequiredError(
            "Đã đạt giới hạn chi phí AI trong ngày. Vui lòng thử lại sau.",
            details={
                "reason": "BUDGET_EXCEEDED",
                "alias": alias,
            },
        )

    # NOTE: the per-user student USD-daily quota gate was removed (WS-1).
    # Cost-weighted per-student metering is now the masked-energy account
    # (weekly hard block + 3h soft warn, no daily). ``user_id`` is still accepted
    # for telemetry/back-compat but no longer drives a daily USD block here.

    # --- Per-org daily budget check ---
    # Runs AFTER the platform check so it remains the primary gate.
    # Queries the pre-aggregated ai_usage_daily rollup (fast path — no log scan).
    # Degrades silently on infra error, exactly like the platform check above.
    if org_id is None:
        return

    org_nested = None
    try:
        from sqlalchemy import select

        from app.modules.ai_settings.domain.models import PLATFORM_SCOPE, AiSettings

        org_nested = await db.begin_nested()
        settings_result = await db.execute(
            select(AiSettings.per_org_daily_budget_usd)
            .where(AiSettings.scope == PLATFORM_SCOPE)
            .limit(1)
        )
        per_org_budget_raw = settings_result.scalar()
        await org_nested.commit()
    except Exception:
        if org_nested is not None and org_nested.is_active:
            await org_nested.rollback()
        return

    if per_org_budget_raw is None:
        return  # no per-org cap configured

    per_org_budget = float(per_org_budget_raw)
    if per_org_budget <= 0:
        return  # 0 / negative = unlimited

    org_spend_nested = None
    try:
        org_spend_nested = await db.begin_nested()
        org_spent = await _fetch_org_spend_today(db, org_id, day_start)
        await org_spend_nested.commit()
    except Exception:
        if org_spend_nested is not None and org_spend_nested.is_active:
            await org_spend_nested.rollback()
        return

    if org_spent + estimated_cost_usd > per_org_budget:
        raise PaymentRequiredError(
            "Tổ chức của bạn đã đạt giới hạn chi phí AI trong ngày.",
            details={
                "reason": "BUDGET_EXCEEDED",
                "alias": alias,
            },
        )
