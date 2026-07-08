"""AI usage meter — energy-based (weekly HARD + 3h SOFT; daily removed).

Thin adapter over :mod:`app.ai.energy.service` (the persona-agnostic meter). The
user-facing unit is an **AI energy %** derived from cost-weighted credits summed
from the durable ``ai_billable_usage`` ledger — never tokens, USD, provider, or
model (``docs/AI_PRODUCT_SPEC.md`` §15).

- ``my_usage()`` powers the sidebar meter.
- ``my_usage_detail()`` adds a per-feature breakdown + recent activity for the
  billing/usage screen.
- ``enforce_quota()`` is the hard gate before an AI request — blocks only on
  WEEKLY exhaustion (after the top-up wallet). The 3h window is advisory.

For a PARTNER member the meter + breakdown are the shared ORG pool (all members);
for a student they are the caller's own user scope.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import service as energy_service
from app.ai.observability.models import AiUsageLog

# Detail-view window + recent-activity size for ``my_usage_detail``.
DEFAULT_WINDOW_DAYS = 30
RECENT_LIMIT = 20

# Product feature taxonomy for the usage breakdown. Maps INTERNAL ``task_type``
# labels (never exposed to the client) to stable product feature CODES that the
# frontend localizes. System/internal tasks are excluded from the breakdown.
_FEATURE_BY_TASK: dict[str, str] = {
    "ai_assistant_chat": "assistant",
    "cover_letter": "cover_letter",
    "ai_edit_command": "cv_edit",
    "cv_vision_extraction": "cv_import",
    "interview_sim": "interview",
    "answer_feedback": "interview",
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
    """Map an internal task_type to a user-facing feature code (or ``None``)."""
    if task_type in _EXCLUDED_TASKS:
        return None
    return _FEATURE_BY_TASK.get(task_type, "other")


def _iso_utc(dt: datetime | None) -> str | None:
    """Serialize a possibly-naive DB timestamp as a UTC ISO-8601 string."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


async def my_usage(session: AsyncSession, *, principal: Any) -> dict:
    """Return the caller's current AI energy snapshot (weekly + 3h)."""
    snap = await energy_service.snapshot(session, principal=principal)
    return snap.to_public()


async def my_usage_detail(
    session: AsyncSession,
    *,
    principal: Any,
    days: int = DEFAULT_WINDOW_DAYS,
    recent_limit: int = RECENT_LIMIT,
) -> dict:
    """Rich usage view: energy snapshot + per-feature breakdown + recent activity.

    Every value is PII- and leakage-safe: energy %, product feature CODES,
    success flags, and reset timestamps only — never provider/model names, token
    counts, USD, or latency.
    """
    snap = await energy_service.snapshot(session, principal=principal)
    result = snap.to_public()

    now = datetime.now(UTC)
    since = now - timedelta(days=max(1, days))

    on_org = energy_service.persona_meters_on_org(principal)
    scope_col = AiUsageLog.org_id if on_org else AiUsageLog.user_id
    scope_val = principal.org_id if on_org else principal.user_id

    # Per-feature breakdown over the window (grouped in the DB).
    grouped = (
        await session.execute(
            select(AiUsageLog.task_type, func.count().label("n"))
            .where(scope_col == scope_val, AiUsageLog.created_at >= since)
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
            .where(scope_col == scope_val)
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

    result.update(
        {
            "window_days": max(1, days),
            "total": total,
            "by_feature": by_feature,
            "recent": recent,
        }
    )
    return result


async def enforce_quota(session: AsyncSession, *, principal: Any) -> None:
    """Hard gate before running an AI request.

    Delegates to the energy meter: raises ``QuotaExceededError`` (409) only on
    WEEKLY energy exhaustion (after the top-up wallet). The 3h burst window is
    advisory and never blocks.
    """
    await energy_service.enforce_energy(session, principal=principal)
