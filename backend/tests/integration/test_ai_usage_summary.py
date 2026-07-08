"""Tests for the per-user AI quota (`usage_service`): the weekly window.

The daily request-count window was removed (WS-1) — cost-weighted metering is
now the masked-energy account (see ``test_daily_removed.py``). This suite covers
the remaining weekly gate: empty usage, counting only the caller's rows, the 80%
warning, week-exhaustion blocking, and the enforcement gate raising 409
QUOTA_EXCEEDED — all against real ``ai_usage_log`` rows (no fabricated numbers
reach the sidebar meter).
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


async def _log_calls(
    db_session,
    user_id,
    count: int,
    *,
    created_at=None,
    task_type: str = "ai_assistant_chat",
    success: bool = True,
) -> None:
    for _ in range(count):
        db_session.add(
            AiUsageLog(
                task_type=task_type,
                model_alias="chat_cheap",
                success=success,
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
    assert "day" not in data  # daily window removed (WS-1)
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

    assert "day" not in data  # daily window removed (WS-1)
    assert data["week"]["used"] == expected_week


async def test_usage_warns_at_80_percent_of_week(db_session) -> None:
    # Reworked from the old daily-warning test (WS-1): only the weekly window
    # drives the warning now.
    principal = await _principal(db_session)
    limit = get_settings().ai_weekly_request_limit

    await _log_calls(db_session, principal.user_id, int(limit * 0.8))
    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["warning"] is True
    assert data["blocked"] is False


async def test_week_exhaustion_blocks_with_week_scope(db_session) -> None:
    # Reworked from ``test_week_exhaustion_blocks_even_with_daily_room`` (WS-1):
    # there is no daily window to keep clear of anymore — the weekly window is
    # the only request-count gate.
    principal = await _principal(db_session)
    weekly = get_settings().ai_weekly_request_limit

    await _log_calls(db_session, principal.user_id, weekly)

    data = await usage_service.my_usage(db_session, principal=principal)

    assert data["blocked"] is True
    assert data["blocked_scope"] == "week"

    with pytest.raises(QuotaExceededError) as exc:
        await usage_service.enforce_quota(db_session, principal=principal)
    assert exc.value.details["reason"] == "AI_WEEKLY_QUOTA_EXCEEDED"


# --------------------------------------------------------------------------- #
# Usage DETAIL view (billing/usage panel): reset timing, per-feature breakdown, #
# recent activity — all PII/leakage-safe.                                       #
# --------------------------------------------------------------------------- #


async def test_usage_detail_empty_for_new_user(db_session) -> None:
    principal = await _principal(db_session)

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    assert data["total"] == 0
    assert data["by_feature"] == []
    assert data["recent"] == []
    assert data["window_days"] == usage_service.DEFAULT_WINDOW_DAYS
    # Only the weekly reset remains (daily window removed, WS-1).
    assert "day_reset" not in data
    week_reset = datetime.fromisoformat(data["week_reset"])
    now = datetime.now(UTC)
    assert week_reset > now


async def test_usage_detail_breakdown_maps_tasks_to_features(db_session) -> None:
    principal = await _principal(db_session)

    await _log_calls(db_session, principal.user_id, 3, task_type="ai_assistant_chat")
    await _log_calls(db_session, principal.user_id, 2, task_type="cover_letter")
    await _log_calls(db_session, principal.user_id, 1, task_type="ai_edit_command")
    # Excluded system task: still counts toward total request volume but must NOT
    # appear as a user-facing feature bucket.
    await _log_calls(db_session, principal.user_id, 2, task_type="kb_embedding")

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    assert data["total"] == 8  # all rows, including excluded system tasks
    features = {row["feature"]: row["count"] for row in data["by_feature"]}
    assert features == {"assistant": 3, "cover_letter": 2, "cv_edit": 1}
    # Sorted by count desc.
    assert [r["feature"] for r in data["by_feature"]] == [
        "assistant",
        "cover_letter",
        "cv_edit",
    ]
    # Excluded task appears nowhere in the breakdown or recent activity.
    assert "other" not in features
    assert all(r["feature"] != "other" for r in data["recent"])


async def test_usage_detail_unknown_task_falls_into_other(db_session) -> None:
    principal = await _principal(db_session)
    await _log_calls(db_session, principal.user_id, 1, task_type="brand_new_feature_x")

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    features = {row["feature"]: row["count"] for row in data["by_feature"]}
    assert features == {"other": 1}


async def test_usage_detail_only_counts_my_rows(db_session) -> None:
    principal = await _principal(db_session)
    other = await register_verified(
        db_session, email=f"usage_detail_other_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    await _log_calls(db_session, principal.user_id, 2, task_type="cover_letter")
    await _log_calls(db_session, other.id, 5, task_type="cover_letter")

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    assert data["total"] == 2
    assert {r["feature"]: r["count"] for r in data["by_feature"]} == {"cover_letter": 2}


async def test_usage_detail_window_excludes_old_rows(db_session) -> None:
    principal = await _principal(db_session)
    now = datetime.now(UTC)
    await _log_calls(db_session, principal.user_id, 2, task_type="cover_letter")
    # 40 days ago — outside the default 30-day window.
    await _log_calls(
        db_session,
        principal.user_id,
        4,
        task_type="cover_letter",
        created_at=now - timedelta(days=40),
    )

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    assert data["total"] == 2
    assert {r["feature"]: r["count"] for r in data["by_feature"]} == {"cover_letter": 2}


async def test_usage_detail_recent_shape_and_ordering(db_session) -> None:
    principal = await _principal(db_session)
    now = datetime.now(UTC)
    await _log_calls(
        db_session,
        principal.user_id,
        1,
        task_type="cover_letter",
        created_at=now - timedelta(hours=2),
    )
    await _log_calls(
        db_session,
        principal.user_id,
        1,
        task_type="interview_sim",
        success=False,
        created_at=now - timedelta(minutes=5),
    )

    data = await usage_service.my_usage_detail(db_session, principal=principal)

    assert len(data["recent"]) == 2
    # Most recent first.
    assert data["recent"][0]["feature"] == "interview"
    assert data["recent"][0]["ok"] is False
    assert data["recent"][1]["feature"] == "cover_letter"
    # Shape: exactly these keys, nothing that could leak internals.
    assert set(data["recent"][0].keys()) == {"feature", "ok", "at"}


async def test_usage_detail_never_leaks_ai_internals(db_session) -> None:
    import json

    principal = await _principal(db_session)
    await _log_calls(db_session, principal.user_id, 2, task_type="cover_letter")
    await _log_calls(db_session, principal.user_id, 1, task_type="cv_vision_extraction")

    data = await usage_service.my_usage_detail(db_session, principal=principal)
    blob = json.dumps(data, ensure_ascii=False).lower()

    for term in (
        "chat_cheap",
        "model_alias",
        "cost",
        "usd",
        "token",
        "prompt",
        "latency",
        "openrouter",
        "openai",
        "gemini",
        "gpt",
        "claude",
        # raw internal task labels must be mapped away, not surfaced verbatim
        "cv_vision_extraction",
        "ai_assistant_chat",
    ):
        assert term not in blob, f"leaked term: {term!r}"


async def test_chat_send_message_is_refused_when_quota_exhausted(db_session) -> None:
    from app.modules.ai_assistant.application import chat_service

    principal = await _principal(db_session)
    created = await chat_service.create_session(db_session, principal=principal)

    # Exhaust the WEEKLY window (the only request-count gate now, WS-1).
    await _log_calls(db_session, principal.user_id, get_settings().ai_weekly_request_limit)

    with pytest.raises(QuotaExceededError):
        await chat_service.send_message(
            db_session,
            principal=principal,
            session_id=uuid.UUID(created["id"]),
            text="Xin chào",
        )
