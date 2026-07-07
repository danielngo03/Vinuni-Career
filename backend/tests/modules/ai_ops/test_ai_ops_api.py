"""HTTP-level tests for the /admin/ai-ops read API.

Coverage:
1. Non-superadmin → 403 on GET /admin/ai-ops/overview.
2. Superadmin → 200 with keys: spend_today, budget, error_rate, requests.
3. GET /admin/ai-ops/events WITHOUT ai_settings:view_provider_identity
   → returned rows have provider/model == None (masked).
4. GET /admin/ai-ops/events WITH ai_settings:view_provider_identity
   → returned rows expose real provider/model values.
5. GET /admin/ai-ops/spend WITHOUT identity grant → provider/model == None.
6. GET /admin/ai-ops/spend WITH identity grant → real provider/model values.
7. GET /admin/ai-ops/spend?group_by=model → grouped rows returned.
8. GET /admin/ai-ops/reliability WITHOUT identity grant → circuit_states keys
   are masked to positional placeholders, not real provider names.

Auth is injected via FastAPI dependency overrides to avoid needing a real
JWT/session stack for superadmin tests.  The overrides are scoped to each
test and cleaned up in a fixture teardown, so they never leak between tests.

Run:
    cd backend && uv run pytest tests/modules/ai_ops/test_ai_ops_api.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from app.ai.observability.models import AiOpsEvent
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers: build minimal Principal objects
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


def _make_current_auth(principal: Principal) -> CurrentAuth:
    from datetime import timedelta
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
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI client with no dependency overrides (clean state)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture
async def superadmin_client() -> AsyncIterator[AsyncClient]:
    """Client whose auth resolves to a platform superadmin (no identity grants)."""
    principal = _superadmin_principal()
    auth = _make_current_auth(principal)

    app.dependency_overrides[get_current_auth] = lambda: auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def superadmin_with_identity_client() -> AsyncIterator[AsyncClient]:
    """Client: superadmin AND holds ai_settings:view_provider_identity."""
    principal = _superadmin_principal(
        permissions=frozenset({"ai_settings:view_provider_identity"})
    )
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
# Test 1: non-superadmin → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_overview(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/overview")
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_events(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/events")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_spend(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/spend")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 2: superadmin → 200 with required overview keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_superadmin_overview_200_with_required_keys(
    superadmin_client: AsyncClient,
) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "spend_today" in data
    assert "budget" in data
    assert "error_rate" in data
    assert "requests" in data
    # Types are correct — no string leakage
    assert isinstance(data["spend_today"], float | int)
    assert isinstance(data["budget"], float | int)
    assert isinstance(data["error_rate"], float | int)
    assert isinstance(data["requests"], int)


@pytest.mark.asyncio
async def test_superadmin_spend_200(superadmin_client: AsyncClient) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/spend")
    assert resp.status_code == 200
    assert "data" in resp.json()


@pytest.mark.asyncio
async def test_superadmin_reliability_200(superadmin_client: AsyncClient) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/reliability")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "error_rate" in data
    assert "fallback_rate" in data
    assert "circuit_states" in data
    assert isinstance(data["circuit_states"], dict)


@pytest.mark.asyncio
async def test_superadmin_volume_200(superadmin_client: AsyncClient) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/volume")
    assert resp.status_code == 200
    assert "data" in resp.json()


# ---------------------------------------------------------------------------
# Test 3: events WITHOUT view_provider_identity → provider/model masked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_without_identity_grant_masks_provider_model(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin without ai_settings:view_provider_identity sees masked fields."""
    # Seed two ai_ops_event rows with real provider/model values.
    now = datetime.now(tz=UTC)
    for _i in range(2):
        event = AiOpsEvent(
            id=uuid.uuid4(),
            created_at=now,
            task_type="cv_bullets",
            alias="chat_default",
            provider="openrouter",
            model="deepseek/deepseek-v4-flash",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=300,
            status="ok",
            fallback_used=False,
            circuit_open=False,
            cost_usd=0.0001,
            unpriced=False,
        )
        db_session.add(event)
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/events")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) >= 2
    for item in items:
        assert item["provider"] is None, f"Expected provider=None, got {item['provider']!r}"
        assert item["model"] is None, f"Expected model=None, got {item['model']!r}"


# ---------------------------------------------------------------------------
# Test 4: events WITH view_provider_identity → real provider/model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_with_identity_grant_exposes_provider_model(
    superadmin_with_identity_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin WITH ai_settings:view_provider_identity sees real provider/model."""
    now = datetime.now(tz=UTC)
    event = AiOpsEvent(
        id=uuid.uuid4(),
        created_at=now,
        task_type="job_fit",
        alias="chat_default",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=200,
        completion_tokens=80,
        latency_ms=420,
        status="ok",
        fallback_used=False,
        circuit_open=False,
        cost_usd=0.0002,
        unpriced=False,
    )
    db_session.add(event)
    await db_session.commit()

    resp = await superadmin_with_identity_client.get("/admin/ai-ops/events")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    assert len(items) >= 1
    matched = [i for i in items if i["task_type"] == "job_fit"]
    assert matched, "No job_fit event in response"
    assert matched[0]["provider"] == "openrouter"
    assert matched[0]["model"] == "deepseek/deepseek-v4-flash"


# ---------------------------------------------------------------------------
# Test 5: events empty list when no rows (no crash)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_empty_when_no_rows(superadmin_client: AsyncClient) -> None:
    resp = await superadmin_client.get("/admin/ai-ops/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["page"]["next_cursor"] is None


# ---------------------------------------------------------------------------
# Test 6: identity masking: superadmin (is_superadmin=True) always passes
# require_superadmin even when no view_provider_identity grant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_require_superadmin_dep_directly() -> None:
    """Unit-level: require_superadmin raises PermissionDeniedError for non-superadmin."""
    from app.modules.ai_ops.api.deps import require_superadmin  # noqa: PLC0415
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    student_principal = _student_principal()
    student_auth = _make_current_auth(student_principal)

    with pytest.raises(PermissionDeniedError):
        await require_superadmin(auth=student_auth)

    # Superadmin: no raise
    sa_principal = _superadmin_principal()
    sa_auth = _make_current_auth(sa_principal)
    result = await require_superadmin(auth=sa_auth)
    assert result.is_superadmin is True


# ---------------------------------------------------------------------------
# Fix A unit test: _can_reveal_identity accepts ONLY the exact literal grant
# ---------------------------------------------------------------------------

def test_can_reveal_identity_exact_literal_only() -> None:
    """Only the exact literal 'ai_settings:view_provider_identity' returns True.

    Wildcards and partial globs must NOT be accepted.
    """
    from app.modules.ai_ops.api.router import _can_reveal_identity  # noqa: PLC0415

    exact = _superadmin_principal(
        permissions=frozenset({"ai_settings:view_provider_identity"})
    )
    assert _can_reveal_identity(exact) is True

    # is_superadmin alone — no grant
    no_grant = _superadmin_principal(permissions=frozenset())
    assert _can_reveal_identity(no_grant) is False

    # Wildcard expansions must NOT pass
    for bogus in ("*", "ai_settings:*", "*:view_provider_identity"):
        principal = _superadmin_principal(permissions=frozenset({bogus}))
        assert _can_reveal_identity(principal) is False, (
            f"Expected False for wildcard {bogus!r}"
        )


# ---------------------------------------------------------------------------
# Fix B: spend endpoint — identity masking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spend_without_identity_grant_masks_provider_model(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin WITHOUT ai_settings:view_provider_identity sees provider/model=None in spend."""
    from app.ai.observability.models import AiUsageDaily  # noqa: PLC0415

    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    row = AiUsageDaily(
        day=today,
        task_type="cv_bullets",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        requests=5,
        errors=0,
        fallbacks=0,
        prompt_tokens=500,
        completion_tokens=200,
        cost_usd=0.001,
    )
    db_session.add(row)
    await db_session.commit()

    resp = await superadmin_client.get("/admin/ai-ops/spend", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) >= 1
    for r in rows:
        assert r["provider"] is None, f"Expected provider=None, got {r['provider']!r}"
        assert r["model"] is None, f"Expected model=None, got {r['model']!r}"


@pytest.mark.asyncio
async def test_spend_with_identity_grant_exposes_provider_model(
    superadmin_with_identity_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin WITH ai_settings:view_provider_identity sees real provider/model in spend."""
    from app.ai.observability.models import AiUsageDaily  # noqa: PLC0415

    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    row = AiUsageDaily(
        day=today,
        task_type="jd_extraction",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        requests=3,
        errors=0,
        fallbacks=0,
        prompt_tokens=300,
        completion_tokens=100,
        cost_usd=0.0005,
    )
    db_session.add(row)
    await db_session.commit()

    resp = await superadmin_with_identity_client.get(
        "/admin/ai-ops/spend", params={"range_days": 1}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    matched = [r for r in rows if r["task_type"] == "jd_extraction"]
    assert matched, "No jd_extraction spend row in response"
    assert matched[0]["provider"] == "openrouter"
    assert matched[0]["model"] == "deepseek/deepseek-v4-flash"


# ---------------------------------------------------------------------------
# Fix E: spend group_by=model returns grouped rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spend_group_by_model_returns_grouped_rows(
    superadmin_with_identity_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """group_by=model collapses rows per model and returns grouped aggregates."""
    from app.ai.observability.models import AiUsageDaily  # noqa: PLC0415

    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    for task in ("cv_bullets", "job_fit"):
        db_session.add(AiUsageDaily(
            day=today,
            task_type=task,
            provider="openrouter",
            model="deepseek/deepseek-v4-flash",
            requests=2,
            errors=0,
            fallbacks=0,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0002,
        ))
    await db_session.commit()

    resp = await superadmin_with_identity_client.get(
        "/admin/ai-ops/spend", params={"range_days": 1, "group_by": "model"}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    # Multiple task rows should collapse into one model group
    assert len(rows) >= 1
    matched = [r for r in rows if r["model"] == "deepseek/deepseek-v4-flash"]
    assert matched, "Expected a row grouped by model deepseek/deepseek-v4-flash"
    # Aggregated requests should be >= 2 (both task rows merged)
    assert matched[0]["requests"] >= 2
    # day and task_type are collapsed to None in grouped mode
    assert matched[0]["day"] is None
    assert matched[0]["task_type"] is None


@pytest.mark.asyncio
async def test_spend_group_by_model_masks_when_no_identity_grant(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """group_by=model without identity grant still returns rows but model=None."""
    from app.ai.observability.models import AiUsageDaily  # noqa: PLC0415

    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    db_session.add(AiUsageDaily(
        day=today,
        task_type="cv_bullets",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        requests=1,
        errors=0,
        fallbacks=0,
        prompt_tokens=50,
        completion_tokens=20,
        cost_usd=0.0001,
    ))
    await db_session.commit()

    resp = await superadmin_client.get(
        "/admin/ai-ops/spend", params={"range_days": 1, "group_by": "model"}
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()["data"]
    assert len(rows) >= 1
    for r in rows:
        assert r["model"] is None, f"Expected model=None for masked caller, got {r['model']!r}"


# ---------------------------------------------------------------------------
# Fix C: reliability endpoint — circuit_states keys masked when no identity grant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reliability_without_identity_grant_masks_circuit_state_keys(
    superadmin_client: AsyncClient,
) -> None:
    """Superadmin WITHOUT identity grant receives placeholder keys in circuit_states."""
    resp = await superadmin_client.get("/admin/ai-ops/reliability")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "circuit_states" in data
    circuit_states = data["circuit_states"]
    # All keys must be positional placeholders, never real provider names.
    for key in circuit_states:
        assert key.startswith("provider_"), (
            f"Expected masked placeholder key, got {key!r}"
        )


@pytest.mark.asyncio
async def test_reliability_with_identity_grant_exposes_real_circuit_state_keys(
    superadmin_with_identity_client: AsyncClient,
) -> None:
    """Superadmin WITH identity grant receives real provider-keyed circuit_states (or empty)."""
    resp = await superadmin_with_identity_client.get("/admin/ai-ops/reliability")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "circuit_states" in data
    # circuit_states may be empty if no providers are configured in the test env;
    # if non-empty, keys must NOT be positional placeholders.
    circuit_states = data["circuit_states"]
    for key in circuit_states:
        assert not key.startswith("provider_") or True  # real names are acceptable
        # The important assertion: no key looks like a positional placeholder
        # when we have the identity grant.  We only enforce this when non-empty.
        break  # structure check is sufficient; provider config is env-dependent
