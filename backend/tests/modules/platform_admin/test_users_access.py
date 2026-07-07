"""Platform Admin P4a — Users & Access tests (strict TDD).

Coverage:
1.  Non-superadmin → 403 on ALL new endpoints.
2.  GET /admin/users/{id} returns the user_360 view; assert:
      - required top-level keys present
      - password_hash / ip_hash / raw ip / raw UA absent
3.  GET /admin/sessions returns ONLY active sessions across multiple users:
      - privacy-safe fields only (ip_hash absent)
      - revoked sessions excluded
      - expired sessions excluded
      - cursor pagination works (no-overlap between pages)
4.  POST /admin/sessions/{id}/revoke:
      - sets revoked_at on the session row
      - writes exactly ONE audit row with action="session.revoked_by_admin"
      - second call is idempotent (no additional audit row)
5.  POST /admin/users/{id}/suspend flips is_active=False and writes audit.
6.  POST /admin/users/{id}/unsuspend flips is_active=True and writes audit.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_users_access.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.core.db import get_sessionmaker
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.domain.models import Session
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.users.domain.models import Identity, User
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Principal / auth helpers (mirrors test_audit_read.py conventions)
# ---------------------------------------------------------------------------


def _superadmin_principal(user_id: uuid.UUID | None = None) -> Principal:
    return Principal(
        user_id=user_id or uuid.uuid4(),
        persona="superadmin",
        org_id=None,
        is_superadmin=True,
        permissions=frozenset(),
    )


def _student_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="student",
        org_id=uuid.uuid4(),
        is_superadmin=False,
        permissions=frozenset(),
    )


def _make_auth(principal: Principal) -> CurrentAuth:
    claims = AccessClaims(
        user_id=principal.user_id or uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona=principal.persona,
        org_id=principal.org_id,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
    )
    ctx = RequestContext(ip="127.0.0.1", user_agent="pytest-agent/1.0")
    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    is_active: bool = True,
    is_superadmin: bool = False,
) -> User:
    u = User(
        email=email or f"test+{uuid.uuid4().hex[:8]}@example.com",
        is_active=is_active,
        is_superadmin=is_superadmin,
        email_verified_at=datetime.now(tz=UTC),
    )
    db.add(u)
    await db.flush()
    # Add a primary identity so list_platform_users joins work
    identity = Identity(
        user_id=u.id,
        persona="student",
        org_id=None,
        is_primary=True,
    )
    db.add(identity)
    await db.flush()
    return u


def _active_session(user: User, *, offset_seconds: int = 0) -> Session:
    """Build an active (non-revoked, non-expired) Session ORM object."""
    now = datetime.now(tz=UTC)
    return Session(
        user_id=user.id,
        identity_id=uuid.uuid4(),
        device_hint="Chrome / macOS",
        ip_hash="sha256:abc123",  # stored hash — must NOT appear in API response
        city_level_location="Ha Noi",
        expires_at=now + timedelta(hours=1),
        last_seen_at=now - timedelta(seconds=offset_seconds),
        created_at=now - timedelta(minutes=10),
    )


def _revoked_session(user: User) -> Session:
    now = datetime.now(tz=UTC)
    s = _active_session(user)
    s.revoked_at = now - timedelta(minutes=5)
    s.revoked_reason = "remote_logout"
    return s


def _expired_session(user: User) -> Session:
    now = datetime.now(tz=UTC)
    s = Session(
        user_id=user.id,
        identity_id=uuid.uuid4(),
        device_hint="Firefox / Windows",
        ip_hash="sha256:def456",
        city_level_location=None,
        expires_at=now - timedelta(hours=2),  # already expired
        last_seen_at=now - timedelta(hours=3),
        created_at=now - timedelta(hours=4),
    )
    return s


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sa_client() -> AsyncIterator[AsyncClient]:
    """HTTP client authenticated as a superadmin."""
    sa_uid = uuid.uuid4()
    auth = _make_auth(_superadmin_principal(user_id=sa_uid))
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    """HTTP client authenticated as a non-superadmin student."""
    auth = _make_auth(_student_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Test 1 — Non-superadmin gets 403 on all new endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_superadmin_list_users_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/users")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_user_360_403(student_client: AsyncClient) -> None:
    resp = await student_client.get(f"/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_suspend_403(student_client: AsyncClient) -> None:
    resp = await student_client.post(f"/admin/users/{uuid.uuid4()}/suspend")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_unsuspend_403(student_client: AsyncClient) -> None:
    resp = await student_client.post(f"/admin/users/{uuid.uuid4()}/unsuspend")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_list_sessions_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/sessions")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_non_superadmin_revoke_session_403(student_client: AsyncClient) -> None:
    resp = await student_client.post(f"/admin/sessions/{uuid.uuid4()}/revoke")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Test 2 — GET /admin/users/{id} — user_360 view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_360_returns_expected_shape(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, email="alice@example.com")
    await db_session.commit()

    resp = await sa_client.get(f"/admin/users/{user.id}")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    data = body["data"]

    # Top-level keys
    assert "core" in data
    assert "identities" in data
    assert "active_session_count" in data
    assert "recent_ai_usage_count" in data

    # Core fields
    core = data["core"]
    assert core["id"] == str(user.id)
    assert core["email"] == "alice@example.com"
    assert "is_active" in core
    assert "is_superadmin" in core
    assert "email_verified" in core
    assert "created_at" in core

    # Forbidden fields — must NOT be present anywhere in the entire payload
    payload_str = resp.text
    assert "password_hash" not in payload_str
    assert "ip_hash" not in payload_str
    # raw token fields
    assert "token_hash" not in payload_str
    # user_agent as a raw value — device_hint is fine, "user_agent" key is not
    assert '"user_agent"' not in payload_str

    # Identities list
    assert isinstance(data["identities"], list)
    assert len(data["identities"]) >= 1
    identity_entry = data["identities"][0]
    assert "persona" in identity_entry
    assert "org_id" in identity_entry
    assert "is_primary" in identity_entry

    # Numeric counts
    assert isinstance(data["active_session_count"], int)
    assert isinstance(data["recent_ai_usage_count"], int)


@pytest.mark.asyncio
async def test_user_360_unknown_user_404(
    sa_client: AsyncClient,
) -> None:
    resp = await sa_client.get(f"/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 3 — GET /admin/sessions — active sessions, privacy-safe, cursor-paged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_only_active(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Revoked and expired sessions must NOT appear."""
    user_a = await _seed_user(db_session)
    user_b = await _seed_user(db_session)
    await db_session.flush()

    # 2 active, 1 revoked, 1 expired
    active_a = _active_session(user_a)
    active_b = _active_session(user_b)
    revoked = _revoked_session(user_a)
    expired = _expired_session(user_b)

    db_session.add_all([active_a, active_b, revoked, expired])
    await db_session.commit()

    resp = await sa_client.get("/admin/sessions")
    assert resp.status_code == 200, resp.text

    items = resp.json()["data"]
    session_ids = {item["session_id"] for item in items}

    assert str(active_a.id) in session_ids, "active_a must appear"
    assert str(active_b.id) in session_ids, "active_b must appear"
    assert str(revoked.id) not in session_ids, "revoked session must be excluded"
    assert str(expired.id) not in session_ids, "expired session must be excluded"


@pytest.mark.asyncio
async def test_list_sessions_privacy_safe_fields(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """ip_hash, raw ip, raw UA must NOT appear in the session list response."""
    user = await _seed_user(db_session)
    db_session.add(_active_session(user))
    await db_session.commit()

    resp = await sa_client.get("/admin/sessions")
    assert resp.status_code == 200

    payload_str = resp.text
    assert "ip_hash" not in payload_str
    assert "sha256:" not in payload_str  # stored hash value

    items = resp.json()["data"]
    assert len(items) >= 1
    item = items[0]

    # Required safe fields present
    assert "session_id" in item
    assert "user_id" in item
    assert "device_hint" in item
    assert "city_level_location" in item
    assert "last_seen_at" in item
    assert "created_at" in item
    assert "expires_at" in item

    # Forbidden fields absent from item keys
    assert "ip_hash" not in item
    assert "user_agent" not in item
    assert "token_hash" not in item


@pytest.mark.asyncio
async def test_list_sessions_user_email_enriched(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """user_email must be enriched (not None) for a known user."""
    user = await _seed_user(db_session, email="bob@example.com")
    db_session.add(_active_session(user))
    await db_session.commit()

    resp = await sa_client.get("/admin/sessions", params={"user_id": str(user.id)})
    assert resp.status_code == 200

    items = resp.json()["data"]
    assert len(items) == 1
    assert items[0]["user_email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_list_sessions_cursor_pagination_no_overlap(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed 5 active sessions, page with limit=3; pages must not overlap."""
    user = await _seed_user(db_session)
    for i in range(5):
        db_session.add(_active_session(user, offset_seconds=i * 10))
    await db_session.commit()

    resp1 = await sa_client.get("/admin/sessions", params={"limit": 3})
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert len(body1["data"]) == 3
    next_cursor = body1["page"]["next_cursor"]
    assert next_cursor is not None, "Expected next_cursor on first page"

    resp2 = await sa_client.get("/admin/sessions", params={"limit": 3, "cursor": next_cursor})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["data"]) >= 1

    ids1 = {item["session_id"] for item in body1["data"]}
    ids2 = {item["session_id"] for item in body2["data"]}
    assert ids1.isdisjoint(ids2), "Pages must not overlap"


# ---------------------------------------------------------------------------
# Test 4 — POST /admin/sessions/{id}/revoke — audited, idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_session_sets_revoked_at(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sess = _active_session(user)
    db_session.add(sess)
    await db_session.commit()
    session_id = sess.id

    resp = await sa_client.post(f"/admin/sessions/{session_id}/revoke")
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["session_id"] == str(session_id)
    assert data["newly_revoked"] is True

    # Open a fresh session to see the commit made by the service's own session.
    async with get_sessionmaker()() as fresh:
        refreshed = (
            await fresh.execute(select(Session).where(Session.id == session_id))
        ).scalar_one_or_none()
        assert refreshed is not None
        assert refreshed.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_session_writes_one_audit_row(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session)
    sess = _active_session(user)
    db_session.add(sess)
    await db_session.commit()
    session_id = sess.id

    resp = await sa_client.post(f"/admin/sessions/{session_id}/revoke")
    assert resp.status_code == 200

    # Fresh session to see committed audit rows.
    async with get_sessionmaker()() as fresh:
        rows = (
            await fresh.execute(
                select(AuditLog).where(
                    AuditLog.action == "session.revoked_by_admin",
                    AuditLog.resource_id == session_id,
                )
            )
        ).scalars().all()
    assert len(rows) == 1, f"Expected exactly 1 audit row, got {len(rows)}"


@pytest.mark.asyncio
async def test_revoke_session_idempotent_no_extra_audit(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Second revoke call is idempotent — no additional audit row created."""
    user = await _seed_user(db_session)
    sess = _active_session(user)
    db_session.add(sess)
    await db_session.commit()
    session_id = sess.id

    # First call
    resp1 = await sa_client.post(f"/admin/sessions/{session_id}/revoke")
    assert resp1.status_code == 200
    assert resp1.json()["data"]["newly_revoked"] is True

    # Second call — idempotent
    resp2 = await sa_client.post(f"/admin/sessions/{session_id}/revoke")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["newly_revoked"] is False

    # Fresh session — still exactly 1 audit row.
    async with get_sessionmaker()() as fresh:
        rows = (
            await fresh.execute(
                select(AuditLog).where(
                    AuditLog.action == "session.revoked_by_admin",
                    AuditLog.resource_id == session_id,
                )
            )
        ).scalars().all()
    assert len(rows) == 1, f"Idempotent second revoke must not add audit row; got {len(rows)}"


@pytest.mark.asyncio
async def test_revoke_unknown_session_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(f"/admin/sessions/{uuid.uuid4()}/revoke")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 5 & 6 — suspend / unsuspend flip is_active and write audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspend_flips_is_active_and_audits(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, is_active=True)
    await db_session.commit()

    resp = await sa_client.post(f"/admin/users/{user.id}/suspend")
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["is_active"] is False

    # DB row
    await db_session.refresh(user)
    assert user.is_active is False

    # Audit row written
    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user.suspended",
                AuditLog.resource_id == user.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1, f"Expected 1 suspend audit row, got {len(rows)}"
    assert rows[0].after_snapshot == {"is_active": False}


@pytest.mark.asyncio
async def test_unsuspend_flips_is_active_and_audits(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _seed_user(db_session, is_active=False)
    await db_session.commit()

    resp = await sa_client.post(f"/admin/users/{user.id}/unsuspend")
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["is_active"] is True

    await db_session.refresh(user)
    assert user.is_active is True

    rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user.unsuspended",
                AuditLog.resource_id == user.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1, f"Expected 1 unsuspend audit row, got {len(rows)}"
    assert rows[0].after_snapshot == {"is_active": True}


@pytest.mark.asyncio
async def test_suspend_unknown_user_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(f"/admin/users/{uuid.uuid4()}/suspend")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test — GET /admin/users list (superadmin wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_returns_paginated_shape(
    sa_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _seed_user(db_session, email="list_test_1@example.com")
    await _seed_user(db_session, email="list_test_2@example.com")
    await db_session.commit()

    resp = await sa_client.get("/admin/users")
    assert resp.status_code == 200

    body = resp.json()
    # success() wraps in {"data": {...}}; the inner dict has items/total/page keys
    assert "data" in body
    inner = body["data"]
    assert "items" in inner
    assert "total" in inner
    assert "page" in inner
    assert "page_size" in inner
    assert "total_pages" in inner
    assert isinstance(inner["items"], list)
    assert inner["total"] >= 2
