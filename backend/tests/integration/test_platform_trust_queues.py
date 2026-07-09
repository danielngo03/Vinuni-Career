"""Operational-queue hardening for the platform-trust surfaces.

Covers the two previously-dead queue states that made privacy and abuse
triage un-closeable, the re-processing guard, and the shared SLA policy
that every university operational queue now presents:

- privacy ``start_processing`` fills the dead ``PROCESSING`` state + claims the
  request (``processed_by``) + audits;
- ``fulfill`` refuses an already-resolved request;
- content-report ``dismiss`` fills the dead ``DISMISSED`` state (close a
  spam/false report without escalating) + audits, and only from ``PENDING``;
- presenter rows carry the shared SLA block (due-by / overdue / health) and a
  derived priority (deletion > export).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.compliance.application import privacy_request_service
from app.modules.moderation.application import report_service, triage_service
from app.shared import moderation as sla
from app.shared.audit import AuditLog
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import CTX, register_verified
from tests.org_utils import add_member, make_org_with_admin


async def _privacy_staff(db):
    _u, org, _admin = await make_org_with_admin(db, org_type="university")
    _staff, _membership, principal = await add_member(
        db, org=org, permissions=[("privacy", "process")]
    )
    return principal


async def _abuse_staff(db):
    _u, org, _admin = await make_org_with_admin(db, org_type="university")
    _staff, _membership, principal = await add_member(
        db, org=org, permissions=[("abuse", "triage"), ("abuse", "read")]
    )
    return principal


# --------------------------------------------------------------------------- #
# Privacy: start_processing (dead PROCESSING state) + fulfill guard           #
# --------------------------------------------------------------------------- #


async def test_privacy_start_processing_claims_and_audits(db_session) -> None:
    user = await register_verified(db_session, email="pq_start@vinuni.edu.vn")
    student = Principal(user_id=user.id, persona="student")
    submitted = await privacy_request_service.submit(
        db_session, principal=student, request_type="deletion", note=None, ctx=CTX
    )
    request_id = uuid.UUID(submitted["request"]["id"])
    staff = await _privacy_staff(db_session)

    started = await privacy_request_service.start_processing(
        db_session, principal=staff, request_id=request_id, ctx=CTX
    )
    assert started["status"] == "processing"
    # processed_by doubles as the claim/assignee once processing begins.
    assert started["assigned_to"] == str(staff.user_id)

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "compliance.privacy_request_processing_started"
            )
        )
    ).scalars().first()
    assert audit is not None
    assert audit.before_snapshot == {"status": "pending"}


async def test_privacy_start_processing_rejects_non_pending(db_session) -> None:
    user = await register_verified(db_session, email="pq_start2@vinuni.edu.vn")
    student = Principal(user_id=user.id, persona="student")
    submitted = await privacy_request_service.submit(
        db_session, principal=student, request_type="export", note=None, ctx=CTX
    )
    request_id = uuid.UUID(submitted["request"]["id"])
    staff = await _privacy_staff(db_session)

    await privacy_request_service.start_processing(
        db_session, principal=staff, request_id=request_id, ctx=CTX
    )
    # Already processing -> cannot start again.
    with pytest.raises(ValidationFailedError):
        await privacy_request_service.start_processing(
            db_session, principal=staff, request_id=request_id, ctx=CTX
        )


async def test_privacy_fulfill_rejects_already_resolved(db_session) -> None:
    user = await register_verified(db_session, email="pq_double@vinuni.edu.vn")
    student = Principal(user_id=user.id, persona="student")
    submitted = await privacy_request_service.submit(
        db_session, principal=student, request_type="export", note=None, ctx=CTX
    )
    request_id = uuid.UUID(submitted["request"]["id"])
    staff = await _privacy_staff(db_session)

    await privacy_request_service.fulfill(
        db_session, principal=staff, request_id=request_id,
        status="fulfilled", note="done", ctx=CTX,
    )
    with pytest.raises(ValidationFailedError):
        await privacy_request_service.fulfill(
            db_session, principal=staff, request_id=request_id,
            status="rejected", note="again", ctx=CTX,
        )


async def test_privacy_presenter_has_priority_and_sla(db_session) -> None:
    user = await register_verified(db_session, email="pq_sla@vinuni.edu.vn")
    student = Principal(user_id=user.id, persona="student")
    deletion = await privacy_request_service.submit(
        db_session, principal=student, request_type="deletion", note=None, ctx=CTX
    )
    row = deletion["request"]
    assert row["priority"] == "high"
    assert row["sla_hours"] == sla.QUEUE_SLA_HOURS[sla.QUEUE_PRIVACY_REQUEST]
    assert row["sla_health"] in {sla.SLA_OK, sla.SLA_DUE_SOON, sla.SLA_OVERDUE}
    assert "due_by" in row and row["due_by"] is not None


# --------------------------------------------------------------------------- #
# Abuse: dismiss_report (dead DISMISSED state)                                #
# --------------------------------------------------------------------------- #


async def _submit_report(db, *, entity_id: uuid.UUID) -> uuid.UUID:
    reporter = await register_verified(db, email=f"rep_{entity_id.hex[:8]}@vinuni.edu.vn")
    reporter_principal = Principal(user_id=reporter.id, persona="student")
    submitted = await report_service.submit(
        db, principal=reporter_principal, entity_type="company",
        entity_id=entity_id, reason_code="spam", note="junk", ctx=CTX,
    )
    return uuid.UUID(submitted["report"]["id"])


async def test_dismiss_report_closes_pending_and_audits(db_session) -> None:
    entity_id = uuid.uuid4()
    report_id = await _submit_report(db_session, entity_id=entity_id)
    staff = await _abuse_staff(db_session)

    dismissed = await triage_service.dismiss_report(
        db_session, principal=staff, report_id=report_id, note="false report", ctx=CTX
    )
    assert dismissed["status"] == "DISMISSED"

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "abuse.report_dismissed")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.after_snapshot == {"status": "DISMISSED"}


async def test_dismiss_report_rejects_already_triaged(db_session) -> None:
    entity_id = uuid.uuid4()
    report_id = await _submit_report(db_session, entity_id=entity_id)
    staff = await _abuse_staff(db_session)

    # Escalated -> TRIAGED; dismiss must then refuse (resolve on the review item).
    await triage_service.escalate_report(
        db_session, principal=staff, report_id=report_id, ctx=CTX
    )
    with pytest.raises(ValidationFailedError):
        await triage_service.dismiss_report(
            db_session, principal=staff, report_id=report_id, note=None, ctx=CTX
        )


async def test_triage_list_entity_type_filter_validates(db_session) -> None:
    staff = await _abuse_staff(db_session)
    with pytest.raises(ValidationFailedError):
        await triage_service.list_triage(
            db_session, principal=staff, entity_type="not_a_real_type"
        )


# --------------------------------------------------------------------------- #
# Shared SLA policy (pure helpers)                                            #
# --------------------------------------------------------------------------- #


def test_sla_health_transitions() -> None:
    now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    # Fresh 24h job: submitted just now, plenty of runway -> ok.
    fresh = sla.sla_health(
        submitted_at=now, due_by=now + timedelta(hours=24), now=now
    )
    assert fresh == sla.SLA_OK
    # 1h before a 24h deadline (< 25% window) -> amber.
    amber = sla.sla_health(
        submitted_at=now - timedelta(hours=23),
        due_by=now + timedelta(hours=1),
        now=now,
    )
    assert amber == sla.SLA_DUE_SOON
    # Past the deadline -> overdue.
    over = sla.sla_health(
        submitted_at=now - timedelta(hours=30),
        due_by=now - timedelta(hours=6),
        now=now,
    )
    assert over == sla.SLA_OVERDUE
    # No deadline -> nothing to breach.
    assert sla.sla_health(submitted_at=now, due_by=None, now=now) == sla.SLA_OK


def test_sla_fields_computes_due_by_from_policy() -> None:
    now = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    submitted = now - timedelta(hours=10)
    fields = sla.sla_fields(
        submitted_at=submitted, kind=sla.QUEUE_CONTENT_REPORT, now=now
    )
    # content_report SLA is 6h -> submitted 10h ago is overdue.
    assert fields["sla_hours"] == 6
    assert fields["is_overdue"] is True
    assert fields["sla_health"] == sla.SLA_OVERDUE
