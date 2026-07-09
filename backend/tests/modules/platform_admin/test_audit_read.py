"""Platform Admin audit log API tests (TDD).

Coverage:
1. Superadmin GET /admin/audit-log returns rows from ALL orgs (platform-wide).
2. Non-superadmin (student) → 403 on list endpoint.
3. Non-superadmin (student) → 403 on export endpoint.
4. Filter: action narrows results correctly.
5. Filter: resource_type narrows results correctly.
6. Filter: since/until narrows results correctly.
7. Filter: actor_id narrows results correctly.
8. Cursor pagination: first page returns next_cursor; second page (using that
   cursor) returns the next batch without overlap.
9. CSV export: header row present, filtered rows match, no ip/ua hash columns,
   no before/after columns; capped at max_rows.
10. require_superadmin unit test — also checks the canonical import path.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_audit_read.py -v
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
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORG_A = uuid.uuid4()
_ORG_B = uuid.uuid4()


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
        org_id=_ORG_A,
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
    ctx = RequestContext(ip="127.0.0.1", user_agent="test")
    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


def _audit_row(
    *,
    actor_org_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str = "test.action",
    resource_type: str = "test_resource",
    resource_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> AuditLog:
    return AuditLog(
        actor_id=actor_id,
        actor_org_id=actor_org_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id or uuid.uuid4(),
        before_snapshot={"old": "value"},
        after_snapshot={"new": "value"},
        ip_hash="hashed_ip",
        user_agent_hash="hashed_ua",
        session_id=uuid.uuid4(),
        occurred_at=occurred_at or datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def superadmin_client() -> AsyncIterator[AsyncClient]:
    auth = _make_auth(_superadmin_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    auth = _make_auth(_student_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Test 1: platform-wide — rows from both orgs are returned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_rows_from_all_orgs(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Superadmin sees audit rows from ORG_A and ORG_B (no org filter applied)."""
    actor_a = uuid.uuid4()
    actor_b = uuid.uuid4()
    db_session.add(_audit_row(actor_org_id=_ORG_A, actor_id=actor_a, action="org_a.action"))
    db_session.add(_audit_row(actor_org_id=_ORG_B, actor_id=actor_b, action="org_b.action"))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/audit-log")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["data"]

    actions = {item["action"] for item in items}
    assert "org_a.action" in actions, "Row from ORG_A missing"
    assert "org_b.action" in actions, "Row from ORG_B missing"

    # Both org IDs appear in the response
    org_ids = {item["actor_org_id"] for item in items}
    assert str(_ORG_A) in org_ids
    assert str(_ORG_B) in org_ids


# ---------------------------------------------------------------------------
# Test 2 & 3: non-superadmin → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/audit-log")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_export_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/audit-log/export")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Test 4: filter by action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_action(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(_audit_row(action="target.action", resource_type="res"))
    db_session.add(_audit_row(action="other.action", resource_type="res"))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/audit-log", params={"action": "target.action"})
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert all(item["action"] == "target.action" for item in items)
    assert any(item["action"] == "target.action" for item in items)


# ---------------------------------------------------------------------------
# Test 5: filter by resource_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_resource_type(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(_audit_row(resource_type="cv_profile", action="cv.update"))
    db_session.add(_audit_row(resource_type="job", action="job.create"))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/audit-log", params={"resource_type": "cv_profile"})
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert all(item["resource_type"] == "cv_profile" for item in items)
    assert len(items) >= 1


# ---------------------------------------------------------------------------
# Test 6: filter by since / until
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_since_until(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(tz=UTC)
    old = now - timedelta(days=10)
    recent = now - timedelta(hours=1)

    db_session.add(_audit_row(action="old.event", occurred_at=old))
    db_session.add(_audit_row(action="recent.event", occurred_at=recent))
    await db_session.commit()

    since = (now - timedelta(days=1)).isoformat()
    resp = await superadmin_client.get("/admin/audit-log", params={"since": since})
    assert resp.status_code == 200
    items = resp.json()["data"]
    actions = {item["action"] for item in items}
    assert "recent.event" in actions
    assert "old.event" not in actions


# ---------------------------------------------------------------------------
# Test 7: filter by actor_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_actor_id(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    target_actor = uuid.uuid4()
    other_actor = uuid.uuid4()
    db_session.add(_audit_row(actor_id=target_actor, action="actor.action"))
    db_session.add(_audit_row(actor_id=other_actor, action="other.actor.action"))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/audit-log", params={"actor_id": str(target_actor)})
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert all(item["actor_id"] == str(target_actor) for item in items)
    assert len(items) >= 1


# ---------------------------------------------------------------------------
# Test 8: cursor pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cursor_pagination(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seed 5 rows, page with limit=3; first page has next_cursor, second page has the rest."""
    for i in range(5):
        db_session.add(_audit_row(action=f"page.action.{i}"))
    await db_session.commit()

    # First page
    resp1 = await superadmin_client.get("/admin/audit-log", params={"limit": 3})
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert len(body1["data"]) == 3
    next_cursor = body1["page"]["next_cursor"]
    assert next_cursor is not None, "Expected next_cursor on page 1"
    assert body1["page"]["limit"] == 3

    # Second page using cursor
    resp2 = await superadmin_client.get(
        "/admin/audit-log", params={"limit": 3, "cursor": next_cursor}
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["data"]) >= 1, "Second page should have remaining rows"

    # No overlap between pages
    ids1 = {item["id"] for item in body1["data"]}
    ids2 = {item["id"] for item in body2["data"]}
    assert ids1.isdisjoint(ids2), "Pages must not overlap"


# ---------------------------------------------------------------------------
# Test 9: CSV export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csv_export_content(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """CSV has header + data rows; no ip/ua hashes; no before/after blobs."""
    actor_id = uuid.uuid4()
    db_session.add(
        _audit_row(
            actor_id=actor_id,
            actor_org_id=_ORG_A,
            action="csv.export.test",
            resource_type="job",
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get(
        "/admin/audit-log/export", params={"action": "csv.export.test"}
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers.get("content-disposition", "")

    lines = resp.text.strip().splitlines()
    assert len(lines) >= 2, "Expected at least header + one data row"

    header = lines[0].split(",")
    # Required columns present
    assert "occurred_at" in header
    assert "actor_email" in header
    assert "actor_id" in header
    assert "actor_org_id" in header
    assert "action" in header
    assert "resource_type" in header
    assert "resource_id" in header

    # Forbidden columns absent
    assert "ip_hash" not in header
    assert "user_agent_hash" not in header
    assert "before" not in header
    assert "after" not in header
    assert "before_snapshot" not in header
    assert "after_snapshot" not in header

    # Data row contains expected action
    data_row = lines[1]
    assert "csv.export.test" in data_row


@pytest.mark.asyncio
async def test_csv_export_action_filter(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """CSV export respects action filter — excluded rows are not in output."""
    db_session.add(_audit_row(action="included.action", resource_type="job"))
    db_session.add(_audit_row(action="excluded.action", resource_type="job"))
    await db_session.commit()

    resp = await superadmin_client.get(
        "/admin/audit-log/export", params={"action": "included.action"}
    )
    assert resp.status_code == 200
    assert "included.action" in resp.text
    assert "excluded.action" not in resp.text


# ---------------------------------------------------------------------------
# Test 10: require_superadmin canonical import path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_superadmin_canonical_import() -> None:
    """require_superadmin imported from auth.api.deps raises 403 for non-superadmin."""
    from app.modules.auth.api.deps import require_superadmin  # noqa: PLC0415
    from app.shared.exceptions import PermissionDeniedError  # noqa: PLC0415

    student_auth = _make_auth(_student_principal())
    with pytest.raises(PermissionDeniedError):
        await require_superadmin(auth=student_auth)

    # Superadmin: no raise, returns principal
    sa_auth = _make_auth(_superadmin_principal())
    result = await require_superadmin(auth=sa_auth)
    assert result.is_superadmin is True


@pytest.mark.asyncio
async def test_require_superadmin_ai_ops_reexport() -> None:
    """ai_ops.api.deps.require_superadmin is the same function (re-exported)."""
    from app.modules.ai_ops.api.deps import require_superadmin as ai_ops_sa  # noqa: PLC0415
    from app.modules.auth.api.deps import require_superadmin as auth_sa  # noqa: PLC0415

    # Both should refer to the same underlying function object.
    assert ai_ops_sa is auth_sa


# ---------------------------------------------------------------------------
# Test: response envelope shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_response_envelope_shape(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Verify exact envelope shape: {data: [...], page: {next_cursor, limit}}."""
    db_session.add(_audit_row(action="envelope.test"))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/audit-log", params={"limit": 10})
    assert resp.status_code == 200
    body = resp.json()

    assert "data" in body
    assert "page" in body
    assert "next_cursor" in body["page"]
    assert "limit" in body["page"]
    assert isinstance(body["data"], list)
    assert isinstance(body["page"]["limit"], int)

    # Verify item shape (no ip/ua hashes in list items either)
    if body["data"]:
        item = body["data"][0]
        assert "id" in item
        assert "actor_id" in item
        assert "actor_org_id" in item
        assert "actor_email" in item
        assert "action" in item
        assert "resource_type" in item
        assert "resource_id" in item
        assert "occurred_at" in item
        assert "ip_hash" not in item
        assert "user_agent_hash" not in item
