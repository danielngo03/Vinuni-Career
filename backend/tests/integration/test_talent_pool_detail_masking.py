"""Talent-pool PROFILE-DETAIL candidate-identity protection.

The passive talent-pool LIST already masks an external partner's view of a passive
candidate behind an opaque ``UV-xxxx`` handle. This proves the DETAIL read
(``GET /students/{id}/profile`` → ``profile_service.get_profile_for_viewer``)
applies the SAME mask, closing the leak where an unrevealed external partner could
read the candidate's real name on the detail path:

- an external partner WITHOUT a granted reveal sees the masked handle (identity +
  contact + avatar withheld), and the handle matches the LIST card's handle;
- a VinUni community viewer (another student) keeps the identified view;
- once the partner holds an ACCEPTED identity reveal for the candidate (recruitment
  handshake) AND may view revealed identities, the detail shows the REAL name.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    reveal_service,
)
from app.modules.student_profiles.application import profile_service, talent_pool_service

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_REVEAL_REASON = "Chúng tôi muốn xác minh thông tin ứng viên để mời phỏng vấn."


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _public_open_student(db, *, prefix: str):
    su, student = await make_student(db, prefix=prefix)
    await profile_service.update_my_profile(
        db,
        principal=student,
        payload={
            "profile_visibility": "public",
            "is_open_to_work": True,
            "location_city": "Hanoi",
        },
        ctx=CTX,
    )
    return su, student


async def _profile_id(db, *, student) -> uuid.UUID:
    prof = await profile_service.get_my_profile(db, principal=student)
    return uuid.UUID(prof["id"])


async def _detail(db, *, principal, profile_id):
    return await profile_service.get_profile_for_viewer(
        db, principal=principal, profile_id=profile_id
    )


# --------------------------------------------------------------------------- #
# External partner without a reveal -> masked detail (the closed leak)         #
# --------------------------------------------------------------------------- #


async def test_external_partner_detail_is_masked(db_session) -> None:
    su, student = await _public_open_student(db_session, prefix="detail_mask")
    pid = await _profile_id(db_session, student=student)
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    detail = await _detail(db_session, principal=partner, profile_id=pid)

    assert detail["identity_masked"] is True
    assert detail["display_name"].startswith("UV-")
    assert detail["display_name"] == detail["anonymous_id"]
    assert detail["avatar_url"] is None
    # Real identity + contact + the internal user_id never leak on the masked path.
    assert "email" not in detail
    assert "phone" not in detail
    assert "user_id" not in detail
    assert (su.full_name or "ZZZ") not in str(detail)
    # Coarse screening signal remains so the recruiter can still screen on fit.
    assert detail["is_open_to_work"] is True
    assert detail["location_city"] == "Hanoi"


async def test_detail_handle_matches_list_handle(db_session) -> None:
    """The masked detail handle is IDENTICAL to the talent-pool LIST card handle."""

    _su, student = await _public_open_student(db_session, prefix="detail_stable")
    pid = await _profile_id(db_session, student=student)
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co 2")

    detail = await _detail(db_session, principal=partner, profile_id=pid)
    listing = await talent_pool_service.search_talent_pool(
        db_session, principal=partner, keyword=None, cursor=None, limit=20
    )
    card = next(c for c in listing["items"] if c["profile_id"] == str(pid))
    assert card["identity_masked"] is True
    assert card["display_name"] == detail["display_name"]


# --------------------------------------------------------------------------- #
# VinUni community viewer keeps the identified detail                          #
# --------------------------------------------------------------------------- #


async def test_vinuni_student_detail_is_identified(db_session) -> None:
    su, owner = await _public_open_student(db_session, prefix="detail_owner")
    pid = await _profile_id(db_session, student=owner)
    _vsu, viewer = await make_student(db_session, prefix="detail_viewer")

    detail = await _detail(db_session, principal=viewer, profile_id=pid)
    assert detail["identity_masked"] is False
    assert not detail["display_name"].startswith("UV-")
    assert detail["display_name"] == su.full_name
    assert "user_id" in detail


# --------------------------------------------------------------------------- #
# Revealed partner -> real identity on the detail path                         #
# --------------------------------------------------------------------------- #


async def test_revealed_partner_sees_real_identity_on_detail(db_session) -> None:
    su, student = await _public_open_student(db_session, prefix="detail_reveal")
    pid = await _profile_id(db_session, student=student)
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Reveal Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)

    # The student applies ANONYMOUSLY, the partner reviews, requests a reveal, and
    # the student accepts — the recruitment handshake that authorizes identity.
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await reveal_service.request_reveal(
        db_session, principal=partner, application_id=app_id, reason=_REVEAL_REASON, ctx=CTX
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id, decision="accepted", ctx=CTX
    )

    detail = await _detail(db_session, principal=partner, profile_id=pid)
    assert detail["identity_masked"] is False
    assert detail["display_name"] == su.full_name
    assert not detail["display_name"].startswith("UV-")


async def test_partner_without_reveal_capability_stays_masked(db_session) -> None:
    """A different partner org (no reveal for THIS candidate) stays masked."""

    su, student = await _public_open_student(db_session, prefix="detail_other")
    pid = await _profile_id(db_session, student=student)
    _pu, _porg, partner_a = await make_org_with_admin(db_session, display_name="Co A")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner_a, uni_principal=uni)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db_session, principal=partner_a, application_id=app_id, ctx=CTX
    )
    await reveal_service.request_reveal(
        db_session, principal=partner_a, application_id=app_id, reason=_REVEAL_REASON, ctx=CTX
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id, decision="accepted", ctx=CTX
    )

    # A SECOND, unrelated partner org has no reveal for this candidate -> masked.
    _pu2, _porg2, partner_b = await make_org_with_admin(db_session, display_name="Co B")
    detail = await _detail(db_session, principal=partner_b, profile_id=pid)
    assert detail["identity_masked"] is True
    assert detail["display_name"].startswith("UV-")
    assert (su.full_name or "ZZZ") not in str(detail)
