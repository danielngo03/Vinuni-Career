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


async def check_async(
    db: AsyncSession,
    *,
    alias: str,
    estimated_cost_usd: float = 0.0,
    user_id: object | None = None,
) -> None:
    """Async hard-stop: query today's real spend from ``ai_usage_log``.

    Raises ``402 PaymentRequiredError`` (code ``BUDGET_EXCEEDED``) if adding
    ``estimated_cost_usd`` to today's total would exceed the configured daily
    budget. Degrades silently on DB errors (never blocks the call path on infra
    failure — only on policy).

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

    if user_id is None:
        return

    user_nested = None
    try:
        from app.modules.billing.application import limit_facade

        user_nested = await db.begin_nested()
        user_budget = await limit_facade.resolve_user_ai_daily_cost_quota(db, user_id)
        if user_budget <= 0:
            await user_nested.commit()
            return
        user_result = await db.execute(
            select(func.coalesce(func.sum(AiUsageLog.cost_usd), 0)).where(
                AiUsageLog.cost_usd.is_not(None),
                AiUsageLog.user_id == user_id,
                AiUsageLog.created_at >= day_start,
            )
        )
        user_spent_today = float(user_result.scalar() or 0.0)
        await user_nested.commit()
    except Exception:
        if user_nested is not None and user_nested.is_active:
            await user_nested.rollback()
        return

    if user_spent_today + estimated_cost_usd > user_budget:
        raise PaymentRequiredError(
            "Bạn đã đạt giới hạn sử dụng AI trong ngày của gói hiện tại.",
            details={
                "reason": "AI_USER_DAILY_QUOTA_EXCEEDED",
                "alias": alias,
            },
        )
