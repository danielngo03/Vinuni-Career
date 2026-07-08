"""Tests for the ``permissions`` field in ``GET /auth/me``.

Coverage:
1. Normal (non-superadmin) user: ``permissions`` is a sorted list of their
   granted permission strings.
2. Superadmin user: ``permissions`` is exactly ``["*"]``.
3. The field is ADDITIVE — all existing /auth/me fields remain present.
4. The field is present even when the user has zero grants (empty list).

We use the FastAPI dependency-override pattern to inject a known
``CurrentAuth`` without needing a real JWT.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app  # noqa: E402
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.users.domain.models import Identity, User
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(user_id: uuid.UUID, identity_id: uuid.UUID) -> AccessClaims:
    return AccessClaims(
        user_id=user_id,
        session_id=uuid.uuid4(),
        identity_id=identity_id,
        persona="student",
        org_id=None,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
    )


def _make_auth(principal: Principal, identity_id: uuid.UUID) -> CurrentAuth:
    return CurrentAuth(
        principal=principal,
        claims=_make_claims(principal.user_id or uuid.uuid4(), identity_id),
        ctx=RequestContext(ip="127.0.0.1", user_agent="pytest/1.0"),
    )


async def _seed_user_with_identity(
    db: AsyncSession,
    *,
    email: str,
    is_superadmin: bool = False,
) -> tuple[User, Identity]:
    user = User(
        email=email,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified_at=datetime.now(tz=UTC),
    )
    db.add(user)
    await db.flush()
    identity = Identity(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_primary=True,
    )
    db.add(identity)
    await db.flush()
    return user, identity


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_normal_user_permissions_empty_list(db_session: AsyncSession) -> None:
    """A user with no grants gets an empty sorted permissions list."""
    user, identity = await _seed_user_with_identity(
        db_session, email="me_no_grants@example.com"
    )
    await db_session.commit()

    principal = Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=frozenset(),
    )
    auth = _make_auth(principal, identity.id)
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "permissions" in data
        assert data["permissions"] == []
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


@pytest.mark.asyncio
async def test_me_normal_user_permissions_sorted(db_session: AsyncSession) -> None:
    """A user with grants gets their permissions as a sorted list."""
    user, identity = await _seed_user_with_identity(
        db_session, email="me_with_grants@example.com"
    )
    await db_session.commit()

    principal = Principal(
        user_id=user.id,
        persona="partner_member",
        org_id=uuid.uuid4(),
        is_superadmin=False,
        permissions=frozenset({"jobs:read", "analytics:read", "candidates:view"}),
    )
    auth = _make_auth(principal, identity.id)
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "permissions" in data
        # Must be sorted
        assert data["permissions"] == sorted(["jobs:read", "analytics:read", "candidates:view"])
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


@pytest.mark.asyncio
async def test_me_superadmin_returns_wildcard(db_session: AsyncSession) -> None:
    """Superadmin gets exactly ``['*']`` regardless of their grants frozenset."""
    user, identity = await _seed_user_with_identity(
        db_session, email="me_superadmin@example.com", is_superadmin=True
    )
    await db_session.commit()

    principal = Principal(
        user_id=user.id,
        persona="superadmin",
        org_id=None,
        is_superadmin=True,
        # In real auth, superadmin permissions frozenset is empty (bypassed by can())
        permissions=frozenset(),
    )
    auth = _make_auth(principal, identity.id)
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "permissions" in data
        assert data["permissions"] == ["*"], f"Superadmin must get ['*'], got {data['permissions']}"
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


@pytest.mark.asyncio
async def test_me_permissions_additive_existing_fields_unchanged(
    db_session: AsyncSession,
) -> None:
    """Adding ``permissions`` must not remove or alter existing /auth/me fields."""
    user, identity = await _seed_user_with_identity(
        db_session, email="me_additive@example.com"
    )
    await db_session.commit()

    principal = Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=frozenset(),
    )
    auth = _make_auth(principal, identity.id)
    app.dependency_overrides[get_current_auth] = lambda: auth
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        # All existing fields must still be present
        assert "id" in data
        assert "email" in data
        assert data["email"] == "me_additive@example.com"
        assert "full_name" in data
        assert "preferred_language" in data
        assert "timezone" in data
        assert "email_verified" in data
        assert "is_superadmin" in data
        assert "active_identity" in data
        assert "persona" in data["active_identity"]

        # New field present
        assert "permissions" in data
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
