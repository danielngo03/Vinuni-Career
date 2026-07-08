"""Integration tests for student Job Alerts CRUD.

Covers: create, list, delete (soft), permission guards, quota limit, name conflict.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.opportunities.application import job_alert_service
from app.shared.exceptions import ConflictError, PermissionDeniedError, QuotaExceededError
from app.shared.models import AuditLog
from sqlalchemy import select

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_alert(db, student, *, name="Python internships", **kwargs) -> dict:
    return await job_alert_service.create_alert(
        db,
        principal=student,
        name=name,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_student_can_create_alert(db_session) -> None:
    _, student = await make_student(db_session)
    alert = await _make_alert(db_session, student, keywords="python", employment_type="internship")
    assert alert["name"] == "Python internships"
    assert alert["keywords"] == "python"
    assert alert["employment_type"] == "internship"
    assert alert["is_active"] is True
    assert "id" in alert
    assert "created_at" in alert


async def test_create_alert_persists_to_list(db_session) -> None:
    _, student = await make_student(db_session)
    await _make_alert(db_session, student, name="Alert A")
    await _make_alert(db_session, student, name="Alert B")
    alerts = await job_alert_service.list_alerts(db_session, principal=student)
    names = {a["name"] for a in alerts}
    assert "Alert A" in names
    assert "Alert B" in names


async def test_create_strips_and_truncates_name(db_session) -> None:
    _, student = await make_student(db_session)
    long_name = "x" * 200
    alert = await _make_alert(db_session, student, name="  " + long_name + "  ")
    assert len(alert["name"]) <= 120
    assert not alert["name"].startswith(" ")


# ---------------------------------------------------------------------------
# conflict
# ---------------------------------------------------------------------------


async def test_duplicate_name_raises_conflict(db_session) -> None:
    _, student = await make_student(db_session)
    await _make_alert(db_session, student, name="Dupe Alert")
    with pytest.raises(ConflictError):
        await _make_alert(db_session, student, name="Dupe Alert")


async def test_different_students_same_name_allowed(db_session) -> None:
    _, student1 = await make_student(db_session)
    _, student2 = await make_student(db_session)
    await _make_alert(db_session, student1, name="Same Name")
    # Should not raise for a different user
    alert2 = await _make_alert(db_session, student2, name="Same Name")
    assert alert2["name"] == "Same Name"


# ---------------------------------------------------------------------------
# quota
# ---------------------------------------------------------------------------


async def test_quota_exceeded_at_10(db_session) -> None:
    _, student = await make_student(db_session)
    for i in range(10):
        await _make_alert(db_session, student, name=f"Alert {i}")
    with pytest.raises(QuotaExceededError):
        await _make_alert(db_session, student, name="Alert 10")


# ---------------------------------------------------------------------------
# delete (soft)
# ---------------------------------------------------------------------------


async def test_delete_removes_from_list(db_session) -> None:
    _, student = await make_student(db_session)
    import uuid as _uuid
    alert = await _make_alert(db_session, student, name="To Delete")
    alert_id = _uuid.UUID(alert["id"])
    await job_alert_service.delete_alert(db_session, principal=student, alert_id=alert_id)
    alerts = await job_alert_service.list_alerts(db_session, principal=student)
    assert not any(a["id"] == str(alert_id) for a in alerts)


async def test_delete_nonexistent_raises_not_found(db_session) -> None:
    import uuid as _uuid

    from app.shared.exceptions import ResourceNotFoundError
    _, student = await make_student(db_session)
    with pytest.raises(ResourceNotFoundError):
        await job_alert_service.delete_alert(
            db_session, principal=student, alert_id=_uuid.uuid4()
        )


async def test_delete_owned_by_other_raises_not_found(db_session) -> None:
    import uuid as _uuid

    from app.shared.exceptions import ResourceNotFoundError
    _, student1 = await make_student(db_session)
    _, student2 = await make_student(db_session)
    alert = await _make_alert(db_session, student1, name="Student1 Alert")
    alert_id = _uuid.UUID(alert["id"])
    with pytest.raises(ResourceNotFoundError):
        await job_alert_service.delete_alert(
            db_session, principal=student2, alert_id=alert_id
        )


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------


async def test_partner_cannot_create_alert(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await _make_alert(db_session, partner, name="Partner Alert")


async def test_partner_cannot_list_alerts(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await job_alert_service.list_alerts(db_session, principal=partner)


async def test_list_empty_for_new_student(db_session) -> None:
    _, student = await make_student(db_session)
    alerts = await job_alert_service.list_alerts(db_session, principal=student)
    assert alerts == []


# ---------------------------------------------------------------------------
# audit (B-594): every write action creates audit data
# ---------------------------------------------------------------------------


async def test_create_and_delete_alert_write_audit_rows(db_session) -> None:
    _, student = await make_student(db_session)
    alert = await _make_alert(db_session, student, name="Audited Alert")
    alert_id = uuid.UUID(alert["id"])

    created_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "job_alert.created",
                AuditLog.resource_id == alert_id,
            )
        )
    ).scalars().all()
    assert len(created_rows) == 1
    created = created_rows[0]
    assert created.resource_type == "job_alert"
    assert created.actor_id == student.user_id
    # Snapshot carries only non-PII alert criteria (no email/name-of-person).
    assert created.after_snapshot is not None
    assert created.after_snapshot.get("name") == "Audited Alert"

    await job_alert_service.delete_alert(
        db_session, principal=student, alert_id=alert_id
    )

    deleted_rows = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "job_alert.deleted",
                AuditLog.resource_id == alert_id,
            )
        )
    ).scalars().all()
    assert len(deleted_rows) == 1
    assert deleted_rows[0].after_snapshot == {"is_active": False}
