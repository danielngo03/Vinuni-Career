"""Tests for audited model-price CRUD at /admin/ai-ops/prices.

Coverage:
1. Superadmin POST /admin/ai-ops/prices creates a row AND writes ONE AuditLog
   with action="ai_model_price.created".
2. PATCH /admin/ai-ops/prices/{price_id} updates the row AND writes one
   AuditLog with action="ai_model_price.updated".
3. Non-superadmin → 403 on POST and PATCH.
4. Negative price → 422 validation error on POST.
5. GET /admin/ai-ops/prices returns all rows for superadmin.
6. Non-superadmin → 403 on GET.

Auth is injected via FastAPI dependency overrides (same pattern as
test_ai_ops_api.py).  The conftest db_session fixture provides a clean
table-per-test via the autouse _clean_tables fixture.

Run:
    cd backend && uv run pytest tests/modules/ai_ops/test_pricing_admin.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.observability.models import AiModelPrice
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers: build minimal Principal objects  (same as test_ai_ops_api.py)
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
    claims = AccessClaims(
        user_id=principal.user_id or uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona=principal.persona,
        org_id=principal.org_id,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
    )
    ctx = RequestContext(ip="127.0.0.1", user_agent="test-agent")
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
# Test 1: POST creates a row and writes one audit log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_price_creates_row_and_audit_log(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /admin/ai-ops/prices → 201, row created, audit log written."""
    payload = {
        "provider": "openrouter",
        "model": "deepseek/deepseek-v4-flash",
        "input_usd_per_1k": 0.00014,
        "output_usd_per_1k": 0.00028,
        "active": True,
    }

    resp = await superadmin_client.post("/admin/ai-ops/prices", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["provider"] == "openrouter"
    assert data["model"] == "deepseek/deepseek-v4-flash"
    assert data["active"] is True
    price_id = data["id"]

    # Exactly one audit log row with action="ai_model_price.created"
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_model_price.created")
    )
    audit_rows = result.scalars().all()
    assert len(audit_rows) == 1, f"Expected 1 audit row, got {len(audit_rows)}"
    audit = audit_rows[0]
    assert audit.resource_type == "ai_model_price"
    assert str(audit.resource_id) == price_id
    # before snapshot is None for create; after snapshot contains new values
    assert audit.before_snapshot is None
    assert audit.after_snapshot is not None
    assert audit.after_snapshot["provider"] == "openrouter"


# ---------------------------------------------------------------------------
# Test 2: PATCH updates the row and writes one audit log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_price_updates_row_and_audit_log(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """PATCH /admin/ai-ops/prices/{id} → 200, row updated, audit log written."""
    # First create a row
    create_payload = {
        "provider": "openrouter",
        "model": "gpt-4o-mini",
        "input_usd_per_1k": 0.00015,
        "output_usd_per_1k": 0.0006,
        "active": True,
    }
    create_resp = await superadmin_client.post("/admin/ai-ops/prices", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    price_id = create_resp.json()["data"]["id"]

    # Now patch it
    patch_payload = {"input_usd_per_1k": 0.00020, "active": False}
    patch_resp = await superadmin_client.patch(
        f"/admin/ai-ops/prices/{price_id}", json=patch_payload
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()["data"]
    assert float(updated["input_usd_per_1k"]) == pytest.approx(0.00020, rel=1e-4)
    assert updated["active"] is False

    # Exactly one audit log row with action="ai_model_price.updated"
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_model_price.updated")
    )
    audit_rows = result.scalars().all()
    assert len(audit_rows) == 1, f"Expected 1 updated audit row, got {len(audit_rows)}"
    audit = audit_rows[0]
    assert audit.resource_type == "ai_model_price"
    assert str(audit.resource_id) == price_id
    # before/after snapshots carry the changed fields
    assert audit.before_snapshot is not None
    assert audit.after_snapshot is not None
    # The changed fields must appear in the diff
    assert "input_usd_per_1k" in audit.before_snapshot or "input_usd_per_1k" in audit.after_snapshot
    assert "active" in audit.before_snapshot or "active" in audit.after_snapshot


# ---------------------------------------------------------------------------
# Test 3: non-superadmin → 403 on POST and PATCH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_post(student_client: AsyncClient) -> None:
    payload = {
        "provider": "openrouter",
        "model": "some-model",
        "input_usd_per_1k": 0.001,
        "output_usd_per_1k": 0.002,
    }
    resp = await student_client.post("/admin/ai-ops/prices", json=payload)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_patch(
    db_session: AsyncSession,
) -> None:
    # Seed a price row directly — avoids conflicting dependency overrides in one test.
    row = AiModelPrice(
        id=uuid.uuid4(),
        provider="openrouter",
        model="patch-test-model",
        input_usd_per_1k=0.001,
        output_usd_per_1k=0.002,
        active=True,
    )
    db_session.add(row)
    await db_session.commit()
    price_id = str(row.id)

    # Now test with student client only (no superadmin override conflict).
    principal = _student_principal()
    auth = _make_current_auth(principal)
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
            resp = await c.patch(f"/admin/ai-ops/prices/{price_id}", json={"active": False})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Test 4: negative price → 422 validation error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_negative_input_price_returns_422(superadmin_client: AsyncClient) -> None:
    payload = {
        "provider": "openrouter",
        "model": "some-model",
        "input_usd_per_1k": -0.001,
        "output_usd_per_1k": 0.002,
    }
    resp = await superadmin_client.post("/admin/ai-ops/prices", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_negative_output_price_returns_422(superadmin_client: AsyncClient) -> None:
    payload = {
        "provider": "openrouter",
        "model": "some-model",
        "input_usd_per_1k": 0.001,
        "output_usd_per_1k": -0.002,
    }
    resp = await superadmin_client.post("/admin/ai-ops/prices", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 5: GET /admin/ai-ops/prices returns all rows for superadmin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_prices_returns_rows_for_superadmin(
    superadmin_client: AsyncClient,
) -> None:
    # Seed two rows
    for model in ("model-a", "model-b"):
        r = await superadmin_client.post(
            "/admin/ai-ops/prices",
            json={
                "provider": "openrouter",
                "model": model,
                "input_usd_per_1k": 0.001,
                "output_usd_per_1k": 0.002,
            },
        )
        assert r.status_code == 201

    resp = await superadmin_client.get("/admin/ai-ops/prices")
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert len(items) >= 2
    models = {item["model"] for item in items}
    assert "model-a" in models
    assert "model-b" in models


# ---------------------------------------------------------------------------
# Test 6: non-superadmin → 403 on GET
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_superadmin_gets_403_on_get(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/ai-ops/prices")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
