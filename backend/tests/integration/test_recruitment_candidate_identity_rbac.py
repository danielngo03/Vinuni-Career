"""Candidate-identity RBAC: reveal request, CV download, and revealed-identity
view are gated on the dedicated ``candidate_identity:*`` capabilities, additive to
the base partner-of-org ``applications:read`` (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``).

Before this hardening the sensitive-identity actions rode on the coarse
``applications:read`` grant, so any recruiter who could review applications could
also unmask anonymous candidates and pull their CVs. This file proves:

- ``request_reveal`` needs ``candidate_identity:request_reveal``;
- partner CV download needs ``candidate_identity:download_cv``;
- an anonymous applicant whose reveal was ACCEPTED is only unmasked for a member
  additionally holding ``candidate_identity:view_revealed_identity`` — without it
  the detail view leaks neither the name NOR the real ``user_id`` (still masked);
- the Admin wildcard (``*:*``) passes every one of them;
- tenant isolation still holds (the capability does not cross orgs).
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
from app.modules.recruitment.domain import lifecycle
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_REASON = "We would like to move this candidate to an on-site interview round."


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_reviewed(db, *, is_anonymous: bool):
    """Published job + a student who applied + partner review (candidate active)."""

    _pu, porg, admin = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)

    su, student = await make_student(db, prefix="candidate")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(db, principal=admin, application_id=app_id, ctx=CTX)
    return porg, admin, su, student, app_id


async def _accept_reveal(db, *, admin, student, app_id) -> None:
    await reveal_service.request_reveal(
        db, principal=admin, application_id=app_id, reason=_REASON, ctx=CTX
    )
    await reveal_service.respond_reveal(
        db,
        principal=student,
        application_id=app_id,
        decision=lifecycle.REVEAL_ACCEPTED,
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# request_reveal                                                              #
# --------------------------------------------------------------------------- #


async def test_request_reveal_denied_without_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    _u, _m, reviewer = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await reveal_service.request_reveal(
            db_session, principal=reviewer, application_id=app_id, reason=_REASON, ctx=CTX
        )


async def test_request_reveal_allowed_with_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    _u, _m, revealer = await add_member(
        db_session,
        org=org,
        permissions=[("applications", "read"), ("candidate_identity", "request_reveal")],
    )
    out = await reveal_service.request_reveal(
        db_session, principal=revealer, application_id=app_id, reason=_REASON, ctx=CTX
    )
    assert out["status"] == lifecycle.REVEAL_PENDING


# --------------------------------------------------------------------------- #
# CV download                                                                 #
# --------------------------------------------------------------------------- #


async def test_cv_download_denied_without_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session, is_anonymous=False)
    _u, _m, reviewer = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await apply_service.get_application_cv_download(
            db_session, principal=reviewer, application_id=app_id
        )


async def test_cv_download_allowed_with_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session, is_anonymous=False)
    _u, _m, downloader = await add_member(
        db_session,
        org=org,
        permissions=[("applications", "read"), ("candidate_identity", "download_cv")],
    )
    out = await apply_service.get_application_cv_download(
        db_session, principal=downloader, application_id=app_id
    )
    assert out.get("download_url")


# --------------------------------------------------------------------------- #
# Revealed-identity view                                                       #
# --------------------------------------------------------------------------- #


async def test_revealed_identity_masked_without_view_grant(db_session) -> None:
    org, admin, _su, student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    await _accept_reveal(db_session, admin=admin, student=student, app_id=app_id)

    _u, _m, reviewer = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    view = await apply_service.get_application(
        db_session, principal=reviewer, application_id=app_id
    )
    applicant = view["applicant"]
    # Even though the reveal was accepted, this member cannot unmask: no name, and
    # crucially no leak of the real ``user_id`` behind the anonymous handle.
    assert applicant["revealed"] is False
    assert "user_id" not in applicant
    assert view["cv_download_available"] is False


async def test_revealed_identity_visible_with_view_grant(db_session) -> None:
    org, admin, _su, student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    await _accept_reveal(db_session, admin=admin, student=student, app_id=app_id)

    _u, _m, viewer = await add_member(
        db_session,
        org=org,
        permissions=[("applications", "read"), ("candidate_identity", "view_revealed_identity")],
    )
    view = await apply_service.get_application(
        db_session, principal=viewer, application_id=app_id
    )
    applicant = view["applicant"]
    assert applicant["revealed"] is True
    assert applicant["user_id"] == str(student.user_id)


# --------------------------------------------------------------------------- #
# Admin wildcard + tenant isolation                                            #
# --------------------------------------------------------------------------- #


async def test_admin_wildcard_passes_every_candidate_identity_action(db_session) -> None:
    org, admin, _su, student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    reveal = await reveal_service.request_reveal(
        db_session, principal=admin, application_id=app_id, reason=_REASON, ctx=CTX
    )
    assert reveal["status"] == lifecycle.REVEAL_PENDING
    await reveal_service.respond_reveal(
        db_session,
        principal=student,
        application_id=app_id,
        decision=lifecycle.REVEAL_ACCEPTED,
        ctx=CTX,
    )
    view = await apply_service.get_application(
        db_session, principal=admin, application_id=app_id
    )
    assert view["applicant"]["revealed"] is True
    dl = await apply_service.get_application_cv_download(
        db_session, principal=admin, application_id=app_id
    )
    assert dl.get("download_url")


async def test_candidate_identity_grant_does_not_cross_org(db_session) -> None:
    org_a, _admin_a, _su, _student, app_id = await _setup_reviewed(db_session, is_anonymous=True)
    _bu, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    _u, _m, revealer_b = await add_member(
        db_session,
        org=org_b,
        permissions=[("applications", "read"), ("candidate_identity", "request_reveal")],
    )
    # Same capability, wrong org -> the cross-org application is invisible (404),
    # never a permission leak that would confirm the resource exists.
    with pytest.raises(ResourceNotFoundError):
        await reveal_service.request_reveal(
            db_session, principal=revealer_b, application_id=app_id, reason=_REASON, ctx=CTX
        )
