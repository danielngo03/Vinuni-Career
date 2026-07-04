"""Partner self-registration -> approval/rejection: happy path, duplicates,
idempotency, concurrency, activation, audit, and outbox notifications."""

from __future__ import annotations

import uuid

import pytest
from app.modules.auth.application import auth_service
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.organization.application import partner_registration_service as prs
from app.modules.organization.application.errors import (
    AlreadyRejectedError,
    DuplicateRegistrationError,
    VersionConflictError,
)
from app.modules.organization.domain.models import (
    Membership,
    Organization,
    PartnerRegistrationRequest,
)
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import email, make_org_with_admin


def _payload(**over) -> dict:
    base = {
        "company_name": "Acme Corp",
        "tax_code": "0123456789",
        "company_website": "https://acme.example",
        "company_size": "11-50",
        "industry": "technology",
        "description": "We build things.",
        "contact_name": "Nguyen Van A",
        "contact_title": "HR Manager",
        "contact_email": email("contact"),
        "contact_phone": "+84912345678",
        "logo_upload_id": None,
    }
    base.update(over)
    return base


async def _reviewer(db_session):
    # A university admin holds *:* -> partners:approve/reject.
    _u, _org, principal = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni", admin_email=email("uni")
    )
    return principal


async def _outbox(db_session, template_key: str):
    return (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == template_key
            )
        )
    ).scalars().all()


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


async def test_register_creates_pending_request_and_ack(db_session) -> None:
    result = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    assert result["status"] == "pending_review"
    req = (
        await db_session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.id == uuid.UUID(result["registration_id"])
            )
        )
    ).scalar_one()
    assert req.status == "pending_review"
    assert req.created_org_id is None
    # No org / user created yet.
    assert (
        await db_session.execute(select(func.count()).select_from(Organization))
    ).scalar_one() == 0
    # Ack notification enqueued; no SMTP contacted (status pending).
    acks = await _outbox(db_session, "partner.registration_received")
    assert len(acks) == 1 and acks[0].status == "pending"


async def test_duplicate_email_rejected_but_idempotency_key_returns_existing(db_session) -> None:
    p = _payload()
    first = await prs.register_partner(db_session, payload=p, ctx=CTX)
    with pytest.raises(DuplicateRegistrationError):
        await prs.register_partner(db_session, payload=_payload(
            contact_email=p["contact_email"], tax_code="9999"
        ), ctx=CTX)
    again = await prs.register_partner(
        db_session, payload=_payload(contact_email=p["contact_email"]),
        ctx=CTX, idempotency_key="abc-123",
    )
    assert again["registration_id"] == first["registration_id"]


async def test_duplicate_tax_code_rejected(db_session) -> None:
    await prs.register_partner(db_session, payload=_payload(tax_code="555"), ctx=CTX)
    with pytest.raises(DuplicateRegistrationError):
        await prs.register_partner(
            db_session,
            payload=_payload(tax_code="555", contact_email=email("other")),
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Approval                                                                     #
# --------------------------------------------------------------------------- #


async def test_approve_bootstraps_org_admin_and_audits(db_session) -> None:
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    reviewer = await _reviewer(db_session)

    out = await prs.approve_partner(
        db_session, principal=reviewer,
        partner_id=uuid.UUID(reg["registration_id"]),
        trust_level="verified", note="welcome", ctx=CTX,
    )
    assert out["status"] == "approved"
    org_id = uuid.UUID(out["organization_id"])
    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    assert org.org_type == "partner"
    assert org.status == "active"
    assert org.is_verified is True
    assert org.trust_level == "verified"

    # First admin membership exists.
    members = (
        await db_session.execute(
            select(Membership).where(Membership.org_id == org_id)
        )
    ).scalars().all()
    assert len(members) == 1 and members[0].status == "active"

    # Audit trail for the approval + bootstrap.
    for action in (
        "partner_registration.approved",
        "organization.created",
        "role.created",
        "membership.created",
    ):
        count = (
            await db_session.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == action
                )
            )
        ).scalar_one()
        assert count >= 1, action

    # Activation email enqueued with a token (no SMTP; status pending).
    approved = await _outbox(db_session, "partner.registration_approved")
    assert len(approved) == 1
    assert approved[0].status == "pending"
    assert approved[0].variables.get("token")


async def test_approve_is_idempotent(db_session) -> None:
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    reviewer = await _reviewer(db_session)
    pid = uuid.UUID(reg["registration_id"])
    first = await prs.approve_partner(
        db_session, principal=reviewer, partner_id=pid, trust_level="standard", ctx=CTX
    )
    second = await prs.approve_partner(
        db_session, principal=reviewer, partner_id=pid, trust_level="standard", ctx=CTX
    )
    assert first["organization_id"] == second["organization_id"]
    # Exactly one partner org created.
    count = (
        await db_session.execute(
            select(func.count()).select_from(Organization).where(
                Organization.org_type == "partner"
            )
        )
    ).scalar_one()
    assert count == 1


async def test_concurrent_approve_version_conflict(db_session) -> None:
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    reviewer = await _reviewer(db_session)
    pid = uuid.UUID(reg["registration_id"])
    await prs.approve_partner(
        db_session, principal=reviewer, partner_id=pid, trust_level="standard",
        version=1, ctx=CTX,
    )
    # A second reviewer holding the stale version loses.
    with pytest.raises(VersionConflictError):
        await prs.approve_partner(
            db_session, principal=reviewer, partner_id=pid, trust_level="standard",
            version=1, ctx=CTX,
        )


async def test_approved_admin_can_activate_and_login(db_session) -> None:
    p = _payload()
    reg = await prs.register_partner(db_session, payload=p, ctx=CTX)
    reviewer = await _reviewer(db_session)
    await prs.approve_partner(
        db_session, principal=reviewer,
        partner_id=uuid.UUID(reg["registration_id"]), trust_level="standard", ctx=CTX,
    )
    approved = await _outbox(db_session, "partner.registration_approved")
    token = approved[0].variables["token"]
    # Admin sets a password + verifies via the activation token.
    user = await auth_service.activate_account(
        db_session, token=token, password="Sup3rSecret!", ctx=CTX
    )
    assert user.is_email_verified is True
    # And can now log in.
    login = await auth_service.login(
        db_session, email=p["contact_email"], password="Sup3rSecret!", ctx=CTX
    )
    assert login.tokens.access_token


# --------------------------------------------------------------------------- #
# Rejection                                                                    #
# --------------------------------------------------------------------------- #


async def test_reject_creates_nothing_and_notifies(db_session) -> None:
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    reviewer = await _reviewer(db_session)
    out = await prs.reject_partner(
        db_session, principal=reviewer,
        partner_id=uuid.UUID(reg["registration_id"]),
        reason="Hồ sơ chưa đầy đủ.", ctx=CTX,
    )
    assert out["status"] == "rejected"
    # No partner org created.
    count = (
        await db_session.execute(
            select(func.count()).select_from(Organization).where(
                Organization.org_type == "partner"
            )
        )
    ).scalar_one()
    assert count == 0
    rejected = await _outbox(db_session, "partner.registration_rejected")
    assert len(rejected) == 1


async def test_approve_after_reject_conflicts(db_session) -> None:
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    reviewer = await _reviewer(db_session)
    pid = uuid.UUID(reg["registration_id"])
    await prs.reject_partner(
        db_session, principal=reviewer, partner_id=pid, reason="no", ctx=CTX
    )
    with pytest.raises(AlreadyRejectedError):
        await prs.approve_partner(
            db_session, principal=reviewer, partner_id=pid, trust_level="standard",
            ctx=CTX,
        )


async def test_partner_admin_cannot_approve_partners(db_session) -> None:
    # A partner Admin holds *:* but is NOT a university actor -> denied.
    reg = await prs.register_partner(db_session, payload=_payload(), ctx=CTX)
    _u, _org, partner_admin = await make_org_with_admin(
        db_session, org_type="partner", display_name="Other Partner"
    )
    from app.shared.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        await prs.approve_partner(
            db_session, principal=partner_admin,
            partner_id=uuid.UUID(reg["registration_id"]), trust_level="standard",
            ctx=CTX,
        )


async def test_re_register_allowed_after_rejection(db_session) -> None:
    p = _payload()
    reg = await prs.register_partner(db_session, payload=p, ctx=CTX)
    reviewer = await _reviewer(db_session)
    await prs.reject_partner(
        db_session, principal=reviewer,
        partner_id=uuid.UUID(reg["registration_id"]), reason="incomplete", ctx=CTX,
    )
    # Same contact may register again (no pending request blocks it).
    again = await prs.register_partner(db_session, payload=p, ctx=CTX)
    assert again["status"] == "pending_review"
    assert again["registration_id"] != reg["registration_id"]
