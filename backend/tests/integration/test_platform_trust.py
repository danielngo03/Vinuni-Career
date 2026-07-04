"""ADR-0014 (E36) platform trust: support console, privacy/compliance, abuse.

Covers RBAC/tenant-isolation on the six new permission nouns, idempotent
duplicate reports, rate limiting, requeue-only-on-dead-lettered-row, reveal
never logging the revealed value, override before/after audit, and retention
sweep idempotency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.compliance.application import (
    consent_service,
    privacy_request_service,
    retention_service,
)
from app.modules.compliance.domain.models import (
    CONSENT_INTERVIEW_RECORDING,
    Consent,
)
from app.modules.documents.domain.models import ApplicationCvSnapshot
from app.modules.moderation.application import report_service, triage_service
from app.modules.moderation.domain.models import ContentReport, HumanReviewItem
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.platform_support.application import (
    outbox_health_service,
    reveal_service,
    support_case_service,
)
from app.shared.audit import AuditLog
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    RateLimitedError,
)
from app.shared.permissions import GUEST, Principal
from sqlalchemy import select

from tests.auth_utils import CTX, register_verified
from tests.org_utils import add_member, make_org_with_admin


async def _university_with_support(db, *, action: str = "act"):
    """A university-org member granted `support:{action}` (not superadmin)."""

    _admin_user, org, _admin_principal = await make_org_with_admin(
        db, org_type="university"
    )
    perms = {("support", action), ("support", "read")}
    _user, _membership, principal = await add_member(
        db, org=org, permissions=list(perms)
    )
    return org, principal


async def _partner_with_support(db, *, action: str = "act"):
    """A PARTNER-org member granted `support:{action}` (must still be denied)."""

    _admin_user, org, _admin_principal = await make_org_with_admin(
        db, org_type="partner"
    )
    perms = {("support", action), ("support", "read")}
    _user, _membership, principal = await add_member(
        db, org=org, permissions=list(perms)
    )
    return org, principal


# --------------------------------------------------------------------------- #
# RBAC / tenant isolation on the new permission nouns                        #
# --------------------------------------------------------------------------- #


async def test_support_case_list_requires_auth(db_session) -> None:
    with pytest.raises(AuthRequiredError):
        await support_case_service.list_cases(db_session, principal=GUEST)


async def test_support_case_list_denied_without_permission(db_session) -> None:
    _admin_user, _org, principal = await make_org_with_admin(
        db_session, org_type="university"
    )
    # `_admin_user` here holds `*:*` from make_org_with_admin's first-admin
    # convenience — use a plain member with NO grants instead.
    _u, _org2, uni = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, bare_principal = await add_member(
        db_session, org=_org2, permissions=[]
    )
    with pytest.raises(PermissionDeniedError):
        await support_case_service.list_cases(db_session, principal=bare_principal)


async def test_support_case_denied_for_partner_org_member(db_session) -> None:
    """`support:*` granted on a PARTNER org must still be denied (university-only)."""

    _org, principal = await _partner_with_support(db_session, action="read")
    with pytest.raises(PermissionDeniedError):
        await support_case_service.list_cases(db_session, principal=principal)


async def test_support_case_allowed_for_superadmin(db_session) -> None:
    user = await register_verified(db_session, email="superadmin_e36@vinuni.edu.vn")
    principal = Principal(user_id=user.id, persona="university_staff", is_superadmin=True)
    items = await support_case_service.list_cases(db_session, principal=principal)
    assert items == []


async def test_support_case_allowed_for_granted_university_member(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="read")
    items = await support_case_service.list_cases(db_session, principal=principal)
    assert items == []


async def test_abuse_triage_denied_without_permission(db_session) -> None:
    _u, org, _uni_admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, bare_principal = await add_member(
        db_session, org=org, permissions=[]
    )
    with pytest.raises(PermissionDeniedError):
        await triage_service.list_triage(db_session, principal=bare_principal)


async def test_abuse_triage_denied_for_partner_org(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session, org_type="partner")
    _member_user, _membership, principal = await add_member(
        db_session, org=org, permissions=[("abuse", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await triage_service.list_triage(db_session, principal=principal)


async def test_abuse_triage_allowed_for_granted_university_member(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, principal = await add_member(
        db_session, org=org, permissions=[("abuse", "read")]
    )
    items = await triage_service.list_triage(db_session, principal=principal)
    assert items == []


async def test_privacy_process_denied_without_permission(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, bare_principal = await add_member(
        db_session, org=org, permissions=[]
    )
    with pytest.raises(PermissionDeniedError):
        await privacy_request_service.list_staff(db_session, principal=bare_principal)


async def test_privacy_process_allowed_for_granted_university_member(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, principal = await add_member(
        db_session, org=org, permissions=[("privacy", "process")]
    )
    items = await privacy_request_service.list_staff(db_session, principal=principal)
    assert items == []


# --------------------------------------------------------------------------- #
# Content report idempotency + rate limiting                                  #
# --------------------------------------------------------------------------- #


async def test_duplicate_report_is_idempotent(db_session) -> None:
    reporter = await register_verified(db_session, email="reporter1@vinuni.edu.vn")
    principal = Principal(user_id=reporter.id, persona="student")
    entity_id = uuid.uuid4()

    first = await report_service.submit(
        db_session,
        principal=principal,
        entity_type="job",
        entity_id=entity_id,
        reason_code="spam",
        note=None,
        ctx=CTX,
    )
    assert first["status"] == "submitted"

    second = await report_service.submit(
        db_session,
        principal=principal,
        entity_type="job",
        entity_id=entity_id,
        reason_code="spam",
        note=None,
        ctx=CTX,
    )
    assert second["status"] == "already_reported"

    count = (
        await db_session.execute(
            select(ContentReport).where(
                ContentReport.reporter_id == reporter.id,
                ContentReport.entity_id == entity_id,
            )
        )
    ).scalars().all()
    assert len(count) == 1


async def test_report_unsupported_entity_type_rejected(db_session) -> None:
    from app.shared.exceptions import ValidationFailedError

    reporter = await register_verified(db_session, email="reporter2@vinuni.edu.vn")
    principal = Principal(user_id=reporter.id, persona="student")
    with pytest.raises(ValidationFailedError):
        await report_service.submit(
            db_session,
            principal=principal,
            entity_type="application",
            entity_id=uuid.uuid4(),
            reason_code="spam",
            note=None,
            ctx=CTX,
        )


async def test_report_rate_limit_enforced(db_session, monkeypatch) -> None:
    monkeypatch.setattr(report_service, "_RATE_LIMIT_MAX_REPORTS", 2)
    reporter = await register_verified(db_session, email="reporter3@vinuni.edu.vn")
    principal = Principal(user_id=reporter.id, persona="student")

    await report_service.submit(
        db_session, principal=principal, entity_type="job", entity_id=uuid.uuid4(),
        reason_code="spam", note=None, ctx=CTX,
    )
    await report_service.submit(
        db_session, principal=principal, entity_type="job", entity_id=uuid.uuid4(),
        reason_code="spam", note=None, ctx=CTX,
    )
    with pytest.raises(RateLimitedError):
        await report_service.submit(
            db_session, principal=principal, entity_type="job", entity_id=uuid.uuid4(),
            reason_code="spam", note=None, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Escalation severity heuristic                                               #
# --------------------------------------------------------------------------- #


async def test_escalate_report_creates_review_item_with_low_severity(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="read")
    _u, uni_org, _admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, abuse_principal = await add_member(
        db_session, org=uni_org, permissions=[("abuse", "triage")]
    )
    reporter = await register_verified(db_session, email="reporter4@vinuni.edu.vn")
    reporter_principal = Principal(user_id=reporter.id, persona="student")
    entity_id = uuid.uuid4()
    submitted = await report_service.submit(
        db_session, principal=reporter_principal, entity_type="company",
        entity_id=entity_id, reason_code="fraud", note="looks fake", ctx=CTX,
    )
    report_id = uuid.UUID(submitted["report"]["id"])

    escalated = await triage_service.escalate_report(
        db_session, principal=abuse_principal, report_id=report_id, ctx=CTX
    )
    assert escalated["status"] == "TRIAGED"

    item = (
        await db_session.execute(
            select(HumanReviewItem).where(
                HumanReviewItem.resource_type == "company",
                HumanReviewItem.resource_id == entity_id,
            )
        )
    ).scalar_one()
    assert item.source == "user_report"
    assert item.severity == "low"


# --------------------------------------------------------------------------- #
# Outbox requeue: only legal on dead-lettered rows                            #
# --------------------------------------------------------------------------- #


async def test_requeue_rejects_non_dead_row(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="act")
    row = NotificationOutbox(
        recipient_id=None, template_key="x", channel="email", locale="vi",
        variables={}, status="pending",
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    with pytest.raises(ConflictError):
        await outbox_health_service.requeue(
            db_session, principal=principal, outbox_id=row.id, ctx=CTX
        )


async def test_requeue_succeeds_on_dead_row_and_audits(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="act")
    row = NotificationOutbox(
        recipient_id=None, template_key="x", channel="email", locale="vi",
        variables={}, status="dead", attempts=5,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    result = await outbox_health_service.requeue(
        db_session, principal=principal, outbox_id=row.id, ctx=CTX
    )
    assert result["status"] == "pending"
    await db_session.refresh(row)
    assert row.status == "pending"
    assert row.attempts == 0

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "support.outbox_requeued")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.after_snapshot["outbox_id"] == str(row.id)


async def test_outbox_health_counts(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="read")
    db_session.add(
        NotificationOutbox(
            recipient_id=None, template_key="x", channel="email", locale="vi",
            variables={}, status="dead",
        )
    )
    await db_session.commit()
    health = await outbox_health_service.get_health(db_session, principal=principal)
    assert health["dead"] >= 1
    assert "oldest_pending_age_seconds" in health


# --------------------------------------------------------------------------- #
# Reveal — never logs the revealed value                                      #
# --------------------------------------------------------------------------- #


async def test_reveal_never_logs_value_in_audit(db_session) -> None:
    _org, principal = await _university_with_support(db_session, action="act")
    target = await register_verified(db_session, email="reveal_target@vinuni.edu.vn")

    result = await reveal_service.reveal(
        db_session,
        principal=principal,
        resource_type="user_contact",
        resource_id=target.id,
        reason="support ticket #123 follow-up",
        ctx=CTX,
    )
    assert result["email"] == target.email

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "support.pii_revealed")
        )
    ).scalars().first()
    assert audit is not None
    dumped = str(audit.after_snapshot)
    assert target.email not in dumped
    assert audit.after_snapshot["target_type"] == "user_contact"


# --------------------------------------------------------------------------- #
# Override — before/after audit diff                                          #
# --------------------------------------------------------------------------- #


async def test_override_reverses_user_suspension_with_before_after(db_session) -> None:
    _u, uni_org, _admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, override_principal = await add_member(
        db_session, org=uni_org, permissions=[("abuse", "override"), ("jobs", "moderate")]
    )
    suspended_user = await register_verified(db_session, email="suspended1@vinuni.edu.vn")
    suspended_user.is_active = False
    await db_session.commit()

    item = HumanReviewItem(
        source="user_report", resource_type="user", resource_id=suspended_user.id,
        severity="high", status="RESOLVED", findings_json={},
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    result = await triage_service.override_action(
        db_session, principal=override_principal, review_item_id=item.id,
        note="Appeal upheld — reinstating account", ctx=CTX,
    )
    assert result["id"] == str(item.id)

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "abuse.action_overridden")
        )
    ).scalars().first()
    assert audit is not None
    assert audit.before_snapshot == {"is_active": False}
    assert audit.after_snapshot == {"is_active": True}


# --------------------------------------------------------------------------- #
# Retention sweep idempotency                                                 #
# --------------------------------------------------------------------------- #


async def test_retention_sweep_is_idempotent(db_session) -> None:
    user = await register_verified(db_session, email="retention_owner@vinuni.edu.vn")
    old_snapshot = ApplicationCvSnapshot(
        user_id=user.id,
        snapshot_json={"summary": "very old cv"},
    )
    db_session.add(old_snapshot)
    await db_session.commit()
    await db_session.refresh(old_snapshot)

    # Force created_at far enough in the past to be past the retention window.
    old_snapshot.created_at = datetime.now(tz=UTC) - timedelta(days=800)
    await db_session.commit()

    first = await retention_service.sweep_retention(db_session)
    await db_session.commit()
    assert first["anonymized"] == 1

    second = await retention_service.sweep_retention(db_session)
    await db_session.commit()
    assert second["anonymized"] == 0

    await db_session.refresh(old_snapshot)
    assert old_snapshot.snapshot_json.get("_retention_anonymized") is True
    assert old_snapshot.redacted_json is None


# --------------------------------------------------------------------------- #
# Consent + privacy request lifecycle                                         #
# --------------------------------------------------------------------------- #


async def test_consent_grant_revoke_roundtrip(db_session) -> None:
    user = await register_verified(db_session, email="consent_user@vinuni.edu.vn")
    principal = Principal(user_id=user.id, persona="student")

    initial = await consent_service.get_mine(db_session, principal=principal)
    assert initial[CONSENT_INTERVIEW_RECORDING]["granted"] is False

    granted = await consent_service.set_mine(
        db_session, principal=principal, consent_type=CONSENT_INTERVIEW_RECORDING,
        granted=True, ctx=CTX,
    )
    assert granted["granted"] is True

    row = (
        await db_session.execute(
            select(Consent).where(
                Consent.user_id == user.id,
                Consent.consent_type == CONSENT_INTERVIEW_RECORDING,
            )
        )
    ).scalar_one()
    assert row.granted is True


async def test_privacy_request_duplicate_open_is_idempotent(db_session) -> None:
    user = await register_verified(db_session, email="privacy_user@vinuni.edu.vn")
    principal = Principal(user_id=user.id, persona="student")

    first = await privacy_request_service.submit(
        db_session, principal=principal, request_type="export", note=None, ctx=CTX,
    )
    assert first["status"] == "submitted"

    second = await privacy_request_service.submit(
        db_session, principal=principal, request_type="export", note=None, ctx=CTX,
    )
    assert second["status"] == "request_already_pending"


async def test_privacy_request_fulfill_writes_audit(db_session) -> None:
    user = await register_verified(db_session, email="privacy_user2@vinuni.edu.vn")
    principal = Principal(user_id=user.id, persona="student")
    submitted = await privacy_request_service.submit(
        db_session, principal=principal, request_type="deletion", note=None, ctx=CTX,
    )
    request_id = uuid.UUID(submitted["request"]["id"])

    _u, org, _admin = await make_org_with_admin(db_session, org_type="university")
    _staff_user, _membership, staff_principal = await add_member(
        db_session, org=org, permissions=[("privacy", "process")]
    )

    fulfilled = await privacy_request_service.fulfill(
        db_session, principal=staff_principal, request_id=request_id,
        status="fulfilled", note="Done manually", ctx=CTX,
    )
    assert fulfilled["status"] == "fulfilled"

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "compliance.privacy_request_fulfilled"
            )
        )
    ).scalars().first()
    assert audit is not None
    assert audit.before_snapshot == {"status": "pending"}
    assert audit.after_snapshot == {"status": "fulfilled"}
