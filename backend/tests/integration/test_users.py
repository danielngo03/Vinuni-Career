"""Integration tests for the ``users`` module.

Covers:
- ``admin_users_service``: university-governance user list/suspend/unsuspend
  (RBAC boundary, self-suspend guard, not-found, empty-state).
- ``user_service``: identity bootstrap lookups (get_by_email/get_by_id,
  add_identity/list_identities/primary_identity).
- ``preferences_service``: notification/account preference read + patch,
  mandatory-category lock, and validation failures.
- ``student_directory_facade``: PII-safe display-name resolution.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.users.application import admin_users_service, preferences_service, user_service
from app.modules.users.application.student_directory_facade import DEPARTED_LABEL, display_for
from app.modules.users.domain.models import Identity, User
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX, register_verified
from tests.documents_utils import make_student
from tests.org_utils import add_member, email, make_org_with_admin


async def _make_superadmin_principal(db_session) -> Principal:
    """A real, verified user promoted to platform superadmin (``org_id=None``)."""

    user = await register_verified(db_session, email=email("super"))
    row = (await db_session.execute(select(User).where(User.id == user.id))).scalar_one()
    row.is_superadmin = True
    await db_session.commit()
    return Principal(
        user_id=user.id, persona="university_staff", org_id=None,
        is_superadmin=True, permissions=frozenset(),
    )


async def _audit_count(db_session, action: str, resource_id) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == action, AuditLog.resource_id == resource_id
            )
        )
    ).scalar_one()


async def _make_partner_member(db_session, org):
    """A user whose PRIMARY identity is partner_member in ``org`` (control-plane
    governs partner-member accounts, not just students)."""

    user = await register_verified(db_session, email=email("pm"))
    # Flip the registration-default student identity off primary, add a primary
    # partner_member identity in the partner org.
    student_ident = (
        await db_session.execute(
            select(Identity).where(
                Identity.user_id == user.id, Identity.is_primary.is_(True)
            )
        )
    ).scalar_one()
    student_ident.is_primary = False
    await user_service.add_identity(
        db_session, user_id=user.id, persona="partner_member",
        org_id=org.id, is_primary=True,
    )
    await db_session.commit()
    return user


# --------------------------------------------------------------------------- #
# admin_users_service.list_platform_users                                     #
# --------------------------------------------------------------------------- #


async def test_university_admin_lists_platform_users(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    student_user, _student = await make_student(db_session, prefix="alice")

    result = await admin_users_service.list_platform_users(db_session, principal=uni)
    emails = {row["email"] for row in result["items"]}
    assert student_user.email in emails
    assert result["total"] >= 2  # uni admin + student


async def test_list_platform_users_filters_by_persona_and_query(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    student_user, _student = await make_student(db_session, prefix="findme")

    result = await admin_users_service.list_platform_users(
        db_session, principal=uni, persona="student", q="findme"
    )
    assert all(row["persona"] == "student" for row in result["items"])
    assert any(row["email"] == student_user.email for row in result["items"])


async def test_list_platform_users_unknown_persona_filter_is_ignored(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    result = await admin_users_service.list_platform_users(
        db_session, principal=uni, persona="not_a_real_persona"
    )
    # Invalid persona silently ignored -> falls back to unfiltered list (still >= 1: the admin).
    assert result["total"] >= 1


async def test_partner_admin_cannot_list_platform_users(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session, org_type="partner")
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.list_platform_users(db_session, principal=partner_admin)


async def test_student_cannot_list_platform_users(db_session) -> None:
    _, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.list_platform_users(db_session, principal=student)


async def test_list_platform_users_empty_query_yields_no_results(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    result = await admin_users_service.list_platform_users(
        db_session, principal=uni, q="no-such-user-xyz-123"
    )
    assert result["items"] == []
    assert result["total"] == 0


# --------------------------------------------------------------------------- #
# admin_users_service.suspend_user / unsuspend_user                           #
# --------------------------------------------------------------------------- #


async def test_university_admin_can_suspend_and_unsuspend_user(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    student_user, _student = await make_student(db_session)

    suspended = await admin_users_service.suspend_user(
        db_session, principal=uni, ctx=CTX, user_id=student_user.id, reason="Spam reports"
    )
    assert suspended["is_active"] is False

    restored = await admin_users_service.unsuspend_user(
        db_session, principal=uni, ctx=CTX, user_id=student_user.id, reason="Appeal accepted"
    )
    assert restored["is_active"] is True


async def test_admin_cannot_suspend_self(db_session) -> None:
    admin_user, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=uni, ctx=CTX, user_id=admin_user.id, reason="x"
        )


async def test_suspend_nonexistent_user_raises_not_found(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(ResourceNotFoundError):
        await admin_users_service.suspend_user(
            db_session, principal=uni, ctx=CTX, user_id=uuid.uuid4(), reason="x"
        )


async def test_partner_admin_cannot_suspend_user(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session, org_type="partner")
    student_user, _student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=partner_admin, ctx=CTX,
            user_id=student_user.id, reason="x",
        )


# --------------------------------------------------------------------------- #
# Cross-persona account governance (accounts:govern grant, audit, protection)  #
# --------------------------------------------------------------------------- #


async def test_granted_governor_can_suspend_student(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    student_user, _student = await make_student(db_session)

    before = await _audit_count(db_session, "account.suspended", student_user.id)
    result = await admin_users_service.suspend_user(
        db_session, principal=governor, ctx=CTX,
        user_id=student_user.id, reason="Multiple abuse reports",
    )
    assert result["is_active"] is False

    await db_session.refresh(student_user)
    assert student_user.is_active is False
    assert await _audit_count(db_session, "account.suspended", student_user.id) == before + 1

    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "account.suspended",
                AuditLog.resource_id == student_user.id,
            )
        )
    ).scalars().all()[-1]
    assert row.after_snapshot["reason"] == "Multiple abuse reports"
    assert row.after_snapshot["target_persona"] == "student"
    assert row.actor_id == governor.user_id


async def test_granted_governor_can_suspend_partner_member(db_session) -> None:
    # The control plane governs partner accounts too: a partner-member user
    # (another org's member) can be suspended by a university governor.
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    _pu, porg, _padmin = await make_org_with_admin(
        db_session, org_type="partner", display_name="Acme"
    )
    partner_user = await _make_partner_member(db_session, porg)

    result = await admin_users_service.suspend_user(
        db_session, principal=governor, ctx=CTX,
        user_id=partner_user.id, reason="Fraudulent listings",
    )
    assert result["is_active"] is False
    await db_session.refresh(partner_user)
    assert partner_user.is_active is False

    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "account.suspended",
                AuditLog.resource_id == partner_user.id,
            )
        )
    ).scalars().all()[-1]
    assert row.after_snapshot["target_persona"] == "partner_member"


async def test_governor_empty_reason_rejected_and_no_write(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    student_user, _student = await make_student(db_session)

    for bad in ("", "   "):
        with pytest.raises(ValidationFailedError):
            await admin_users_service.suspend_user(
                db_session, principal=governor, ctx=CTX,
                user_id=student_user.id, reason=bad,
            )
    # No mutation and no audit row on rejected reason.
    await db_session.refresh(student_user)
    assert student_user.is_active is True
    assert await _audit_count(db_session, "account.suspended", student_user.id) == 0


async def test_ungranted_university_staffer_denied(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _mu, _m, ungranted = await add_member(
        db_session, org=uni, permissions=[("jobs", "read")], role_name="NoGovern"
    )
    student_user, _student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=ungranted, ctx=CTX,
            user_id=student_user.id, reason="x",
        )
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.list_platform_users(db_session, principal=ungranted)


async def test_partner_wildcard_holder_denied_for_governance(db_session) -> None:
    # A partner Admin holds ``*:*`` (matches ``accounts:govern``) but is NOT a
    # university org -> the org-type gate blocks it (mirrors taxonomy/support).
    _u, _porg, partner_admin = await make_org_with_admin(db_session, org_type="partner")
    student_user, _student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=partner_admin, ctx=CTX,
            user_id=student_user.id, reason="x",
        )
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.list_platform_users(db_session, principal=partner_admin)


async def test_superadmin_can_govern_accounts(db_session) -> None:
    superadmin = await _make_superadmin_principal(db_session)
    student_user, _student = await make_student(db_session)

    result = await admin_users_service.suspend_user(
        db_session, principal=superadmin, ctx=CTX,
        user_id=student_user.id, reason="Platform action",
    )
    assert result["is_active"] is False
    assert await _audit_count(db_session, "account.suspended", student_user.id) == 1


async def test_non_superadmin_governor_cannot_govern_superadmin_target(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    # Seed a superadmin target.
    target = await register_verified(db_session, email=email("sa-target"))
    row = (await db_session.execute(select(User).where(User.id == target.id))).scalar_one()
    row.is_superadmin = True
    await db_session.commit()

    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=governor, ctx=CTX, user_id=target.id, reason="x"
        )
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.get_account_detail(
            db_session, principal=governor, user_id=target.id
        )
    # Target untouched.
    await db_session.refresh(row)
    assert row.is_active is True


async def test_superadmin_may_govern_superadmin_target(db_session) -> None:
    superadmin = await _make_superadmin_principal(db_session)
    target = await register_verified(db_session, email=email("sa-target2"))
    row = (await db_session.execute(select(User).where(User.id == target.id))).scalar_one()
    row.is_superadmin = True
    await db_session.commit()

    result = await admin_users_service.suspend_user(
        db_session, principal=superadmin, ctx=CTX, user_id=target.id, reason="Ops action"
    )
    assert result["is_active"] is False


async def test_governor_detail_is_privacy_safe(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    student_user, _student = await make_student(db_session)

    detail = await admin_users_service.get_account_detail(
        db_session, principal=governor, user_id=student_user.id
    )
    assert detail["core"]["email"] == student_user.email
    assert detail["core"]["is_active"] is True
    assert isinstance(detail["identities"], list)
    assert "active_session_count" in detail
    # Privacy: no password hash, raw tokens, or AI internals leak.
    flat = str(detail)
    for forbidden in ("password_hash", "token", "ip_hash", "user_agent"):
        assert forbidden not in flat


async def test_reinstate_writes_reason_audit(db_session) -> None:
    _u, uni, _admin = await make_org_with_admin(db_session, org_type="university")
    _gu, _m, governor = await add_member(
        db_session, org=uni, permissions=[("accounts", "govern")], role_name="AcctGov"
    )
    student_user, _student = await make_student(db_session)
    await admin_users_service.suspend_user(
        db_session, principal=governor, ctx=CTX, user_id=student_user.id, reason="Investigation"
    )
    result = await admin_users_service.unsuspend_user(
        db_session, principal=governor, ctx=CTX, user_id=student_user.id, reason="Cleared"
    )
    assert result["is_active"] is True
    assert await _audit_count(db_session, "account.reinstated", student_user.id) == 1


# --------------------------------------------------------------------------- #
# user_service — identity bootstrap                                          #
# --------------------------------------------------------------------------- #


async def test_create_user_and_lookup_by_email_and_id(db_session) -> None:
    created = await user_service.create_user(
        db_session, email="New.User@VinUni.Edu.Vn", password_hash="hash", full_name="New User"
    )
    assert created.email == "new.user@vinuni.edu.vn"  # normalized

    by_email = await user_service.get_by_email(db_session, "New.User@VinUni.Edu.Vn")
    assert by_email is not None
    assert by_email.id == created.id

    by_id = await user_service.get_by_id(db_session, created.id)
    assert by_id is not None
    assert by_id.email == created.email


async def test_get_by_email_unknown_returns_none(db_session) -> None:
    assert await user_service.get_by_email(db_session, "ghost@vinuni.edu.vn") is None


async def test_get_by_id_unknown_returns_none(db_session) -> None:
    assert await user_service.get_by_id(db_session, uuid.uuid4()) is None


async def test_add_identity_and_list_identities_primary_first(db_session) -> None:
    user = await user_service.create_user(
        db_session, email="multi@vinuni.edu.vn", password_hash=None, full_name="Multi Persona"
    )
    secondary = await user_service.add_identity(
        db_session, user_id=user.id, persona="student", is_primary=False
    )
    primary = await user_service.add_identity(
        db_session, user_id=user.id, persona="partner_member", is_primary=True
    )

    identities = await user_service.list_identities(db_session, user.id)
    assert identities[0].id == primary.id
    assert {i.id for i in identities} == {secondary.id, primary.id}

    resolved_primary = await user_service.primary_identity(db_session, user.id)
    assert resolved_primary is not None
    assert resolved_primary.id == primary.id


async def test_list_identities_empty_for_fresh_user(db_session) -> None:
    user = await user_service.create_user(
        db_session, email="lonely@vinuni.edu.vn", password_hash=None, full_name="Lonely"
    )
    identities = await user_service.list_identities(db_session, user.id)
    assert identities == []
    assert await user_service.primary_identity(db_session, user.id) is None


async def test_get_identity_scoped_to_owning_user(db_session) -> None:
    user = await user_service.create_user(
        db_session, email="owner@vinuni.edu.vn", password_hash=None, full_name="Owner"
    )
    other_user = await user_service.create_user(
        db_session, email="other@vinuni.edu.vn", password_hash=None, full_name="Other"
    )
    identity = await user_service.add_identity(db_session, user_id=user.id, persona="student")

    found = await user_service.get_identity(db_session, identity_id=identity.id, user_id=user.id)
    assert found is not None

    not_found_for_other = await user_service.get_identity(
        db_session, identity_id=identity.id, user_id=other_user.id
    )
    assert not_found_for_other is None


# --------------------------------------------------------------------------- #
# preferences_service                                                         #
# --------------------------------------------------------------------------- #


async def test_get_preferences_returns_default_catalogue_for_new_user(db_session) -> None:
    student_user, _student = await make_student(db_session)
    prefs = await preferences_service.get_preferences(db_session, student_user.id)

    assert prefs["locale"] in {"vi", "en"}
    assert "security_alert" in prefs["categories"]
    assert prefs["categories"]["security_alert"]["locked"] is True
    assert prefs["categories"]["security_alert"]["email"] == "mandatory"
    assert prefs["categories"]["message"]["locked"] is False


async def test_patch_preferences_updates_locale_theme_and_category(db_session) -> None:
    student_user, _student = await make_student(db_session)

    updated = await preferences_service.patch_preferences(
        db_session,
        student_user.id,
        {
            "locale": "en",
            "theme": "dark",
            "categories": {"job_digest": {"in_app": False, "email": "off"}},
        },
    )
    assert updated["locale"] == "en"
    assert updated["theme"] == "dark"
    assert updated["categories"]["job_digest"]["in_app"] is False
    assert updated["categories"]["job_digest"]["email"] == "off"


async def test_patch_preferences_cannot_disable_mandatory_category(db_session) -> None:
    student_user, _student = await make_student(db_session)

    updated = await preferences_service.patch_preferences(
        db_session,
        student_user.id,
        {"categories": {"security_alert": {"in_app": False, "email": "off"}}},
    )
    # Mandatory category ignores in_app/email overrides — stays locked+mandatory.
    assert updated["categories"]["security_alert"]["locked"] is True
    assert updated["categories"]["security_alert"]["email"] == "mandatory"


async def test_patch_preferences_invalid_locale_raises_validation_error(db_session) -> None:
    student_user, _student = await make_student(db_session)
    with pytest.raises(ValidationFailedError):
        await preferences_service.patch_preferences(db_session, student_user.id, {"locale": "fr"})


async def test_patch_preferences_invalid_category_email_setting_raises(db_session) -> None:
    student_user, _student = await make_student(db_session)
    with pytest.raises(ValidationFailedError):
        await preferences_service.patch_preferences(
            db_session,
            student_user.id,
            {"categories": {"message": {"email": "hourly"}}},
        )


async def test_patch_preferences_categories_not_a_dict_raises(db_session) -> None:
    student_user, _student = await make_student(db_session)
    with pytest.raises(ValidationFailedError):
        await preferences_service.patch_preferences(
            db_session, student_user.id, {"categories": ["not", "a", "dict"]}
        )


# --------------------------------------------------------------------------- #
# student_directory_facade.display_for                                       #
# --------------------------------------------------------------------------- #


async def test_display_for_returns_full_name_for_active_user(db_session) -> None:
    student_user, _student = await make_student(db_session)
    result = await display_for(db_session, [student_user.id])
    assert result[student_user.id] == student_user.full_name


async def test_display_for_masks_deactivated_user(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    student_user, _student = await make_student(db_session)
    await admin_users_service.suspend_user(
        db_session, principal=uni, ctx=CTX, user_id=student_user.id, reason="Deactivated"
    )

    result = await display_for(db_session, [student_user.id], locale="en")
    assert result[student_user.id] == DEPARTED_LABEL["en"]


async def test_display_for_empty_ids_returns_empty_dict(db_session) -> None:
    assert await display_for(db_session, []) == {}
