"""Platform Admin P7 — Alerts & Incidents tests (strict TDD).

Coverage:
1.  Non-superadmin → 403 on all alert/incident endpoints.
2.  check_rule: all 4 comparisons (gt, lt, gte, lte), boundary cases.
3.  Rule CRUD:
      - create persists row + exactly ONE audit row.
      - invalid metric/comparison/severity → 422.
      - empty name → 422.
      - update patches fields + audit; missing rule → 404.
      - delete removes row + audited; missing → 404.
4.  evaluate_alerts:
      - firing rule opens ONE incident (idempotent: second run does NOT duplicate).
      - when metric drops below threshold, auto-resolves the open incident.
      - notification enqueue failure does NOT abort evaluation.
      - metric fetch failure skips that rule but continues evaluating others.
5.  Incident ack/resolve:
      - ack flips status → acknowledged + audited + idempotent.
      - resolve flips status → resolved + audited + idempotent.
      - already-resolved incident: ack is a no-op (idempotent, not audited again).
6.  List incidents: status filter works; cursor pagination.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_alerts.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.platform_admin.application.alerts_service import check_rule, evaluate_alerts
from app.modules.platform_admin.domain.models import AlertRule, Incident
from app.shared.audit import AuditContext
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
    ctx = RequestContext(ip="127.0.0.1", user_agent="pytest/1.0")
    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sa_client() -> AsyncIterator[AsyncClient]:
    uid = uuid.uuid4()
    auth = _make_auth(_superadmin_principal(user_id=uid))
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
# DB helpers
# ---------------------------------------------------------------------------


async def _get_rules(db: AsyncSession) -> list[AlertRule]:
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at))
    return list(result.scalars().all())


async def _get_incidents(db: AsyncSession) -> list[Incident]:
    result = await db.execute(select(Incident).order_by(Incident.triggered_at))
    return list(result.scalars().all())


async def _get_audit_rows(db: AsyncSession, resource_type: str) -> list[AuditLog]:
    result = await db.execute(select(AuditLog).where(AuditLog.resource_type == resource_type))
    return list(result.scalars().all())


def _superadmin_ctx(principal: Principal) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=None,
        session_id=uuid.uuid4(),
        ip="127.0.0.1",
        user_agent="pytest/1.0",
    )


# ---------------------------------------------------------------------------
# 1. Non-superadmin → 403 on all endpoints
# ---------------------------------------------------------------------------


async def test_non_superadmin_list_rules_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/alerts/rules")
    assert resp.status_code == 403


async def test_non_superadmin_create_rule_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.post(
        "/admin/alerts/rules",
        json={"name": "test", "metric": "queue_depth", "comparison": "gt", "threshold": 10},
    )
    assert resp.status_code == 403


async def test_non_superadmin_update_rule_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.patch(
        f"/admin/alerts/rules/{uuid.uuid4()}",
        json={"enabled": False},
    )
    assert resp.status_code == 403


async def test_non_superadmin_delete_rule_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.delete(f"/admin/alerts/rules/{uuid.uuid4()}")
    assert resp.status_code == 403


async def test_non_superadmin_list_incidents_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/alerts/incidents")
    assert resp.status_code == 403


async def test_non_superadmin_ack_incident_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.post(f"/admin/alerts/incidents/{uuid.uuid4()}/acknowledge")
    assert resp.status_code == 403


async def test_non_superadmin_resolve_incident_forbidden(student_client: AsyncClient) -> None:
    resp = await student_client.post(f"/admin/alerts/incidents/{uuid.uuid4()}/resolve")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. check_rule — pure unit tests, all 4 comparisons
# ---------------------------------------------------------------------------


def test_check_rule_gt_fires_above() -> None:
    assert check_rule(11.0, "gt", 10.0) is True


def test_check_rule_gt_does_not_fire_equal() -> None:
    assert check_rule(10.0, "gt", 10.0) is False


def test_check_rule_gt_does_not_fire_below() -> None:
    assert check_rule(9.0, "gt", 10.0) is False


def test_check_rule_gte_fires_equal() -> None:
    assert check_rule(10.0, "gte", 10.0) is True


def test_check_rule_gte_fires_above() -> None:
    assert check_rule(15.0, "gte", 10.0) is True


def test_check_rule_gte_does_not_fire_below() -> None:
    assert check_rule(9.9, "gte", 10.0) is False


def test_check_rule_lt_fires_below() -> None:
    assert check_rule(5.0, "lt", 10.0) is True


def test_check_rule_lt_does_not_fire_equal() -> None:
    assert check_rule(10.0, "lt", 10.0) is False


def test_check_rule_lt_does_not_fire_above() -> None:
    assert check_rule(11.0, "lt", 10.0) is False


def test_check_rule_lte_fires_equal() -> None:
    assert check_rule(10.0, "lte", 10.0) is True


def test_check_rule_lte_fires_below() -> None:
    assert check_rule(3.0, "lte", 10.0) is True


def test_check_rule_lte_does_not_fire_above() -> None:
    assert check_rule(10.1, "lte", 10.0) is False


def test_check_rule_unknown_comparison_is_false() -> None:
    assert check_rule(100.0, "eq", 10.0) is False


# ---------------------------------------------------------------------------
# 3. Rule CRUD
# ---------------------------------------------------------------------------


async def test_create_rule_persists_row_and_audit(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "name": "High queue depth",
        "metric": "queue_depth",
        "comparison": "gt",
        "threshold": 100,
        "severity": "warning",
        "enabled": True,
        "channels": ["in_app"],
    }
    resp = await sa_client.post("/admin/alerts/rules", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["name"] == "High queue depth"
    assert data["metric"] == "queue_depth"
    assert data["comparison"] == "gt"
    assert data["threshold"] == 100.0
    assert data["severity"] == "warning"
    assert data["enabled"] is True
    assert data["channels"] == ["in_app"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    rules = await _get_rules(db_session)
    assert len(rules) == 1

    audits = await _get_audit_rows(db_session, "alert_rule")
    assert len(audits) == 1
    assert audits[0].action == "alert_rule.created"
    assert audits[0].before_snapshot is None
    assert audits[0].after_snapshot is not None
    assert audits[0].after_snapshot["metric"] == "queue_depth"


async def test_create_rule_invalid_metric_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/alerts/rules",
        json={"name": "bad", "metric": "nonexistent_metric", "comparison": "gt", "threshold": 1},
    )
    assert resp.status_code == 422


async def test_create_rule_invalid_comparison_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/alerts/rules",
        json={"name": "bad", "metric": "queue_depth", "comparison": "eq", "threshold": 1},
    )
    assert resp.status_code == 422


async def test_create_rule_invalid_severity_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/alerts/rules",
        json={
            "name": "bad",
            "metric": "queue_depth",
            "comparison": "gt",
            "threshold": 1,
            "severity": "extreme",
        },
    )
    assert resp.status_code == 422


async def test_create_rule_empty_name_returns_422(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(
        "/admin/alerts/rules",
        json={"name": "", "metric": "queue_depth", "comparison": "gt", "threshold": 1},
    )
    assert resp.status_code == 422


async def test_update_rule_patches_fields_and_audits(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    create_resp = await sa_client.post(
        "/admin/alerts/rules",
        json={
            "name": "AI spend",
            "metric": "ai_spend_vs_budget_pct",
            "comparison": "gte",
            "threshold": 80,
        },
    )
    assert create_resp.status_code == 200
    rule_id = create_resp.json()["data"]["id"]

    patch_resp = await sa_client.patch(
        f"/admin/alerts/rules/{rule_id}",
        json={"threshold": 90.0, "severity": "critical", "enabled": False},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()["data"]
    assert updated["threshold"] == 90.0
    assert updated["severity"] == "critical"
    assert updated["enabled"] is False

    audits = await _get_audit_rows(db_session, "alert_rule")
    actions = {a.action for a in audits}
    assert "alert_rule.created" in actions
    assert "alert_rule.updated" in actions

    update_audit = next(a for a in audits if a.action == "alert_rule.updated")
    assert update_audit.before_snapshot is not None
    assert update_audit.before_snapshot["threshold"] == 80.0
    assert update_audit.after_snapshot is not None
    assert update_audit.after_snapshot["threshold"] == 90.0


async def test_update_missing_rule_returns_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.patch(
        f"/admin/alerts/rules/{uuid.uuid4()}",
        json={"enabled": False},
    )
    assert resp.status_code == 404


async def test_delete_rule_removes_row_and_audits(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    create_resp = await sa_client.post(
        "/admin/alerts/rules",
        json={"name": "To delete", "metric": "outbox_failed", "comparison": "gt", "threshold": 5},
    )
    assert create_resp.status_code == 200
    rule_id = create_resp.json()["data"]["id"]

    del_resp = await sa_client.delete(f"/admin/alerts/rules/{rule_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted"] is True

    rules = await _get_rules(db_session)
    assert len(rules) == 0

    audits = await _get_audit_rows(db_session, "alert_rule")
    actions = {a.action for a in audits}
    assert "alert_rule.deleted" in actions


async def test_delete_missing_rule_returns_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.delete(f"/admin/alerts/rules/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_list_rules_returns_all(sa_client: AsyncClient) -> None:
    for i in range(3):
        await sa_client.post(
            "/admin/alerts/rules",
            json={
                "name": f"rule-{i}",
                "metric": "queue_depth",
                "comparison": "gt",
                "threshold": i * 10,
            },
        )
    resp = await sa_client.get("/admin/alerts/rules")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 3


# ---------------------------------------------------------------------------
# 4. evaluate_alerts
# ---------------------------------------------------------------------------


async def _insert_rule(db: AsyncSession, **kwargs: Any) -> AlertRule:
    """Helper: insert an AlertRule directly for service-layer tests."""
    defaults: dict[str, Any] = {
        "name": "test rule",
        "metric": "queue_depth",
        "comparison": "gt",
        "threshold": 10.0,
        "window_days": 1,
        "severity": "warning",
        "enabled": True,
        "channels": [],
        "updated_by": None,
    }
    defaults.update(kwargs)
    rule = AlertRule(**defaults)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def test_evaluate_alerts_firing_rule_opens_incident(db_session: AsyncSession) -> None:
    rule = await _insert_rule(db_session, metric="queue_depth", comparison="gt", threshold=10.0)

    # Patch queue_depth to return a value that fires the rule (>10).
    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(return_value=50.0),
    ):
        result = await evaluate_alerts(db_session)

    assert result["opened"] == 1
    assert result["evaluated"] == 1

    incidents = await _get_incidents(db_session)
    assert len(incidents) == 1
    assert incidents[0].rule_id == rule.id
    assert incidents[0].status == "open"
    assert incidents[0].value == 50.0
    assert incidents[0].threshold == 10.0
    # Message must be user-safe — no internals.
    assert "queue" in incidents[0].message.lower() or "depth" in incidents[0].message.lower()


async def test_evaluate_alerts_idempotent_does_not_duplicate(db_session: AsyncSession) -> None:
    """Second evaluation with firing rule and existing open incident must NOT open a duplicate."""
    await _insert_rule(db_session, metric="queue_depth", comparison="gt", threshold=10.0)

    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(return_value=50.0),
    ):
        await evaluate_alerts(db_session)
        # Second run — same firing condition.
        result2 = await evaluate_alerts(db_session)

    assert result2["opened"] == 0  # no new incident
    incidents = await _get_incidents(db_session)
    assert len(incidents) == 1  # still only one


async def test_evaluate_alerts_auto_resolves_when_metric_drops(db_session: AsyncSession) -> None:
    """When metric drops below threshold, the open incident must be auto-resolved."""
    await _insert_rule(db_session, metric="queue_depth", comparison="gt", threshold=10.0)

    # First run: fires → opens incident.
    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(return_value=50.0),
    ):
        result1 = await evaluate_alerts(db_session)
    assert result1["opened"] == 1

    # Second run: metric drops below threshold → auto-resolve.
    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(return_value=5.0),
    ):
        result2 = await evaluate_alerts(db_session)

    assert result2["resolved"] == 1

    incidents = await _get_incidents(db_session)
    assert len(incidents) == 1
    assert incidents[0].status == "resolved"
    assert incidents[0].resolved_at is not None


async def test_evaluate_alerts_notification_failure_does_not_abort(
    db_session: AsyncSession,
) -> None:
    """A notification enqueue failure must not abort the evaluation sweep."""
    await _insert_rule(
        db_session,
        metric="queue_depth",
        comparison="gt",
        threshold=10.0,
        channels=["in_app"],
    )

    with (
        patch(
            "app.modules.platform_admin.application.alerts_service._fetch_metric",
            new=AsyncMock(return_value=50.0),
        ),
        patch(
            "app.modules.platform_admin.application.alerts_service"
            "._enqueue_incident_notification_best_effort",
            new=AsyncMock(side_effect=RuntimeError("SMTP down")),
        ),
    ):
        result = await evaluate_alerts(db_session)

    # Evaluation still ran and incident was opened despite notification failure.
    assert result["evaluated"] == 1
    assert result["opened"] == 1


async def test_evaluate_alerts_metric_fetch_failure_skips_rule(db_session: AsyncSession) -> None:
    """When metric fetch fails, that rule is skipped but the sweep continues."""
    await _insert_rule(db_session, metric="queue_depth", comparison="gt", threshold=10.0)
    await _insert_rule(
        db_session, name="rule2", metric="outbox_failed", comparison="gt", threshold=5.0
    )

    call_count = 0

    async def _side_effect(_session: Any, metric: str, _window_days: int) -> float | None:
        nonlocal call_count
        call_count += 1
        if metric == "queue_depth":
            return None  # simulate fetch failure for first rule
        return 100.0  # second rule fires

    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(side_effect=_side_effect),
    ):
        result = await evaluate_alerts(db_session)

    assert result["evaluated"] == 2
    # First rule skipped (metric=None), second rule fired.
    assert result["opened"] == 1
    incidents = await _get_incidents(db_session)
    assert len(incidents) == 1
    assert incidents[0].metric == "outbox_failed"


async def test_evaluate_alerts_disabled_rule_is_skipped(db_session: AsyncSession) -> None:
    """Disabled rules must not be evaluated."""
    await _insert_rule(
        db_session, metric="queue_depth", comparison="gt", threshold=10.0, enabled=False
    )

    with patch(
        "app.modules.platform_admin.application.alerts_service._fetch_metric",
        new=AsyncMock(return_value=999.0),
    ):
        result = await evaluate_alerts(db_session)

    assert result["evaluated"] == 0
    assert result["opened"] == 0


# ---------------------------------------------------------------------------
# 5. Incident ack / resolve
# ---------------------------------------------------------------------------


async def _create_open_incident(db: AsyncSession, rule: AlertRule) -> Incident:
    """Insert an open incident directly for ack/resolve tests."""
    inc = Incident(
        rule_id=rule.id,
        metric=rule.metric,
        severity=rule.severity,
        status="open",
        message="Test incident: queue depth exceeded.",
        value=50.0,
        threshold=10.0,
        triggered_at=datetime.now(tz=UTC),
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


async def test_acknowledge_incident_flips_status_and_audits(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    rule = await _insert_rule(db_session)
    incident = await _create_open_incident(db_session, rule)

    resp = await sa_client.post(f"/admin/alerts/incidents/{incident.id}/acknowledge")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "acknowledged"
    assert data["acknowledged_at"] is not None
    assert data["acknowledged_by"] is not None

    audits = await _get_audit_rows(db_session, "incident")
    assert any(a.action == "incident.acknowledged" for a in audits)


async def test_acknowledge_incident_idempotent(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second ack on an already-acknowledged incident must be a no-op (no extra audit row)."""
    rule = await _insert_rule(db_session)
    incident = await _create_open_incident(db_session, rule)

    await sa_client.post(f"/admin/alerts/incidents/{incident.id}/acknowledge")
    resp2 = await sa_client.post(f"/admin/alerts/incidents/{incident.id}/acknowledge")
    assert resp2.status_code == 200

    audits = await _get_audit_rows(db_session, "incident")
    ack_audits = [a for a in audits if a.action == "incident.acknowledged"]
    assert len(ack_audits) == 1  # only one audit row, not two


async def test_resolve_incident_flips_status_and_audits(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    rule = await _insert_rule(db_session)
    incident = await _create_open_incident(db_session, rule)

    resp = await sa_client.post(f"/admin/alerts/incidents/{incident.id}/resolve")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None

    audits = await _get_audit_rows(db_session, "incident")
    assert any(a.action == "incident.resolved" for a in audits)


async def test_resolve_incident_idempotent(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second resolve on an already-resolved incident must be a no-op."""
    rule = await _insert_rule(db_session)
    incident = await _create_open_incident(db_session, rule)

    await sa_client.post(f"/admin/alerts/incidents/{incident.id}/resolve")
    resp2 = await sa_client.post(f"/admin/alerts/incidents/{incident.id}/resolve")
    assert resp2.status_code == 200

    audits = await _get_audit_rows(db_session, "incident")
    resolve_audits = [a for a in audits if a.action == "incident.resolved"]
    assert len(resolve_audits) == 1


async def test_ack_on_resolved_incident_is_noop(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ack on an already-resolved incident must return 200 without changing status or auditing."""
    rule = await _insert_rule(db_session)
    incident = await _create_open_incident(db_session, rule)

    # Resolve first.
    await sa_client.post(f"/admin/alerts/incidents/{incident.id}/resolve")

    # Ack on resolved — must be harmless.
    resp = await sa_client.post(f"/admin/alerts/incidents/{incident.id}/acknowledge")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "resolved"  # unchanged

    # Only one audit row (the resolve), no ack audit.
    audits = await _get_audit_rows(db_session, "incident")
    ack_audits = [a for a in audits if a.action == "incident.acknowledged"]
    assert len(ack_audits) == 0


async def test_ack_missing_incident_returns_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(f"/admin/alerts/incidents/{uuid.uuid4()}/acknowledge")
    assert resp.status_code == 404


async def test_resolve_missing_incident_returns_404(sa_client: AsyncClient) -> None:
    resp = await sa_client.post(f"/admin/alerts/incidents/{uuid.uuid4()}/resolve")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. List incidents — status filter + cursor pagination
# ---------------------------------------------------------------------------


async def test_list_incidents_no_filter(sa_client: AsyncClient, db_session: AsyncSession) -> None:
    rule = await _insert_rule(db_session)
    for _ in range(3):
        await _create_open_incident(db_session, rule)

    resp = await sa_client.get("/admin/alerts/incidents")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 3
    assert "page" in body


async def test_list_incidents_status_filter(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    rule = await _insert_rule(db_session)
    inc = await _create_open_incident(db_session, rule)
    await _create_open_incident(db_session, rule)

    # Resolve one.
    await sa_client.post(f"/admin/alerts/incidents/{inc.id}/resolve")

    resp_open = await sa_client.get("/admin/alerts/incidents?status=open")
    assert resp_open.status_code == 200
    assert len(resp_open.json()["data"]) == 1

    resp_resolved = await sa_client.get("/admin/alerts/incidents?status=resolved")
    assert resp_resolved.status_code == 200
    assert len(resp_resolved.json()["data"]) == 1


async def test_list_incidents_pagination_limit(
    sa_client: AsyncClient, db_session: AsyncSession
) -> None:
    rule = await _insert_rule(db_session)
    for _ in range(5):
        await _create_open_incident(db_session, rule)

    resp = await sa_client.get("/admin/alerts/incidents?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["page"]["next_cursor"] is not None
