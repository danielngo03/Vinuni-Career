"""HTTP-level tests for GET /admin/overview — superadmin platform read model.

Coverage:
1. Superadmin GET /admin/overview → 200 with keys ai, outbox, moderation_pending,
   active_users.
2. Non-superadmin → 403.
3. One sub-query failing → endpoint still returns 200 with a safe fallback for
   that section (not 500).

Auth is injected via FastAPI dependency overrides to avoid needing a real
JWT/session stack.  Overrides are scoped to each test and cleaned up in fixture
teardown so they never leak.

Run:
    cd backend && uv run pytest tests/modules/dashboards/test_platform_overview.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Principal helpers (mirror the ai_ops test conventions)
# ---------------------------------------------------------------------------


def _superadmin_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        org_id=None,
        is_superadmin=True,
        permissions=frozenset(),
    )


def _student_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=frozenset(),
    )


def _make_current_auth(principal: Principal) -> CurrentAuth:
    claims = AccessClaims(
        user_id=principal.user_id or uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona=principal.persona,
        org_id=principal.org_id,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
    )
    ctx = RequestContext(ip="127.0.0.1", user_agent="test")
    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def superadmin_client() -> AsyncIterator[AsyncClient]:
    """Client whose auth resolves to a platform superadmin."""
    principal = _superadmin_principal()
    auth = _make_current_auth(principal)

    app.dependency_overrides[get_current_auth] = lambda: auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    """Client whose auth resolves to a regular student (not superadmin)."""
    principal = _student_principal()
    auth = _make_current_auth(principal)

    app.dependency_overrides[get_current_auth] = lambda: auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Test 1: Superadmin → 200 with all required keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_superadmin_overview_200_with_required_keys(
    superadmin_client: AsyncClient,
) -> None:
    resp = await superadmin_client.get("/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Top-level sections must all be present.
    assert "ai" in data, f"Missing 'ai' key in: {list(data.keys())}"
    assert "outbox" in data, f"Missing 'outbox' key in: {list(data.keys())}"
    assert "moderation_pending" in data, "Missing 'moderation_pending' key"
    assert "active_users" in data, "Missing 'active_users' key"

    # ai section keys.
    ai = data["ai"]
    assert "spend_today" in ai
    assert "budget" in ai
    assert "error_rate" in ai
    assert "requests" in ai

    # Scalar types — no raw strings or provider internals.
    assert isinstance(data["moderation_pending"], int)
    assert isinstance(data["active_users"], int)


# ---------------------------------------------------------------------------
# Test 2: Non-superadmin → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/overview")
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Test 3: One sub-query failing → 200 with safe fallback (no 500)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_failing_subquery_returns_200_with_fallback(
    superadmin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate moderation count raising; endpoint must return 200 with fallback 0."""
    from app.modules.opportunities.application import dashboard_read as opp_read

    async def _raise(*args: object, **kwargs: object) -> int:
        raise RuntimeError("injected moderation failure")

    monkeypatch.setattr(opp_read, "count_pending_moderation_jobs", _raise)

    resp = await superadmin_client.get("/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # The failed section falls back to 0 — no 500 raised.
    assert data["moderation_pending"] == 0

    # Other sections still return something (not necessarily non-zero, but present).
    assert "ai" in data
    assert "outbox" in data
    assert "active_users" in data


# ---------------------------------------------------------------------------
# Test 4: ai sub-query failing → 200 with safe fallback {}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_failing_subquery_returns_200_with_fallback(
    superadmin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate ai_ops_read_service.overview raising; endpoint must return 200 with fallback {}."""
    from app.modules.ai_ops.application import ai_ops_read_service

    async def _raise(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("injected ai failure")

    monkeypatch.setattr(ai_ops_read_service, "overview", _raise)

    resp = await superadmin_client.get("/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # The failed section falls back to {} — no 500 raised.
    assert data["ai"] == {}

    # Other sections still present.
    assert "outbox" in data
    assert "moderation_pending" in data
    assert "active_users" in data


# ---------------------------------------------------------------------------
# Test 5: outbox sub-query failing → 200 with safe fallback {}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outbox_failing_subquery_returns_200_with_fallback(
    superadmin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate dispatch_service.status_counts raising; endpoint must return 200 with fallback."""
    from app.modules.notifications.application import dispatch_service

    async def _raise(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(dispatch_service, "status_counts", _raise)

    resp = await superadmin_client.get("/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # The failed section falls back to {} — no 500 raised.
    assert data["outbox"] == {}

    # Other sections still present.
    assert "ai" in data
    assert "moderation_pending" in data
    assert "active_users" in data
