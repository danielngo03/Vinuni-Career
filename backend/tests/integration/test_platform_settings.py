"""Integration tests for platform appearance settings (self-hosted font catalogue).

Covers: default settings on first read (empty-state / lazy row creation),
superadmin update happy path, permission-denied for non-admin personas and
guests, and invalid font_key validation failure.

FIXED (previously reported as bugs, now resolved): ``settings_service._to_response``
used to read a nonexistent ``row.font_key`` attribute (``PlatformSettings`` only
has ``google_font_url`` / ``google_font_family``); it now derives the active
``font_key`` by reverse-looking-up the stored ``google_font_family`` against
``FONT_CATALOGUE``, and ``update_settings`` persists the family name for the
selected key. Also, ``_check_admin`` used to gate on
``principal.persona == "university_admin"``, a persona string that does not
exist anywhere else in the codebase (real university staff bootstrap via
``make_org_with_admin`` assigns ``university_staff`` — see
``app/modules/auth/domain/personas.py``). That check is now superadmin-only
(the incorrect/dead persona comparison was removed rather than widened, since
docs do not explicitly grant university-staff org-admins this capability —
see ``settings_service._check_admin`` docstring for the rationale).
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.platform_settings.application import settings_service
from app.shared.exceptions import PermissionDeniedError, ValidationFailedError
from app.shared.permissions import GUEST, Principal

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


def _superadmin_principal() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="staff", is_superadmin=True)


# --------------------------------------------------------------------------- #
# get_settings — default / empty state (BLOCKED by AttributeError bug above)   #
# --------------------------------------------------------------------------- #


async def test_get_settings_returns_default_font_when_unset(db_session) -> None:
    data = await settings_service.get_settings(db_session)
    assert data["font_key"] == settings_service.DEFAULT_FONT_KEY
    assert data["font_family"] == "Plus Jakarta Sans"
    assert len(data["catalogue"]) == len(settings_service.FONT_CATALOGUE)


async def test_get_settings_is_idempotent_across_calls(db_session) -> None:
    first = await settings_service.get_settings(db_session)
    second = await settings_service.get_settings(db_session)
    assert first == second


# --------------------------------------------------------------------------- #
# update_settings — happy path (only reachable with is_superadmin=True)        #
# --------------------------------------------------------------------------- #


async def test_superadmin_can_update_font(db_session) -> None:
    superadmin = _superadmin_principal()

    updated = await settings_service.update_settings(
        db_session, principal=superadmin, font_key="inter", actor_id=superadmin.user_id
    )
    assert updated["font_key"] == "inter"
    assert updated["font_family"] == "Inter"


async def test_update_settings_with_none_resets_to_default(db_session) -> None:
    superadmin = _superadmin_principal()

    await settings_service.update_settings(
        db_session, principal=superadmin, font_key="manrope", actor_id=superadmin.user_id
    )
    reset = await settings_service.update_settings(
        db_session, principal=superadmin, font_key=None, actor_id=superadmin.user_id
    )
    assert reset["font_key"] == settings_service.DEFAULT_FONT_KEY


# --------------------------------------------------------------------------- #
# permission denied                                                            #
# --------------------------------------------------------------------------- #


async def test_partner_admin_cannot_update_font(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session, org_type="partner")
    with pytest.raises(PermissionDeniedError):
        await settings_service.update_settings(
            db_session, principal=partner_admin, font_key="inter", actor_id=partner_admin.user_id
        )


async def test_student_cannot_update_font(db_session) -> None:
    _, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await settings_service.update_settings(
            db_session, principal=student, font_key="inter", actor_id=student.user_id
        )


async def test_guest_cannot_update_font(db_session) -> None:
    with pytest.raises(PermissionDeniedError):
        await settings_service.update_settings(
            db_session, principal=GUEST, font_key="inter", actor_id=None
        )


async def test_real_university_staff_principal_is_denied_due_to_persona_mismatch_bug(
    db_session,
) -> None:
    """Regression-documents the ``_check_admin`` persona bug (see module docstring):
    a real, bootstrapped university-org admin (persona ``university_staff``) is
    denied because the service checks for a persona string (``university_admin``)
    that is never actually assigned anywhere in the system.
    """
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(PermissionDeniedError):
        await settings_service.update_settings(
            db_session, principal=uni, font_key="inter", actor_id=uni.user_id
        )


# --------------------------------------------------------------------------- #
# invalid input                                                                #
# --------------------------------------------------------------------------- #


async def test_invalid_font_key_raises_validation_error(db_session) -> None:
    superadmin = _superadmin_principal()
    with pytest.raises(ValidationFailedError):
        await settings_service.update_settings(
            db_session, principal=superadmin, font_key="comic_sans", actor_id=superadmin.user_id
        )
