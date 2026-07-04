"""Tests for per-user AI quotas (`usage_service`): daily + weekly windows.

Covers: empty usage, counting only the caller's rows per window, the 80%
warning, week-exhaustion blocking even with daily room left, and the
enforcement gate raising 409 QUOTA_EXCEEDED — all against real
``ai_usage_log`` rows (no fabricated numbers reach the sidebar meter).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.observability.models import AiUsageLog
from app.core.config import get_settings
from app.modules.ai_assistant.application import usage_service
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

from tests.auth_utils import register_verified


async def _log_calls(db_session, user_id, count: int, *, created_at=None) -> None:
    for _ in range(count):
        db_session.add(
            AiUsageLog(
                task_type="ai_assistant_chat",
                model_alias="chat_cheap",
                success=True,
                user_id=user_id,
                created_at=created_at or datetime.now(UTC),
            )
        )
    await db_session.flush()


async def _principal(db_session) -> Principal:
    user = await register_verified(
        db_session, email=f"usage_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    return Principal(user_id=user.id, persona="partner", permissions=frozenset())


async def test_usage_empty_for_new_user(db_session) -> None:
    principal = await _principal(db_session)

    data = await usage_service.my_usage(db_session, principal=principal)

    settings = get_settings()
    assert data["day"] == {"used": 0, "limit": settings.ai_daily_request_limit, "pct": 0}
    assert data["week"] == {"used": 0, "limit": settings.ai_weekly_request_limit, "pct": 0}
    assert data["warning"] is False
    assert data["blocked"] is False
    assert data["blocked_scope"] is None


async def test_usage_counts_per_window_and_only_my_rows(db_session) -> None:
    principal = await _principal(db_session)
    other = await register_verified(
        db_session, email=f"usage_other_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    now = datetime.now(UTC)

    await _log_calls(db_session, principal.user_id, 3)
    await _log_calls(db_session, other.id, 5)
    # Earlier this week (not today): counts weekly, not daily. Anchor on a
    # Thursday+ mindset: go back 1 day but clamp inside the current ISO week.
    days_into_week = now.weekday()
    if days_into_week >= 1:
        await _log_calls(db_session, principal.user_id, 2, created_at=now - timedelta(days=1))
        expected_week = 5
    else:
        expected_week = 3
    # Last week: counts nowhere.
    await _log_calls(db_session, principal.user_id, 4, created_at=now - timedelta(days=8))

    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["day"]["used"] == 3
    assert data["week"]["used"] == expected_week


async def test_usage_warns_at_80_percent_of_day(db_session) -> None:
    principal = await _principal(db_session)
    limit = get_settings().ai_daily_request_limit

    await _log_calls(db_session, principal.user_id, int(limit * 0.8))
    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["warning"] is True
    assert data["blocked"] is False


async def test_day_exhaustion_blocks_with_day_scope(db_session) -> None:
    principal = await _principal(db_session)
    limit = get_settings().ai_daily_request_limit

    await _log_calls(db_session, principal.user_id, limit)
    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["blocked"] is True
    assert data["blocked_scope"] == "day"

    with pytest.raises(QuotaExceededError) as exc:
        await usage_service.enforce_quota(db_session, principal=principal)
    assert exc.value.details["reason"] == "AI_DAILY_QUOTA_EXCEEDED"


async def test_week_exhaustion_blocks_even_with_daily_room(db_session) -> None:
    principal = await _principal(db_session)
    settings = get_settings()
    now = datetime.now(UTC)

    # Fill the WEEKLY window using rows from earlier in the week when possible,
    # keeping today's count well under the daily limit. Early in the week
    # (Mon/Tue) part of the fill lands today by necessity — the weekly scope
    # must still dominate the blocked reason.
    weekly = settings.ai_weekly_request_limit
    earlier_days = min(now.weekday(), 6)
    if earlier_days >= 1:
        per_day = weekly // earlier_days + 1
        for d in range(1, earlier_days + 1):
            await _log_calls(
                db_session, principal.user_id, per_day, created_at=now - timedelta(days=d)
            )
    else:
        await _log_calls(db_session, principal.user_id, weekly)

    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["blocked"] is True
    assert data["blocked_scope"] == "week"

    with pytest.raises(QuotaExceededError) as exc:
        await usage_service.enforce_quota(db_session, principal=principal)
    assert exc.value.details["reason"] == "AI_WEEKLY_QUOTA_EXCEEDED"


async def test_chat_send_message_is_refused_when_quota_exhausted(db_session) -> None:
    from app.modules.ai_assistant.application import chat_service

    principal = await _principal(db_session)
    created = await chat_service.create_session(db_session, principal=principal)

    await _log_calls(db_session, principal.user_id, get_settings().ai_daily_request_limit)

    with pytest.raises(QuotaExceededError):
        await chat_service.send_message(
            db_session,
            principal=principal,
            session_id=uuid.UUID(created["id"]),
            text="Xin chào",
        )
