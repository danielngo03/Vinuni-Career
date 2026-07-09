"""Per-user AI request quota: rolling session + weekly windows.

Counts ``ai_usage_log`` rows for the caller (request counts only — no cost,
token, latency, or provider data ever leaves the backend, per AI_PRODUCT_SPEC
leakage rules) against one platform allowance:

- ``AI_SESSION_REQUEST_LIMIT`` — rolling short-session soft-warning window.
- ``AI_WEEKLY_REQUEST_LIMIT`` — hard cap, resets at UTC Monday 00:00.

The daily request-count window was removed (WS-1): fine-grained, cost-weighted
metering is now the masked-energy account
(:mod:`app.modules.billing.application.energy_service`). This legacy
request-count surface keeps a rolling session warning and weekly hard cap as a
coarse safety net for chat.

``my_usage()`` powers the sidebar meter; ``enforce_quota()`` is the hard gate
called before running an AI request — when the weekly window is exhausted the
request is refused with ``409 QUOTA_EXCEEDED``. The UI warns from 80% in either
window.
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

# Detail-view window + recent-activity size for ``my_usage_detail``.
DEFAULT_WINDOW_DAYS = 30
RECENT_LIMIT = 20

# Product feature taxonomy for the usage breakdown. Maps INTERNAL ``task_type``
# labels (never exposed to the client) to stable product feature CODES that the
# frontend localizes. Keeping this an explicit allowlist means a new internal
# task never silently leaks a raw label into a user surface. System/internal
# tasks (translation, embeddings, rerank, eval judge) are deliberately excluded:
# they are not user-initiated features and would only confuse the breakdown.
_FEATURE_BY_TASK: dict[str, str] = {
    "ai_assistant_chat": "assistant",
    "cover_letter": "cover_letter",
    "ai_edit_command": "cv_edit",
    "cv_vision_extraction": "cv_import",
    "interview_sim": "interview",
    "answer_feedback": "interview",
    "mock_interview_turn": "mock_interview",
    "mock_interview_report": "mock_interview",
    "mock_interview_realtime": "mock_interview",
    "scorecard_suggest": "scorecard",
    "screening_brief": "screening",
    "bulk_screening_brief": "screening",
    "jd_generation": "jd_draft",
    "jd_extraction": "jd_import",
    "jd_vision_extraction": "jd_import",
    "market_intelligence": "market_intel",
}
_EXCLUDED_TASKS: frozenset[str] = frozenset(
    {
        "skill_translation",
        "jd_translation",
        "cv_translation",
        "eval_judge",
        "kb_embedding",
        "retrieval_rerank",
    }
)


def _feature_for(task_type: str) -> str | None:
    """Map an internal task_type to a user-facing feature code.

    Returns ``None`` for excluded system/internal tasks (dropped from the
    breakdown), a mapped code for known product features, or ``"other"`` for an
    unrecognized but non-excluded task (honest catch-all for future features).
    """
    if task_type in _EXCLUDED_TASKS:
        return None
    return _FEATURE_BY_TASK.get(task_type, "other")


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=UTC)


def _iso_utc(dt: datetime | None) -> str | None:
    """Serialize a possibly-naive DB timestamp as a UTC ISO-8601 string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


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
    """Return the caller's rolling session and weekly AI request usage."""
    settings = get_settings()
    now = datetime.now(UTC)

    session_used = await _count_since(
        session,
        principal.user_id,
        now - timedelta(hours=max(1, settings.ai_session_window_hours)),
    )
    week_used = await _count_since(session, principal.user_id, _week_start(now))
    session_window = _window(session_used, settings.ai_session_request_limit)
    week = _window(week_used, settings.ai_weekly_request_limit)

    blocked_scope = "week" if week["pct"] >= 100 else None

    return {
        "session": session_window,
        "week": week,
        "warning": max(session_window["pct"], week["pct"]) >= WARNING_THRESHOLD_PCT,
        "blocked": blocked_scope is not None,
        "blocked_scope": blocked_scope,
    }


async def my_usage_detail(
    session: AsyncSession,
    *,
    principal: Any,
    days: int = DEFAULT_WINDOW_DAYS,
    recent_limit: int = RECENT_LIMIT,
) -> dict:
    """Rich usage view for the caller's billing/usage screen.

    Extends ``my_usage`` (the sidebar meter) with reset timing, a per-feature
    breakdown, and a recent-activity list over the last ``days``. Every value is
    PII- and leakage-safe: only request counts, product feature CODES, success
    flags, and reset timestamps are returned — never provider/model names, model
    aliases, token counts, cost, or latency (``docs/AI_PRODUCT_SPEC.md`` §15).
    """
    settings = get_settings()
    now = datetime.now(UTC)

    session_used = await _count_since(
        session,
        principal.user_id,
        now - timedelta(hours=max(1, settings.ai_session_window_hours)),
    )
    week_used = await _count_since(session, principal.user_id, _week_start(now))
    session_window = _window(session_used, settings.ai_session_request_limit)
    week = _window(week_used, settings.ai_weekly_request_limit)
    blocked_scope = "week" if week["pct"] >= 100 else None

    since = now - timedelta(days=max(1, days))

    # Per-feature breakdown over the window (grouped in the DB).
    grouped = (
        await session.execute(
            select(AiUsageLog.task_type, func.count().label("n"))
            .where(
                AiUsageLog.user_id == principal.user_id,
                AiUsageLog.created_at >= since,
            )
            .group_by(AiUsageLog.task_type)
        )
    ).all()
    feature_counts: dict[str, int] = {}
    total = 0
    for task_type, n in grouped:
        total += int(n)
        feature = _feature_for(task_type)
        if feature is None:
            continue
        feature_counts[feature] = feature_counts.get(feature, 0) + int(n)
    by_feature = [
        {"feature": feature, "count": count}
        for feature, count in sorted(
            feature_counts.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    # Recent activity. Over-fetch so excluded system rows don't starve the list.
    recent_rows = (
        await session.execute(
            select(
                AiUsageLog.task_type,
                AiUsageLog.success,
                AiUsageLog.created_at,
            )
            .where(AiUsageLog.user_id == principal.user_id)
            .order_by(AiUsageLog.created_at.desc())
            .limit(max(1, recent_limit) * 3)
        )
    ).all()
    recent: list[dict] = []
    for task_type, success, created_at in recent_rows:
        feature = _feature_for(task_type)
        if feature is None:
            continue
        recent.append(
            {"feature": feature, "ok": bool(success), "at": _iso_utc(created_at)}
        )
        if len(recent) >= recent_limit:
            break

    return {
        "session": session_window,
        "week": week,
        "warning": max(session_window["pct"], week["pct"]) >= WARNING_THRESHOLD_PCT,
        "blocked": blocked_scope is not None,
        "blocked_scope": blocked_scope,
        "week_reset": _iso_utc(_week_start(now) + timedelta(days=7)),
        "window_days": max(1, days),
        "total": total,
        "by_feature": by_feature,
        "recent": recent,
    }


async def enforce_quota(session: AsyncSession, *, principal: Any) -> None:
    """Hard gate before running an AI request.

    Raises ``QuotaExceededError`` (409) when the weekly allowance is exhausted.
    The daily window was removed (WS-1); cost-weighted metering lives in the
    masked-energy account, and this coarse request-count gate keeps only the
    weekly hard cap.
    """
    usage = await my_usage(session, principal=principal)
    if not usage["blocked"]:
        return
    raise QuotaExceededError(
        "Bạn đã dùng hết hạn mức AI trong tuần. Hạn mức sẽ được đặt lại vào thứ Hai.",
        details={"reason": "AI_WEEKLY_QUOTA_EXCEEDED"},
    )
