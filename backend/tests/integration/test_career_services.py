"""Career-services counselor workspace tests (B-554).

Covers RBAC/permission denial, tenant isolation, appointment double-booking,
duplicate cohort membership idempotency, at-risk flag lifecycle, CV review
assignment, and outcomes-reporting aggregation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.career_services.application import (
    appointment_service,
    at_risk_service,
    cohort_service,
    cv_review_service,
    employer_note_service,
    intervention_service,
    reporting_service,
)
from app.modules.career_services.domain import catalog
from app.shared.exceptions import ConflictError, PermissionDeniedError, ValidationFailedError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX
from tests.career_services_utils import ALL_CAREER_SERVICES_PERMISSIONS, add_counselor
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin


def _future(hours: int = 24) -> datetime:
    return (datetime.now(tz=UTC) + timedelta(hours=hours)).replace(microsecond=0)


async def _setup(db_session: AsyncSession):
    """A university org + one fully-permissioned counselor."""

    _admin, org, _admin_p = await make_org_with_admin(db_session, org_type="university")
    _cu, _m, counselor = await add_counselor(
        db_session, org=org, permissions=ALL_CAREER_SERVICES_PERMISSIONS
    )
    return org, counselor


# --------------------------------------------------------------------------- #
# RBAC / permission denial                                                    #
# --------------------------------------------------------------------------- #


async def test_create_cohort_denied_without_permission(db_session: AsyncSession) -> None:
    _admin, org, _admin_p = await make_org_with_admin(db_session, org_type="university")
    _cu, _m, bare_counselor = await add_counselor(db_session, org=org, permissions=[])

    with pytest.raises(PermissionDeniedError):
        await cohort_service.create_cohort(
            db_session,
            principal=bare_counselor,
            name="Cohort A",
            description=None,
            ctx=CTX,
        )


async def test_partner_persona_cannot_touch_career_services(db_session: AsyncSession) -> None:
    _pu, porg, _admin_p = await make_org_with_admin(db_session, display_name="ACME")
    # A non-admin partner member with NO career-services grants (the org admin's
    # own ``*:*`` wildcard would trivially pass every check).
    _mu, _membership, partner_member = await add_member(
        db_session, org=porg, permissions=[("jobs", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await cohort_service.list_cohorts(db_session, principal=partner_member)


# --------------------------------------------------------------------------- #
# Tenant isolation                                                            #
# --------------------------------------------------------------------------- #


async def test_cross_org_cohort_access_denied(db_session: AsyncSession) -> None:
    org_a, counselor_a = await _setup(db_session)
    org_b, counselor_b = await _setup(db_session)

    created = await cohort_service.create_cohort(
        db_session, principal=counselor_a, name="Org A Cohort", description=None, ctx=CTX
    )
    cohort_id = uuid.UUID(created["id"])

    # Org B's counselor cannot see/update org A's cohort — scoped query returns
    # nothing for a different org_id, surfaced as 404 (enumeration-safe).
    from app.shared.exceptions import ResourceNotFoundError

    with pytest.raises(ResourceNotFoundError):
        await cohort_service.update_cohort(
            db_session,
            principal=counselor_b,
            cohort_id=cohort_id,
            name="Hijacked",
            description=None,
            status=None,
            ctx=CTX,
        )

    org_a_cohorts = await cohort_service.list_cohorts(db_session, principal=counselor_a)
    org_b_cohorts = await cohort_service.list_cohorts(db_session, principal=counselor_b)
    assert len(org_a_cohorts) == 1
    assert len(org_b_cohorts) == 0


# --------------------------------------------------------------------------- #
# Duplicate cohort membership (idempotent)                                    #
# --------------------------------------------------------------------------- #


async def test_duplicate_cohort_membership_is_idempotent(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="cs-member")

    cohort = await cohort_service.create_cohort(
        db_session, principal=counselor, name="CS 2026", description=None, ctx=CTX
    )
    cohort_id = uuid.UUID(cohort["id"])

    first = await cohort_service.add_member(
        db_session,
        principal=counselor,
        cohort_id=cohort_id,
        student_id=student.user_id,
        ctx=CTX,
    )
    second = await cohort_service.add_member(
        db_session,
        principal=counselor,
        cohort_id=cohort_id,
        student_id=student.user_id,
        ctx=CTX,
    )
    assert first["id"] == second["id"]

    members = await cohort_service.list_members(
        db_session, principal=counselor, cohort_id=cohort_id
    )
    assert len(members) == 1


async def test_duplicate_cohort_name_rejected(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    await cohort_service.create_cohort(
        db_session, principal=counselor, name="Dup Name", description=None, ctx=CTX
    )
    with pytest.raises(ConflictError):
        await cohort_service.create_cohort(
            db_session, principal=counselor, name="Dup Name", description=None, ctx=CTX
        )


# --------------------------------------------------------------------------- #
# At-risk flag lifecycle                                                      #
# --------------------------------------------------------------------------- #


async def test_at_risk_flag_lifecycle(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="cs-risk")

    flag = await at_risk_service.create_flag(
        db_session,
        principal=counselor,
        student_id=student.user_id,
        reason=catalog.RISK_REASON_NO_APPLICATIONS,
        severity=catalog.RISK_SEVERITY_HIGH,
        notes="No applications in 2 months.",
        cohort_id=None,
        ctx=CTX,
    )
    assert flag["status"] == catalog.RISK_OPEN

    # Resolving without notes is rejected.
    with pytest.raises(ValidationFailedError):
        await at_risk_service.update_flag_status(
            db_session,
            principal=counselor,
            flag_id=uuid.UUID(flag["id"]),
            status=catalog.RISK_RESOLVED,
            resolution_notes=None,
            ctx=CTX,
        )

    resolved = await at_risk_service.update_flag_status(
        db_session,
        principal=counselor,
        flag_id=uuid.UUID(flag["id"]),
        status=catalog.RISK_RESOLVED,
        resolution_notes="Applied to 3 jobs after outreach.",
        ctx=CTX,
    )
    assert resolved["status"] == catalog.RISK_RESOLVED
    assert resolved["resolved_at"] is not None
    assert resolved["resolution_notes"] == "Applied to 3 jobs after outreach."

    open_flags = await at_risk_service.list_flags(
        db_session, principal=counselor, status=catalog.RISK_OPEN
    )
    assert open_flags == []


# --------------------------------------------------------------------------- #
# CV review queue assignment                                                  #
# --------------------------------------------------------------------------- #


async def test_cv_review_assignment_transitions_status(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="cs-cv")

    item = await cv_review_service.create_item(
        db_session,
        principal=counselor,
        student_id=student.user_id,
        cv_id=None,
        priority=catalog.CV_REVIEW_PRIORITY_HIGH,
        ctx=CTX,
    )
    assert item["status"] == catalog.CV_REVIEW_QUEUED

    assigned = await cv_review_service.assign_counselor(
        db_session,
        principal=counselor,
        item_id=uuid.UUID(item["id"]),
        counselor_id=counselor.user_id,
        ctx=CTX,
    )
    assert assigned["status"] == catalog.CV_REVIEW_IN_REVIEW
    assert assigned["assigned_counselor_id"] == str(counselor.user_id)

    done = await cv_review_service.update_status(
        db_session,
        principal=counselor,
        item_id=uuid.UUID(item["id"]),
        status=catalog.CV_REVIEW_APPROVED,
        feedback="Looks strong — minor formatting tweak.",
        ctx=CTX,
    )
    assert done["status"] == catalog.CV_REVIEW_APPROVED
    assert done["resolved_at"] is not None


# --------------------------------------------------------------------------- #
# Appointment double-booking                                                   #
# --------------------------------------------------------------------------- #


async def test_appointment_double_booking_rejected(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _s1, student1 = await make_student(db_session, prefix="cs-appt-1")
    _s2, student2 = await make_student(db_session, prefix="cs-appt-2")

    slot = _future()
    first = await appointment_service.book_appointment(
        db_session,
        principal=counselor,
        student_id=student1.user_id,
        counselor_id=counselor.user_id,
        scheduled_at=slot,
        duration_minutes=30,
        mode=catalog.APPT_MODE_VIDEO,
        location=None,
        notes=None,
        ctx=CTX,
    )
    assert first["status"] == catalog.APPT_REQUESTED

    with pytest.raises(ConflictError):
        await appointment_service.book_appointment(
            db_session,
            principal=counselor,
            student_id=student2.user_id,
            counselor_id=counselor.user_id,
            scheduled_at=slot,
            duration_minutes=30,
            mode=catalog.APPT_MODE_VIDEO,
            location=None,
            notes=None,
            ctx=CTX,
        )

    # Cancelling the first appointment frees the slot for rebooking.
    cancelled = await appointment_service.update_status(
        db_session,
        principal=counselor,
        appointment_id=uuid.UUID(first["id"]),
        status=catalog.APPT_CANCELLED,
        cancel_reason="Student rescheduled.",
        ctx=CTX,
    )
    assert cancelled["status"] == catalog.APPT_CANCELLED

    rebooked = await appointment_service.book_appointment(
        db_session,
        principal=counselor,
        student_id=student2.user_id,
        counselor_id=counselor.user_id,
        scheduled_at=slot,
        duration_minutes=30,
        mode=catalog.APPT_MODE_VIDEO,
        location=None,
        notes=None,
        ctx=CTX,
    )
    assert rebooked["status"] == catalog.APPT_REQUESTED


async def test_appointment_cancel_requires_reason(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="cs-appt-cancel")

    appt = await appointment_service.book_appointment(
        db_session,
        principal=counselor,
        student_id=student.user_id,
        counselor_id=counselor.user_id,
        scheduled_at=_future(hours=48),
        duration_minutes=30,
        mode=catalog.APPT_MODE_IN_PERSON,
        location="Room 101",
        notes=None,
        ctx=CTX,
    )
    with pytest.raises(ValidationFailedError):
        await appointment_service.update_status(
            db_session,
            principal=counselor,
            appointment_id=uuid.UUID(appt["id"]),
            status=catalog.APPT_CANCELLED,
            cancel_reason=None,
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Employer relationship notes + intervention history                          #
# --------------------------------------------------------------------------- #


async def test_employer_note_and_intervention_flow(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _pu, employer_org, _pp = await make_org_with_admin(db_session, display_name="Employer Co")
    _su, student = await make_student(db_session, prefix="cs-intervention")

    note = await employer_note_service.create_note(
        db_session,
        principal=counselor,
        employer_org_id=employer_org.id,
        category=catalog.NOTE_CATEGORY_PARTNERSHIP,
        visibility=catalog.NOTE_VISIBILITY_ALL_STAFF,
        note_text="Great turnout at last career fair.",
        ctx=CTX,
    )
    assert note["category_label"] in {"Hợp tác", "Partnership"}

    flag = await at_risk_service.create_flag(
        db_session,
        principal=counselor,
        student_id=student.user_id,
        reason=catalog.RISK_REASON_GRADUATING_UNPLACED,
        severity=catalog.RISK_SEVERITY_HIGH,
        notes=None,
        cohort_id=None,
        ctx=CTX,
    )

    intervention = await intervention_service.create_intervention(
        db_session,
        principal=counselor,
        student_id=student.user_id,
        intervention_type=catalog.INTERVENTION_EMPLOYER_REFERRAL,
        description="Referred to Employer Co's open analyst role.",
        linked_appointment_id=None,
        linked_at_risk_flag_id=uuid.UUID(flag["id"]),
        ctx=CTX,
    )
    assert intervention["outcome"] == catalog.INTERVENTION_OUTCOME_PENDING

    updated = await intervention_service.update_outcome(
        db_session,
        principal=counselor,
        record_id=uuid.UUID(intervention["id"]),
        outcome=catalog.INTERVENTION_OUTCOME_IMPROVED,
        ctx=CTX,
    )
    assert updated["outcome"] == catalog.INTERVENTION_OUTCOME_IMPROVED


async def test_intervention_rejects_cross_org_linked_flag(db_session: AsyncSession) -> None:
    org_a, counselor_a = await _setup(db_session)
    org_b, counselor_b = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="cs-cross-link")

    flag_b = await at_risk_service.create_flag(
        db_session,
        principal=counselor_b,
        student_id=student.user_id,
        reason=catalog.RISK_REASON_OTHER,
        severity=catalog.RISK_SEVERITY_LOW,
        notes=None,
        cohort_id=None,
        ctx=CTX,
    )

    with pytest.raises(ValidationFailedError):
        await intervention_service.create_intervention(
            db_session,
            principal=counselor_a,
            student_id=student.user_id,
            intervention_type=catalog.INTERVENTION_OTHER,
            description="Cross-org link attempt.",
            linked_appointment_id=None,
            linked_at_risk_flag_id=uuid.UUID(flag_b["id"]),
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Outcomes reporting aggregation                                              #
# --------------------------------------------------------------------------- #


async def test_reporting_summary_aggregates_correctly(db_session: AsyncSession) -> None:
    org, counselor = await _setup(db_session)
    _s1, student1 = await make_student(db_session, prefix="cs-report-1")
    _s2, student2 = await make_student(db_session, prefix="cs-report-2")

    await cohort_service.create_cohort(
        db_session, principal=counselor, name="Reporting Cohort", description=None, ctx=CTX
    )

    flag1 = await at_risk_service.create_flag(
        db_session,
        principal=counselor,
        student_id=student1.user_id,
        reason=catalog.RISK_REASON_ACADEMIC,
        severity=catalog.RISK_SEVERITY_MEDIUM,
        notes=None,
        cohort_id=None,
        ctx=CTX,
    )
    await at_risk_service.create_flag(
        db_session,
        principal=counselor,
        student_id=student2.user_id,
        reason=catalog.RISK_REASON_OTHER,
        severity=catalog.RISK_SEVERITY_LOW,
        notes=None,
        cohort_id=None,
        ctx=CTX,
    )
    await at_risk_service.update_flag_status(
        db_session,
        principal=counselor,
        flag_id=uuid.UUID(flag1["id"]),
        status=catalog.RISK_RESOLVED,
        resolution_notes="Improved after tutoring referral.",
        ctx=CTX,
    )

    await cv_review_service.create_item(
        db_session,
        principal=counselor,
        student_id=student1.user_id,
        cv_id=None,
        priority=catalog.CV_REVIEW_PRIORITY_NORMAL,
        ctx=CTX,
    )

    await appointment_service.book_appointment(
        db_session,
        principal=counselor,
        student_id=student1.user_id,
        counselor_id=counselor.user_id,
        scheduled_at=_future(),
        duration_minutes=30,
        mode=catalog.APPT_MODE_VIDEO,
        location=None,
        notes=None,
        ctx=CTX,
    )

    summary = await reporting_service.get_reporting_summary(db_session, principal=counselor)
    assert summary["active_cohorts"] == 1
    assert summary["open_at_risk_flags"] == 1  # one resolved, one still open
    assert summary["open_cv_reviews"] == 1
    appt_statuses = {row["code"]: row["count"] for row in summary["appointments_by_status"]}
    assert appt_statuses.get(catalog.APPT_REQUESTED) == 1
    risk_statuses = {row["code"]: row["count"] for row in summary["at_risk_by_status"]}
    assert risk_statuses.get(catalog.RISK_RESOLVED) == 1
    assert risk_statuses.get(catalog.RISK_OPEN) == 1

    # Another org's counselor sees a fresh, isolated summary.
    other_org, other_counselor = await _setup(db_session)
    other_summary = await reporting_service.get_reporting_summary(
        db_session, principal=other_counselor
    )
    assert other_summary["active_cohorts"] == 0
    assert other_summary["open_at_risk_flags"] == 0
