"""B-553 Employer CRM: profile quality, seats, campus owner, risk flags,
university-only notes, event/campaign rollup, hiring outcomes.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.organization.application import crm_service
from app.modules.organization.application.errors import NotUniversityActorError
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


async def _audit_count(db_session, action: str) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _university_manager(db_session):
    """A university org + a staff principal holding ``partners:read``/``manage``."""

    _u, uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    return uni_admin, uni_org


# --------------------------------------------------------------------------- #
# Profile quality                                                             #
# --------------------------------------------------------------------------- #


async def test_profile_quality_rubric_is_deterministic_and_explainable(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    data = await crm_service.get_profile_quality(
        db_session, principal=admin, org_id=org.id
    )
    assert 0 <= data["score"] <= 100
    assert isinstance(data["breakdown"], list)
    # Verified at bootstrap + has one active recruiter (the admin) => some points.
    assert data["score"] > 0
    assert "missing" in data


async def test_profile_quality_denied_for_other_partner_org(db_session) -> None:
    _u_a, org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _u_b, org_b, _admin_b = await make_org_with_admin(db_session, display_name="B")
    with pytest.raises(PermissionDeniedError):
        await crm_service.get_profile_quality(
            db_session, principal=admin_a, org_id=org_b.id
        )


async def test_profile_quality_visible_to_university_actor(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    uni_admin, _uni_org = await _university_manager(db_session)
    data = await crm_service.get_profile_quality(
        db_session, principal=uni_admin, org_id=org.id
    )
    assert 0 <= data["score"] <= 100


# --------------------------------------------------------------------------- #
# Recruiter seats                                                             #
# --------------------------------------------------------------------------- #


async def test_recruiter_seats_reflects_active_members_and_cap(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    await add_member(db_session, org=org, permissions=[("jobs", "read")])
    data = await crm_service.recruiter_seats_summary(
        db_session, principal=admin, org_id=org.id
    )
    assert data["used"] == 2
    assert data["limit"] == org.max_team_members
    assert data["unlimited"] is False


# --------------------------------------------------------------------------- #
# Campus relationship owner (university-only write)                          #
# --------------------------------------------------------------------------- #


async def test_partner_cannot_set_campus_owner(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await crm_service.set_campus_owner(
            db_session, principal=admin, org_id=org.id,
            owner_user_id=admin.user_id, ctx=CTX,
        )


async def test_university_actor_can_set_and_audit_campus_owner(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    uni_user, _uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni2"
    )
    before = await _audit_count(db_session, "organization.campus_owner_set")
    result = await crm_service.set_campus_owner(
        db_session, principal=uni_admin, org_id=org.id,
        owner_user_id=uni_user.id, ctx=CTX,
    )
    assert result["campus_relationship_owner_id"] == str(uni_user.id)
    after = await _audit_count(db_session, "organization.campus_owner_set")
    assert after == before + 1

    fetched = await crm_service.get_campus_owner(
        db_session, principal=uni_admin, org_id=org.id
    )
    assert fetched["campus_relationship_owner_id"] == str(uni_user.id)


async def test_non_university_actor_cannot_read_campus_owner(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await crm_service.get_campus_owner(db_session, principal=admin, org_id=org.id)


# --------------------------------------------------------------------------- #
# Risk / trust flags (university-only)                                       #
# --------------------------------------------------------------------------- #


async def test_partner_cannot_raise_or_read_risk_flags(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await crm_service.raise_risk_flag(
            db_session, principal=admin, org_id=org.id, flag_type="spam_reports",
            severity="high", note=None, ctx=CTX,
        )
    with pytest.raises(PermissionDeniedError):
        await crm_service.list_risk_flags(db_session, principal=admin, org_id=org.id)


async def test_university_actor_raises_and_resolves_risk_flag(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _uni_user, _uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni3"
    )
    flag = await crm_service.raise_risk_flag(
        db_session, principal=uni_admin, org_id=org.id, flag_type="unverified_tax_id",
        severity="high", note="Tax ID pending verification.", ctx=CTX,
    )
    assert flag["is_resolved"] is False

    flags = await crm_service.list_risk_flags(
        db_session, principal=uni_admin, org_id=org.id
    )
    assert len(flags) == 1

    resolved = await crm_service.resolve_risk_flag(
        db_session, principal=uni_admin, org_id=org.id, flag_id=uuid.UUID(flag["id"]),
        resolution_note="Verified via tax authority API.", ctx=CTX,
    )
    assert resolved["is_resolved"] is True


async def test_invalid_severity_rejected(db_session) -> None:
    from app.shared.exceptions import ValidationFailedError

    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _uni_user, _uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni4"
    )
    with pytest.raises(ValidationFailedError):
        await crm_service.raise_risk_flag(
            db_session, principal=uni_admin, org_id=org.id, flag_type="x",
            severity="catastrophic", note=None, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# University-only notes (never visible to the partner org)                   #
# --------------------------------------------------------------------------- #


async def test_partner_cannot_create_or_read_notes(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await crm_service.create_note(
            db_session, principal=admin, org_id=org.id, body="note", ctx=CTX
        )
    with pytest.raises(PermissionDeniedError):
        await crm_service.list_notes(db_session, principal=admin, org_id=org.id)


async def test_university_actor_creates_note_and_audits(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _uni_user, _uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni5"
    )
    before = await _audit_count(db_session, "organization.note_created")
    note = await crm_service.create_note(
        db_session, principal=uni_admin, org_id=org.id,
        body="Flaky invoice history, follow up next quarter.", ctx=CTX,
    )
    after = await _audit_count(db_session, "organization.note_created")
    assert after == before + 1

    notes = await crm_service.list_notes(db_session, principal=uni_admin, org_id=org.id)
    assert notes[0]["id"] == note["id"]


async def test_empty_note_rejected(db_session) -> None:
    from app.shared.exceptions import ValidationFailedError

    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _uni_user, _uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni6"
    )
    with pytest.raises(ValidationFailedError):
        await crm_service.create_note(
            db_session, principal=uni_admin, org_id=org.id, body="   ", ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Event / campaign rollup + hiring outcomes (read-only joins)                 #
# --------------------------------------------------------------------------- #


async def test_crm_activity_rollup_empty_org(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    data = await crm_service.event_campaign_rollup(
        db_session, principal=admin, org_id=org.id
    )
    assert data["events"]["total"] == 0
    assert data["campaigns"]["total"] == 0


async def test_hiring_outcomes_empty_org(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    data = await crm_service.hiring_outcomes(db_session, principal=admin, org_id=org.id)
    assert data["total_applications"] == 0
    assert data["hired"] == 0
    assert data["offers_accepted"] == 0
