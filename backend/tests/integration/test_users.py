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
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError, ValidationFailedError

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


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
        db_session, principal=uni, user_id=student_user.id
    )
    assert suspended["is_active"] is False

    restored = await admin_users_service.unsuspend_user(
        db_session, principal=uni, user_id=student_user.id
    )
    assert restored["is_active"] is True


async def test_admin_cannot_suspend_self(db_session) -> None:
    admin_user, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(db_session, principal=uni, user_id=admin_user.id)


async def test_suspend_nonexistent_user_raises_not_found(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(ResourceNotFoundError):
        await admin_users_service.suspend_user(db_session, principal=uni, user_id=uuid.uuid4())


async def test_partner_admin_cannot_suspend_user(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session, org_type="partner")
    student_user, _student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.suspend_user(
            db_session, principal=partner_admin, user_id=student_user.id
        )


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
    await admin_users_service.suspend_user(db_session, principal=uni, user_id=student_user.id)

    result = await display_for(db_session, [student_user.id], locale="en")
    assert result[student_user.id] == DEPARTED_LABEL["en"]


async def test_display_for_empty_ids_returns_empty_dict(db_session) -> None:
    assert await display_for(db_session, []) == {}
