"""Per-user AI request quotas: daily + weekly windows.

Counts ``ai_usage_log`` rows for the caller (request counts only — no cost,
token, latency, or provider data ever leaves the backend, per AI_PRODUCT_SPEC
leakage rules) against two platform allowances:

- ``AI_DAILY_REQUEST_LIMIT``  — resets at UTC midnight.
- ``AI_WEEKLY_REQUEST_LIMIT`` — resets at UTC Monday 00:00.

``my_usage()`` powers the sidebar meter; ``enforce_quota()`` is the hard gate
called before running an AI request — when EITHER window is exhausted the
request is refused with ``409 QUOTA_EXCEEDED`` (an exhausted week blocks even
if today still has room). The UI warns from 80% on the tighter window.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiUsageLog
from app.core.config import get_settings
from app.shared.exceptions import QuotaExceededError

WARNING_THRESHOLD_PCT = 80


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=UTC)


async def _count_since(session: AsyncSession, user_id: Any, since: datetime) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(AiUsageLog)
            .where(AiUsageLog.user_id == user_id, AiUsageLog.created_at >= since)
        )
    ).scalar_one()


def _window(used: int, limit: int) -> dict:
    limit = max(1, limit)
    return {
        "used": int(used),
        "limit": limit,
        "pct": min(100, round(used * 100 / limit)),
    }


async def my_usage(session: AsyncSession, *, principal: Any) -> dict:
    """Return today's and this week's AI request usage for the caller."""
    settings = get_settings()
    now = datetime.now(UTC)

    day_used = await _count_since(session, principal.user_id, _day_start(now))
    week_used = await _count_since(session, principal.user_id, _week_start(now))

    day = _window(day_used, settings.ai_daily_request_limit)
    week = _window(week_used, settings.ai_weekly_request_limit)

    # Week exhaustion dominates: it blocks for longer, so it is the scope the
    # user must act on first.
    blocked_scope = "week" if week["pct"] >= 100 else "day" if day["pct"] >= 100 else None

    return {
        "day": day,
        "week": week,
        "warning": max(day["pct"], week["pct"]) >= WARNING_THRESHOLD_PCT,
        "blocked": blocked_scope is not None,
        "blocked_scope": blocked_scope,
    }


async def enforce_quota(session: AsyncSession, *, principal: Any) -> None:
    """Hard gate before running an AI request.

    Raises ``QuotaExceededError`` (409) when the daily or weekly allowance is
    exhausted. The weekly check is authoritative: an exhausted week refuses
    requests even when the daily window still has room.
    """
    usage = await my_usage(session, principal=principal)
    if not usage["blocked"]:
        return
    if usage["blocked_scope"] == "week":
        raise QuotaExceededError(
            "Bạn đã dùng hết hạn mức AI trong tuần. Hạn mức sẽ được đặt lại vào thứ Hai.",
            details={"reason": "AI_WEEKLY_QUOTA_EXCEEDED"},
        )
    raise QuotaExceededError(
        "Bạn đã dùng hết hạn mức AI trong ngày. Vui lòng quay lại vào ngày mai.",
        details={"reason": "AI_DAILY_QUOTA_EXCEEDED"},
    )
