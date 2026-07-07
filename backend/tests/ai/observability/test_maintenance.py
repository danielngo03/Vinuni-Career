"""Tests for AI ops maintenance jobs: reconcile + prune.

TDD: tests written first. Run:
    cd backend && uv run pytest tests/ai/observability/test_maintenance.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.observability.models import AiOpsEvent, AiUsageDaily
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    *,
    created_at: datetime,
    task_type: str = "job_fit",
    provider: str | None = "openrouter",
    model: str | None = "deepseek/deepseek-r1",
    org_id: uuid.UUID | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    latency_ms: int = 300,
    status: str = "ok",
    fallback_used: bool = False,
    cost_usd: float = 0.002,
) -> AiOpsEvent:
    return AiOpsEvent(
        created_at=created_at,
        task_type=task_type,
        alias="chat_default",
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=status,
        fallback_used=fallback_used,
        circuit_open=False,
        cost_usd=cost_usd,
        unpriced=False,
        org_id=org_id,
        user_id=None,
        session_id=None,
        request_id=None,
        langfuse_trace_id=None,
    )


def _day_start(dt: datetime) -> datetime:
    """Return midnight UTC of the given datetime."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# reconcile_ai_usage_daily tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_creates_daily_rows_from_events(db_session: AsyncSession) -> None:
    """Reconcile a day with two distinct grains → two AiUsageDaily rows."""
    from app.ai.observability.maintenance import reconcile_ai_usage_daily

    day = _day_start(datetime(2026, 6, 1, tzinfo=UTC))
    org = uuid.uuid4()

    # Grain 1: job_fit / openrouter / deepseek-r1 / org
    db_session.add(_make_event(created_at=day.replace(hour=9), task_type="job_fit",
                               org_id=org, prompt_tokens=100, completion_tokens=50,
                               cost_usd=0.001))
    db_session.add(_make_event(created_at=day.replace(hour=14), task_type="job_fit",
                               org_id=org, prompt_tokens=200, completion_tokens=80,
                               cost_usd=0.002, fallback_used=True))
    # Grain 2: cv_bullets / openai / gpt-4o-mini / no org
    db_session.add(_make_event(created_at=day.replace(hour=11), task_type="cv_bullets",
                               provider="openai", model="gpt-4o-mini", org_id=None,
                               prompt_tokens=400, completion_tokens=150,
                               cost_usd=0.005, status="error"))
    await db_session.flush()

    written = await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    assert written == 2

    rows = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(rows) == 2

    # Locate grain 1
    g1 = next(r for r in rows if r.task_type == "job_fit")
    assert g1.requests == 2
    assert g1.prompt_tokens == 300
    assert g1.completion_tokens == 130
    assert float(g1.cost_usd) == pytest.approx(0.003)
    assert g1.fallbacks == 1
    assert g1.errors == 0
    assert g1.latency_ms_sum == 600
    assert g1.latency_ms_count == 2
    assert g1.org_id == org

    # Locate grain 2
    g2 = next(r for r in rows if r.task_type == "cv_bullets")
    assert g2.requests == 1
    assert g2.errors == 1
    assert g2.fallbacks == 0
    assert g2.prompt_tokens == 400
    assert g2.completion_tokens == 150
    assert float(g2.cost_usd) == pytest.approx(0.005)
    assert g2.org_id is None


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(db_session: AsyncSession) -> None:
    """Running reconcile twice yields the same totals, not doubled."""
    from app.ai.observability.maintenance import reconcile_ai_usage_daily

    day = _day_start(datetime(2026, 6, 2, tzinfo=UTC))

    db_session.add(_make_event(created_at=day.replace(hour=10), task_type="embedding",
                               provider=None, model=None,
                               prompt_tokens=50, completion_tokens=0, cost_usd=0.001))
    db_session.add(_make_event(created_at=day.replace(hour=11), task_type="embedding",
                               provider=None, model=None,
                               prompt_tokens=60, completion_tokens=0, cost_usd=0.001))
    await db_session.flush()

    await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    # Run again — totals must be unchanged.
    written2 = await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    rows = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(rows) == 1
    assert rows[0].requests == 2
    assert rows[0].prompt_tokens == 110
    assert float(rows[0].cost_usd) == pytest.approx(0.002)
    assert written2 == 1


@pytest.mark.asyncio
async def test_reconcile_corrects_wrong_preexisting_daily_row(db_session: AsyncSession) -> None:
    """A pre-existing stale/wrong AiUsageDaily row is corrected to the recomputed value."""
    from app.ai.observability.maintenance import reconcile_ai_usage_daily

    day = _day_start(datetime(2026, 6, 3, tzinfo=UTC))
    org = uuid.uuid4()

    # Seed the source events.
    db_session.add(_make_event(created_at=day.replace(hour=8), task_type="cover_letter",
                               provider="openai", model="gpt-4o-mini", org_id=org,
                               prompt_tokens=300, completion_tokens=100, cost_usd=0.004))
    await db_session.flush()

    # Pre-seed a WRONG daily row for the same grain (simulates a ledger failure).
    stale = AiUsageDaily(
        day=day,
        task_type="cover_letter",
        provider="openai",
        model="gpt-4o-mini",
        org_id=org,
        requests=99,      # wrong
        errors=5,         # wrong
        fallbacks=0,
        blocked=0,
        prompt_tokens=9999,  # wrong
        completion_tokens=9999,
        cost_usd=99.0,       # wrong
        latency_ms_sum=0,
        latency_ms_count=0,
    )
    db_session.add(stale)
    await db_session.flush()

    written = await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    rows = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(rows) == 1
    assert written == 1

    row = rows[0]
    # Must reflect the truth from ai_ops_event, not the stale values.
    assert row.requests == 1
    assert row.errors == 0
    assert row.prompt_tokens == 300
    assert row.completion_tokens == 100
    assert float(row.cost_usd) == pytest.approx(0.004)


@pytest.mark.asyncio
async def test_reconcile_excludes_events_outside_day(db_session: AsyncSession) -> None:
    """Events from adjacent days must not be folded into the target day's rollup."""
    from app.ai.observability.maintenance import reconcile_ai_usage_daily

    day = _day_start(datetime(2026, 6, 4, tzinfo=UTC))
    prev_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)

    db_session.add(_make_event(created_at=day.replace(hour=12), task_type="job_fit",
                               prompt_tokens=100, cost_usd=0.001))
    # These must be excluded:
    db_session.add(_make_event(created_at=prev_day.replace(hour=23), task_type="job_fit",
                               prompt_tokens=999, cost_usd=9.0))
    db_session.add(_make_event(created_at=next_day.replace(hour=0), task_type="job_fit",
                               prompt_tokens=999, cost_usd=9.0))
    await db_session.flush()

    await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    rows = (await db_session.scalars(
        select(AiUsageDaily).where(AiUsageDaily.day == day)
    )).all()
    assert len(rows) == 1
    assert rows[0].requests == 1
    assert rows[0].prompt_tokens == 100


@pytest.mark.asyncio
async def test_reconcile_returns_zero_for_empty_day(db_session: AsyncSession) -> None:
    """Reconciling a day with no events returns 0 and writes no rows."""
    from app.ai.observability.maintenance import reconcile_ai_usage_daily

    day = _day_start(datetime(2026, 6, 5, tzinfo=UTC))
    written = await reconcile_ai_usage_daily(db_session, day)
    await db_session.flush()

    assert written == 0
    rows = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# prune_ai_ops_events tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_deletes_old_events_keeps_recent(db_session: AsyncSession) -> None:
    """Events older than the retention window are deleted; recent ones are kept."""
    from app.ai.observability.maintenance import prune_ai_ops_events

    now = datetime.now(UTC)
    old_ts = now - timedelta(days=91)
    recent_ts = now - timedelta(days=10)

    for _ in range(3):
        db_session.add(_make_event(created_at=old_ts, task_type="job_fit"))
    for _ in range(2):
        db_session.add(_make_event(created_at=recent_ts, task_type="cv_bullets"))
    await db_session.flush()

    deleted = await prune_ai_ops_events(db_session, older_than_days=90)
    await db_session.flush()

    assert deleted == 3

    remaining = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(remaining) == 2
    assert all(e.task_type == "cv_bullets" for e in remaining)


@pytest.mark.asyncio
async def test_prune_does_not_touch_ai_usage_daily(db_session: AsyncSession) -> None:
    """Pruning raw events must never delete AiUsageDaily rollup rows."""
    from app.ai.observability.maintenance import prune_ai_ops_events

    now = datetime.now(UTC)
    old_ts = now - timedelta(days=95)

    db_session.add(_make_event(created_at=old_ts, task_type="job_fit"))
    # Also seed a daily rollup row that should remain untouched.
    day = _day_start(old_ts)
    db_session.add(AiUsageDaily(
        day=day,
        task_type="job_fit",
        provider="openrouter",
        model="deepseek/deepseek-r1",
        org_id=None,
        requests=5,
        errors=0,
        fallbacks=0,
        blocked=0,
        prompt_tokens=500,
        completion_tokens=200,
        cost_usd=0.01,
        latency_ms_sum=1500,
        latency_ms_count=5,
    ))
    await db_session.flush()

    deleted = await prune_ai_ops_events(db_session, older_than_days=90)
    await db_session.flush()

    assert deleted == 1
    # AiUsageDaily rows are untouched.
    daily_rows = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily_rows) == 1
    assert daily_rows[0].requests == 5


@pytest.mark.asyncio
async def test_prune_returns_zero_when_nothing_to_prune(db_session: AsyncSession) -> None:
    """When all events are within the retention window, nothing is deleted."""
    from app.ai.observability.maintenance import prune_ai_ops_events

    now = datetime.now(UTC)
    for _ in range(4):
        db_session.add(_make_event(created_at=now - timedelta(days=5), task_type="job_fit"))
    await db_session.flush()

    deleted = await prune_ai_ops_events(db_session, older_than_days=90)
    await db_session.flush()

    assert deleted == 0
    remaining = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(remaining) == 4


@pytest.mark.asyncio
async def test_prune_exact_boundary_is_exclusive(db_session: AsyncSession) -> None:
    """Events at exactly now - older_than_days are NOT deleted (boundary is exclusive).

    Uses a fixed ``_now`` to avoid clock drift between row creation and cutoff
    calculation.
    """
    from app.ai.observability.maintenance import prune_ai_ops_events

    fixed_now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)
    cutoff = fixed_now - timedelta(days=90)

    # Exactly at the boundary — must be kept (cutoff is strict less-than).
    db_session.add(_make_event(created_at=cutoff, task_type="job_fit"))
    # One second before the cutoff — must be deleted.
    db_session.add(_make_event(created_at=cutoff - timedelta(seconds=1),
                               task_type="job_fit"))
    await db_session.flush()

    deleted = await prune_ai_ops_events(db_session, older_than_days=90, _now=fixed_now)
    await db_session.flush()

    assert deleted == 1
    remaining = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(remaining) == 1
