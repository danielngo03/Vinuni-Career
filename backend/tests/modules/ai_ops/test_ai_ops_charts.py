"""Tests for the two new chart endpoints:

  GET /admin/ai-ops/timeseries
  GET /admin/ai-ops/error-heatmap

Coverage:
1. Non-superadmin → 403 on both endpoints.
2. timeseries: returns one row per day in range with correct sums from AiUsageDaily.
3. timeseries: gap days filled with zero rows (continuous axis).
4. timeseries: null p95 on days with no AiOpsEvent rows.
5. timeseries: known-seed p95 computed correctly via nearest-rank.
6. error-heatmap: groups by day+hour correctly with a seeded set.
7. error-heatmap: empty response when no events.
8. Neither endpoint leaks provider or model identity.

Run:
    cd backend && uv run pytest tests/modules/ai_ops/test_ai_ops_charts.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.observability.models import AiOpsEvent, AiUsageDaily
from app.main import app
from app.modules.auth.api.deps import get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _superadmin_principal(permissions: frozenset[str] = frozenset()) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        org_id=None,
        is_superadmin=True,
        permissions=permissions,
    )


def _student_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=frozenset(),
    )


def _make_auth(principal: Principal):  # type: ignore[return]
    from datetime import timedelta as td  # noqa: PLC0415

    claims = AccessClaims(
        user_id=principal.user_id or uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona=principal.persona,
        org_id=principal.org_id,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + td(minutes=30),
    )
    ctx = RequestContext(ip="127.0.0.1", user_agent="test")
    from app.modules.auth.api.deps import CurrentAuth  # noqa: PLC0415

    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def superadmin_client() -> AsyncIterator[AsyncClient]:
    principal = _superadmin_principal()
    auth = _make_auth(principal)
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    principal = _student_principal()
    auth = _make_auth(principal)
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# 1. Non-superadmin → 403 on both endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_superadmin_timeseries_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/timeseries")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_error_heatmap_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/error-heatmap")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# 2. timeseries: correct sums from AiUsageDaily
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_correct_sums(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed two AiUsageDaily rows for today and assert sums appear in the series."""
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for task in ("cv_bullets", "job_fit"):
        db_session.add(
            AiUsageDaily(
                day=today,
                task_type=task,
                provider="openrouter",
                model="deepseek/v4",
                requests=10,
                errors=2,
                fallbacks=0,
                prompt_tokens=500,
                completion_tokens=200,
                cost_usd=0.005,
                latency_ms_sum=2000,
                latency_ms_count=10,
            )
        )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/timeseries", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    series = body["data"]["series"]
    assert len(series) == 1  # range_days=1 → only today
    row = series[0]
    today_iso = today.date().isoformat()
    assert row["day"] == today_iso
    assert row["requests"] == 20   # 10 + 10
    assert row["errors"] == 4      # 2 + 2
    assert row["prompt_tokens"] == 1000
    assert row["completion_tokens"] == 400
    assert abs(row["cost_usd"] - 0.010) < 1e-6
    # avg_latency: (2000+2000) / (10+10) = 200.0
    assert row["avg_latency_ms"] is not None
    assert abs(row["avg_latency_ms"] - 200.0) < 0.01
    assert row["error_rate"] == pytest.approx(4 / 20)


# ---------------------------------------------------------------------------
# 3. timeseries: gap days filled with zero rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_gap_days_filled(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Over a 3-day window with data only on day 1, all 3 days must appear."""
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    two_days_ago = today - timedelta(days=2)

    # Seed only the oldest day
    db_session.add(
        AiUsageDaily(
            day=two_days_ago,
            task_type="gap_test",
            provider="",
            model="",
            requests=5,
            errors=0,
            fallbacks=0,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.001,
            latency_ms_sum=500,
            latency_ms_count=5,
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/timeseries", params={"range_days": 3})
    assert resp.status_code == 200, resp.text
    series = resp.json()["data"]["series"]
    assert len(series) == 3, f"Expected 3 days, got {len(series)}: {[s['day'] for s in series]}"

    two_days_ago_iso = two_days_ago.date().isoformat()
    oldest_row = next(s for s in series if s["day"] == two_days_ago_iso)
    assert oldest_row["requests"] == 5

    # Middle day and today should be zero-filled
    gap_rows = [s for s in series if s["day"] != two_days_ago_iso]
    for gap in gap_rows:
        assert gap["requests"] == 0
        assert gap["errors"] == 0
        assert gap["cost_usd"] == 0.0
        assert gap["avg_latency_ms"] is None
        assert gap["p95_latency_ms"] is None


# ---------------------------------------------------------------------------
# 4. timeseries: null p95 on days with no AiOpsEvent rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_null_p95_when_no_events(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When no AiOpsEvent rows exist, every day's p95_latency_ms must be None."""
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    db_session.add(
        AiUsageDaily(
            day=today,
            task_type="null_p95_test",
            provider="",
            model="",
            requests=3,
            errors=0,
            fallbacks=0,
            prompt_tokens=50,
            completion_tokens=20,
            cost_usd=0.0005,
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/timeseries", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    series = resp.json()["data"]["series"]
    assert len(series) >= 1
    for row in series:
        assert row["p95_latency_ms"] is None, f"Expected None, got {row['p95_latency_ms']}"


# ---------------------------------------------------------------------------
# 5. timeseries: known-seed p95 computed correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_known_seed_p95(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed 20 events for today with latencies 50..1000 (step 50).

    Nearest-rank p95: ceil(0.95 * 20) - 1 = ceil(19) - 1 = 18 → sorted[18] = 950.
    """
    now = datetime.now(tz=UTC)
    latencies = list(range(50, 1050, 50))  # 50, 100, ..., 1000 — 20 values
    assert len(latencies) == 20
    for lat in latencies:
        db_session.add(
            AiOpsEvent(
                id=uuid.uuid4(),
                created_at=now,
                task_type="p95_timeseries_test",
                alias="chat_default",
                provider=None,
                model=None,
                latency_ms=lat,
                status="ok",
                fallback_used=False,
                circuit_open=False,
                unpriced=True,
            )
        )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/timeseries", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    series = resp.json()["data"]["series"]
    today_iso = now.date().isoformat()
    today_row = next((s for s in series if s["day"] == today_iso), None)
    assert today_row is not None, f"No row for {today_iso} in series: {[s['day'] for s in series]}"
    # ceil(0.95 * 20) - 1 = 19 - 1 = 18 → latencies[18] = 950
    assert today_row["p95_latency_ms"] == 950, (
        f"Expected p95=950, got {today_row['p95_latency_ms']}"
    )


# ---------------------------------------------------------------------------
# 6. error-heatmap: groups by day+hour correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_heatmap_groups_by_day_hour(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed events at two distinct hours; assert cells match known day+hour counts."""
    # Pin to a specific hour so the test is not time-of-day-sensitive.
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    # hour 3: 4 requests, 2 errors (status="error")
    for i in range(4):
        db_session.add(
            AiOpsEvent(
                id=uuid.uuid4(),
                created_at=today.replace(hour=3, minute=i),
                task_type="heatmap_test",
                alias="chat_default",
                status="error" if i < 2 else "ok",
                fallback_used=False,
                circuit_open=False,
                unpriced=True,
            )
        )
    # hour 14: 3 requests, 0 errors
    for i in range(3):
        db_session.add(
            AiOpsEvent(
                id=uuid.uuid4(),
                created_at=today.replace(hour=14, minute=i),
                task_type="heatmap_test",
                alias="chat_default",
                status="ok",
                fallback_used=False,
                circuit_open=False,
                unpriced=True,
            )
        )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/error-heatmap", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    cells = resp.json()["data"]["cells"]

    today_iso = today.date().isoformat()
    cell_3 = next((c for c in cells if c["day"] == today_iso and c["hour"] == 3), None)
    cell_14 = next((c for c in cells if c["day"] == today_iso and c["hour"] == 14), None)

    assert cell_3 is not None, f"No cell for hour=3 on {today_iso}. cells={cells}"
    assert cell_3["requests"] == 4
    assert cell_3["errors"] == 2

    assert cell_14 is not None, f"No cell for hour=14 on {today_iso}. cells={cells}"
    assert cell_14["requests"] == 3
    assert cell_14["errors"] == 0


# ---------------------------------------------------------------------------
# 7. error-heatmap: empty when no events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_heatmap_empty_when_no_events(
    superadmin_client: AsyncClient,
) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/error-heatmap")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["cells"] == []


# ---------------------------------------------------------------------------
# 8. No provider/model leakage in either endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeseries_no_provider_model_fields(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """timeseries rows must never carry provider or model keys."""
    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    db_session.add(
        AiUsageDaily(
            day=today,
            task_type="leak_test",
            provider="openrouter",
            model="deepseek/v4",
            requests=1,
            errors=0,
            fallbacks=0,
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.0001,
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/timeseries", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    series = resp.json()["data"]["series"]
    for row in series:
        assert "provider" not in row, f"provider leaked in timeseries row: {row}"
        assert "model" not in row, f"model leaked in timeseries row: {row}"


@pytest.mark.asyncio
async def test_error_heatmap_no_provider_model_fields(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """error-heatmap cells must never carry provider or model keys."""
    now = datetime.now(tz=UTC)
    db_session.add(
        AiOpsEvent(
            id=uuid.uuid4(),
            created_at=now,
            task_type="heatmap_leak_test",
            alias="chat_default",
            provider="openrouter",
            model="deepseek/v4",
            status="ok",
            fallback_used=False,
            circuit_open=False,
            unpriced=False,
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/error-heatmap", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    cells = resp.json()["data"]["cells"]
    for cell in cells:
        assert "provider" not in cell, f"provider leaked in heatmap cell: {cell}"
        assert "model" not in cell, f"model leaked in heatmap cell: {cell}"
