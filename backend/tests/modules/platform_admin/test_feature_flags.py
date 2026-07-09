"""Platform Admin P5 — Feature Flags & Permission Catalog tests (strict TDD).

Coverage:
1.  Non-superadmin → 403 on list/create/update/catalog.
2.  Create flag → row persisted + exactly ONE audit row; fields match.
3.  Duplicate key → 409 ConflictError; response body contains no DB internals.
4.  Invalid rollout (>100 or <0) → 422 ValidationFailedError.
5.  Invalid key format → 422 ValidationFailedError.
6.  PATCH update toggles enabled + writes exactly ONE audit row.
7.  PATCH on missing flag_id → 404.
8.  evaluate() off / on / partial-rollout determinism.
9.  GET /admin/permission-catalog returns resource/actions from PERMISSION_CATALOG.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_feature_flags.py -v
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.organization.domain.catalog import PERMISSION_CATALOG
from app.modules.platform_admin.application.feature_flags_service import evaluate
from app.modules.platform_admin.domain.models import FeatureFlag
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Principal / auth helpers
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
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sa_client() -> AsyncIterator[AsyncClient]:
    """Authenticated as superadmin."""
    uid = uuid.uuid4()
    auth = _make_auth(_superadmin_principal(user_id=uid))
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    """Authenticated as non-superadmin student."""
    auth = _make_auth(_student_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Helper: read DB rows inside tests
# ---------------------------------------------------------------------------


async def _get_flags(db: AsyncSession) -> list[FeatureFlag]:
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    return list(result.scalars().all())


async def _get_audit_rows(db: AsyncSession, resource_type: str = "feature_flag") -> list[AuditLog]:
    result = await db.execute(select(AuditLog).where(AuditLog.resource_type == resource_type))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 1. Non-superadmin → 403
# ---------------------------------------------------------------------------


async def test_non_superadmin_list_flags_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/feature-flags")
    assert resp.status_code == 403


async def test_non_superadmin_create_flag_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.post(
        "/admin/feature-flags",
        json={"key": "test.flag", "description": "x"},
    )
    assert resp.status_code == 403


async def test_non_superadmin_update_flag_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.patch(
        f"/admin/feature-flags/{uuid.uuid4()}",
        json={"enabled": True},
    )
    assert resp.status_code == 403


async def test_non_superadmin_catalog_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/permission-catalog")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Create flag → row persisted + ONE audit row
# ---------------------------------------------------------------------------


async def test_create_flag_persists_row_and_audit(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "key": "cv_studio.ai_rewrite",
        "description": "Enable AI rewrite in CV Studio",
        "enabled": False,
        "rollout_percentage": 0,
    }
    resp = await sa_client.post("/admin/feature-flags", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["key"] == "cv_studio.ai_rewrite"
    assert data["enabled"] is False
    assert data["rollout_percentage"] == 0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Confirm DB row exists.
    flags = await _get_flags(db_session)
    assert len(flags) == 1
    assert flags[0].key == "cv_studio.ai_rewrite"

    # Exactly one audit row.
    audits = await _get_audit_rows(db_session)
    assert len(audits) == 1
    assert audits[0].action == "feature_flag.created"
    assert audits[0].before_snapshot is None
    assert audits[0].after_snapshot is not None
    assert audits[0].after_snapshot["key"] == "cv_studio.ai_rewrite"


# ---------------------------------------------------------------------------
# 3. Duplicate key → 409, no DB internals in body
# ---------------------------------------------------------------------------


async def test_duplicate_key_returns_409(sa_client: AsyncClient) -> None:
    payload = {"key": "jobs.beta", "description": "beta"}
    await sa_client.post("/admin/feature-flags", json=payload)
    resp = await sa_client.post("/admin/feature-flags", json=payload)
    assert resp.status_code == 409

    body = resp.json()
    # No DB internals (table names, constraint names, SQL) must appear.
    body_str = str(body).lower()
    for forbidden in ("unique", "constraint", "pg", "sqlite", "sql", "violat"):
        assert forbidden not in body_str, f"DB internal '{forbidden}' leaked into 409 body"


# ---------------------------------------------------------------------------
# 4. Invalid rollout → 422
# ---------------------------------------------------------------------------


async def test_invalid_rollout_above_100_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/feature-flags",
        json={"key": "rollout.test", "rollout_percentage": 101},
    )
    assert resp.status_code == 422


async def test_invalid_rollout_below_0_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/feature-flags",
        json={"key": "rollout.neg", "rollout_percentage": -1},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Invalid key format → 422
# ---------------------------------------------------------------------------


async def test_invalid_key_empty_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post("/admin/feature-flags", json={"key": ""})
    assert resp.status_code == 422


async def test_invalid_key_uppercase_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post("/admin/feature-flags", json={"key": "MyFlag"})
    assert resp.status_code == 422


async def test_invalid_key_leading_dot_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post("/admin/feature-flags", json={"key": ".bad"})
    assert resp.status_code == 422


async def test_invalid_key_trailing_dot_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post("/admin/feature-flags", json={"key": "bad."})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. PATCH update toggles enabled + audited
# ---------------------------------------------------------------------------


async def test_update_flag_toggles_enabled_and_audits(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Create first.
    create_resp = await sa_client.post(
        "/admin/feature-flags",
        json={"key": "beta.feature", "enabled": False},
    )
    assert create_resp.status_code == 200
    flag_id = create_resp.json()["data"]["id"]

    # Now update.
    patch_resp = await sa_client.patch(
        f"/admin/feature-flags/{flag_id}",
        json={"enabled": True, "rollout_percentage": 50},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()["data"]
    assert updated["enabled"] is True
    assert updated["rollout_percentage"] == 50

    # Two audit rows total: one created, one updated.
    audits = await _get_audit_rows(db_session)
    actions = {a.action for a in audits}
    assert "feature_flag.created" in actions
    assert "feature_flag.updated" in actions

    # The update audit must capture before/after.
    update_audit = next(a for a in audits if a.action == "feature_flag.updated")
    assert update_audit.before_snapshot is not None
    assert update_audit.before_snapshot["enabled"] is False
    assert update_audit.after_snapshot is not None
    assert update_audit.after_snapshot["enabled"] is True


# ---------------------------------------------------------------------------
# 7. PATCH on missing flag → 404
# ---------------------------------------------------------------------------


async def test_update_missing_flag_returns_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.patch(
        f"/admin/feature-flags/{uuid.uuid4()}",
        json={"enabled": True},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. evaluate() — pure unit tests
# ---------------------------------------------------------------------------


class _MockFlag:
    """Minimal duck-type for FeatureFlag to test evaluate() without a DB."""

    def __init__(self, *, enabled: bool, rollout_percentage: int, key: str = "test") -> None:
        self.enabled = enabled
        self.rollout_percentage = rollout_percentage
        self.key = key


def test_evaluate_disabled_flag_always_false() -> None:
    flag = _MockFlag(enabled=False, rollout_percentage=100)
    assert evaluate(flag, subject_key="user-abc") is False  # type: ignore[arg-type]
    assert evaluate(flag, subject_key=None) is False  # type: ignore[arg-type]


def test_evaluate_enabled_full_rollout_always_true() -> None:
    flag = _MockFlag(enabled=True, rollout_percentage=100)
    assert evaluate(flag, subject_key="user-abc") is True  # type: ignore[arg-type]
    assert evaluate(flag, subject_key=None) is True  # type: ignore[arg-type]


def test_evaluate_enabled_zero_rollout_always_false() -> None:
    flag = _MockFlag(enabled=True, rollout_percentage=0)
    assert evaluate(flag, subject_key="user-abc") is False  # type: ignore[arg-type]


def test_evaluate_partial_rollout_none_subject_is_false() -> None:
    # Conservative: no subject key → not bucketed → False.
    flag = _MockFlag(enabled=True, rollout_percentage=50)
    assert evaluate(flag, subject_key=None) is False  # type: ignore[arg-type]


def test_evaluate_partial_rollout_deterministic() -> None:
    """Same subject always lands in the same bucket; result is stable."""
    flag = _MockFlag(enabled=True, rollout_percentage=50)
    subject = "user-determinism-check"

    # Compute expected bucket manually.
    bucket = int(hashlib.sha256(subject.encode()).hexdigest(), 16) % 100
    expected = bucket < 50

    # Multiple calls must agree.
    for _ in range(5):
        assert evaluate(flag, subject_key=subject) is expected  # type: ignore[arg-type]


def test_evaluate_partial_rollout_boundary_0_and_100() -> None:
    """Boundary subjects: bucket=0 always in (any pct>0), bucket=99 always out at pct=1."""
    # Find a subject whose bucket is exactly 0 by brute-force (small loop, deterministic).
    subject_bucket_0: str | None = None
    subject_bucket_99: str | None = None
    for i in range(10_000):
        s = f"scan-{i}"
        b = int(hashlib.sha256(s.encode()).hexdigest(), 16) % 100
        if b == 0 and subject_bucket_0 is None:
            subject_bucket_0 = s
        if b == 99 and subject_bucket_99 is None:
            subject_bucket_99 = s
        if subject_bucket_0 and subject_bucket_99:
            break

    if subject_bucket_0:
        flag = _MockFlag(enabled=True, rollout_percentage=1)
        assert evaluate(flag, subject_key=subject_bucket_0) is True  # type: ignore[arg-type]

    if subject_bucket_99:
        flag = _MockFlag(enabled=True, rollout_percentage=99)
        assert evaluate(flag, subject_key=subject_bucket_99) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 9. GET /admin/permission-catalog
# ---------------------------------------------------------------------------


async def test_permission_catalog_returns_known_resources(sa_client: AsyncClient) -> None:
    resp = await sa_client.get("/admin/permission-catalog")
    assert resp.status_code == 200

    catalog = resp.json()["data"]["catalog"]
    assert isinstance(catalog, list)
    assert len(catalog) == len(PERMISSION_CATALOG)

    resources = {entry["resource"] for entry in catalog}
    assert resources == set(PERMISSION_CATALOG.keys())


async def test_permission_catalog_ai_settings_has_view_provider_identity(
    sa_client: AsyncClient,
) -> None:
    resp = await sa_client.get("/admin/permission-catalog")
    assert resp.status_code == 200

    catalog = resp.json()["data"]["catalog"]
    ai_entry = next((e for e in catalog if e["resource"] == "ai_settings"), None)
    assert ai_entry is not None
    assert "view_provider_identity" in ai_entry["actions"]


async def test_permission_catalog_actions_are_sorted(sa_client: AsyncClient) -> None:
    resp = await sa_client.get("/admin/permission-catalog")
    assert resp.status_code == 200

    catalog = resp.json()["data"]["catalog"]
    for entry in catalog:
        actions = entry["actions"]
        assert actions == sorted(actions), f"Actions for {entry['resource']} are not sorted"


async def test_permission_catalog_resources_are_sorted(sa_client: AsyncClient) -> None:
    resp = await sa_client.get("/admin/permission-catalog")
    assert resp.status_code == 200

    catalog = resp.json()["data"]["catalog"]
    resources = [entry["resource"] for entry in catalog]
    assert resources == sorted(resources)


# ---------------------------------------------------------------------------
# 10. List flags returns all flags sorted by key
# ---------------------------------------------------------------------------


async def test_list_flags_sorted_by_key(sa_client: AsyncClient) -> None:
    keys = ["zz.flag", "aa.flag", "mm.flag"]
    for k in keys:
        r = await sa_client.post("/admin/feature-flags", json={"key": k})
        assert r.status_code == 200

    resp = await sa_client.get("/admin/feature-flags")
    assert resp.status_code == 200

    returned_keys = [item["key"] for item in resp.json()["data"]]
    assert returned_keys == sorted(keys)
