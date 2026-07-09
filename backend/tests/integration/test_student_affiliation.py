"""Student affiliation / verification persona tests (THEME A).

Covers the now-meaningful VinUni-vs-external-vs-alumni distinction:

- VinUni verify with an institution email -> affiliation ``vinuni_student`` + verified.
- VinUni verify with a NON-institution email -> 422 (service-layer enforcement).
- External verify -> affiliation ``external`` (any email allowed).
- Alumni verify -> persona ``alumni`` + affiliation ``alumni``.
- ``resolve_display`` provisional derivation (unverified) + verified override.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.onboarding.application import onboarding_service as svc
from app.modules.onboarding.domain.models import StudentVerification
from app.modules.student_profiles.application import affiliation_facade
from app.modules.users.application import user_service
from app.shared.exceptions import ValidationFailedError
from app.shared.models import AuditLog

from tests.auth_utils import register_verified

CTX = RequestContext(ip="203.0.113.9", user_agent="Mozilla/5.0 (Macintosh) Chrome/120")


async def _fetch_student_email_otp(session, user_id) -> str:
    rows = (
        await session.execute(
            select(NotificationOutbox)
            .where(NotificationOutbox.recipient_id == user_id)
            .order_by(NotificationOutbox.created_at.desc())
        )
    ).scalars().all()
    for row in rows:
        if row.template_key == "account.student_email_verification":
            return str(row.variables["otp_code"])
    raise AssertionError("no student email OTP enqueued")


async def _run_verify(session, user, *, student_email: str, student_kind: str):
    await svc.request_student_verify(
        session,
        user_id=user.id,
        university_name="VinUniversity",
        student_id_number="V2024001",
        student_email=student_email,
        student_kind=student_kind,
        ctx=CTX,
    )
    await session.commit()
    otp = await _fetch_student_email_otp(session, user.id)
    state = await svc.confirm_student_verify(
        session, user_id=user.id, otp_code=otp, id_card_file_path=None, ctx=CTX
    )
    await session.commit()
    return state


# --------------------------------------------------------------------------- #
# (a) VinUni institution email -> vinuni_student + verified                    #
# --------------------------------------------------------------------------- #


async def test_vinuni_verify_institution_email_sets_verified_affiliation(
    db_session,
) -> None:
    user = await register_verified(db_session, email="aff_vinuni@example.com")

    await _run_verify(
        db_session,
        user,
        student_email="s.v2024001@vinuni.edu.vn",
        student_kind="vinuni_student",
    )

    aff = await affiliation_facade.get_affiliation(db_session, user_id=user.id)
    assert aff["affiliation"] == "vinuni_student"
    assert aff["verified"] is True
    assert aff["verified_at"] is not None

    verif = (
        await db_session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user.id)
        )
    ).scalar_one()
    assert verif.student_kind == "vinuni_student"
    assert verif.status == "verified"

    # The verification write is audited with the resulting affiliation.
    audits = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.actor_id == user.id,
                AuditLog.action == "onboarding.student_email_verified",
            )
        )
    ).scalars().all()
    assert any(
        (a.after_snapshot or {}).get("affiliation") == "vinuni_student"
        for a in audits
    )


# --------------------------------------------------------------------------- #
# (b) VinUni + non-institution email -> 422, no affiliation written            #
# --------------------------------------------------------------------------- #


async def test_vinuni_verify_non_institution_email_rejected(db_session) -> None:
    user = await register_verified(db_session, email="aff_fake_vinuni@example.com")
    user_id = user.id

    # The validation raises before any write — no rollback needed.
    with pytest.raises(ValidationFailedError) as excinfo:
        await svc.request_student_verify(
            db_session,
            user_id=user_id,
            university_name="VinUniversity",
            student_id_number="V2024002",
            student_email="not.vinuni@gmail.com",
            student_kind="vinuni_student",
            ctx=CTX,
        )

    err = excinfo.value
    assert err.http_status == 422
    # User-safe message — no raw internal code leaked.
    assert "VinUni" in err.message
    assert "_" not in err.message  # no snake_case internal token

    # Nothing persisted: no verification row, affiliation stays general/unverified.
    verif = (
        await db_session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user_id)
        )
    ).scalar_one_or_none()
    assert verif is None
    aff = await affiliation_facade.get_affiliation(db_session, user_id=user_id)
    assert aff["affiliation"] == "general"
    assert aff["verified"] is False


# --------------------------------------------------------------------------- #
# (c) External verify -> external, any email allowed                           #
# --------------------------------------------------------------------------- #


async def test_external_verify_sets_external_affiliation(db_session) -> None:
    user = await register_verified(db_session, email="aff_external@example.com")

    await _run_verify(
        db_session,
        user,
        student_email="external.student@gmail.com",
        student_kind="external",
    )

    aff = await affiliation_facade.get_affiliation(db_session, user_id=user.id)
    assert aff["affiliation"] == "external"
    assert aff["verified"] is True

    # Persona is unchanged for an external student (stays 'student').
    identity = await user_service.primary_identity(db_session, user.id)
    assert identity is not None
    assert identity.persona == "student"


# --------------------------------------------------------------------------- #
# (d) Alumni verify -> persona alumni + affiliation alumni                     #
# --------------------------------------------------------------------------- #


async def test_alumni_verify_assigns_alumni_persona_and_affiliation(
    db_session,
) -> None:
    user = await register_verified(db_session, email="aff_alumni@example.com")

    await _run_verify(
        db_session,
        user,
        student_email="alum.2019@vinuni.edu.vn",
        student_kind="vinuni_alumni",
    )

    aff = await affiliation_facade.get_affiliation(db_session, user_id=user.id)
    assert aff["affiliation"] == "alumni"
    assert aff["verified"] is True

    identity = await user_service.primary_identity(db_session, user.id)
    assert identity is not None
    assert identity.persona == "alumni"


async def test_alumni_verify_requires_institution_email(db_session) -> None:
    user = await register_verified(db_session, email="aff_alumni_bad@example.com")

    with pytest.raises(ValidationFailedError):
        await svc.request_student_verify(
            db_session,
            user_id=user.id,
            university_name="VinUniversity",
            student_id_number="V2019009",
            student_email="alum@gmail.com",
            student_kind="vinuni_alumni",
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# (e) resolve_display provisional derivation                                   #
# --------------------------------------------------------------------------- #


async def test_resolve_display_provisional_from_institution_login_email(
    db_session,
) -> None:
    user = await register_verified(db_session, email="prov.student@vinuni.edu.vn")
    display = await affiliation_facade.resolve_display(
        db_session,
        user_id=user.id,
        login_email=user.email,
        seeker_type=None,
    )
    assert display == {"affiliation": "vinuni_student", "verified": False}


async def test_resolve_display_provisional_from_seeker_type(db_session) -> None:
    user = await register_verified(db_session, email="prov_ext@example.com")

    # student / fresh_graduate -> external (unverified)
    for seeker in ("student", "fresh_graduate"):
        display = await affiliation_facade.resolve_display(
            db_session,
            user_id=user.id,
            login_email="prov_ext@gmail.com",
            seeker_type=seeker,
        )
        assert display == {"affiliation": "external", "verified": False}

    # professional -> general
    display = await affiliation_facade.resolve_display(
        db_session,
        user_id=user.id,
        login_email="prov_ext@gmail.com",
        seeker_type="professional",
    )
    assert display == {"affiliation": "general", "verified": False}

    # unknown / None -> general
    display = await affiliation_facade.resolve_display(
        db_session,
        user_id=user.id,
        login_email="prov_ext@gmail.com",
        seeker_type=None,
    )
    assert display == {"affiliation": "general", "verified": False}


async def test_resolve_display_prefers_stored_verified_affiliation(db_session) -> None:
    user = await register_verified(db_session, email="prov_stored@example.com")
    await affiliation_facade.set_affiliation(
        db_session,
        user_id=user.id,
        affiliation="alumni",
        verified_at=datetime.now(tz=UTC),
    )
    await db_session.commit()

    # Even with a non-institution login email + professional seeker, the stored
    # verified affiliation wins.
    display = await affiliation_facade.resolve_display(
        db_session,
        user_id=user.id,
        login_email="prov_stored@gmail.com",
        seeker_type="professional",
    )
    assert display == {"affiliation": "alumni", "verified": True}


async def test_set_affiliation_rejects_unknown_value(db_session) -> None:
    user = await register_verified(db_session, email="aff_bad_value@example.com")
    with pytest.raises(ValueError):
        await affiliation_facade.set_affiliation(
            db_session, user_id=user.id, affiliation="not_a_real_affiliation"
        )
