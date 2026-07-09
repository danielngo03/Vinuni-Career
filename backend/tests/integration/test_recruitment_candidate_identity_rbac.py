"""Candidate CV-access RBAC (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``).

An application ALWAYS exposes the applicant's real identity to a partner who holds
the base ``applications:read`` grant (owner decision 2026-07-10 — the anonymous
apply + identity-reveal handshake was removed). What stays gated is CV ACCESS: the
watermarked CV download is additive on ``candidate_identity:download_cv`` and every
use is audited. This file proves:

- the partner detail always carries the applicant's real ``user_id`` / name / email
  (never masked, no reveal dance);
- partner CV download needs ``candidate_identity:download_cv``;
- the Admin wildcard (``*:*``) passes CV download;
- tenant isolation holds (the capability does not cross orgs — a cross-org
  application is a ``404``, never a permission leak).
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, apply_service, decision_service
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_reviewed(db):
    """Published job + a student who applied + partner review (candidate active)."""

    _pu, porg, admin = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)

    su, student = await make_student(db, prefix="candidate")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(db, principal=admin, application_id=app_id, ctx=CTX)
    return porg, admin, su, student, app_id


# --------------------------------------------------------------------------- #
# Identity is always present (never masked)                                    #
# --------------------------------------------------------------------------- #


async def test_partner_detail_always_exposes_real_identity(db_session) -> None:
    org, _admin, _su, student, app_id = await _setup_reviewed(db_session)
    _u, _m, reviewer = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    view = await apply_service.get_application(
        db_session, principal=reviewer, application_id=app_id
    )
    applicant = view["applicant"]
    assert applicant["user_id"] == str(student.user_id)
    assert applicant["full_name"]
    assert applicant["email"]


# --------------------------------------------------------------------------- #
# CV download                                                                 #
# --------------------------------------------------------------------------- #


async def test_cv_download_denied_without_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session)
    _u, _m, reviewer = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await apply_service.get_application_cv_download(
            db_session, principal=reviewer, application_id=app_id
        )


async def test_cv_download_allowed_with_candidate_identity_grant(db_session) -> None:
    org, _admin, _su, _student, app_id = await _setup_reviewed(db_session)
    _u, _m, downloader = await add_member(
        db_session,
        org=org,
        permissions=[("applications", "read"), ("candidate_identity", "download_cv")],
    )
    out = await apply_service.get_application_cv_download(
        db_session, principal=downloader, application_id=app_id
    )
    assert out.get("download_url")
    assert out.get("has_watermark") is True


# --------------------------------------------------------------------------- #
# Admin wildcard + tenant isolation                                            #
# --------------------------------------------------------------------------- #


async def test_admin_wildcard_passes_cv_download(db_session) -> None:
    _org, admin, _su, _student, app_id = await _setup_reviewed(db_session)
    dl = await apply_service.get_application_cv_download(
        db_session, principal=admin, application_id=app_id
    )
    assert dl.get("download_url")


async def test_candidate_identity_grant_does_not_cross_org(db_session) -> None:
    _org_a, _admin_a, _su, _student, app_id = await _setup_reviewed(db_session)
    _bu, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    _u, _m, downloader_b = await add_member(
        db_session,
        org=org_b,
        permissions=[("applications", "read"), ("candidate_identity", "download_cv")],
    )
    # Same capability, wrong org -> the cross-org application is invisible (404),
    # never a permission leak that would confirm the resource exists.
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application_cv_download(
            db_session, principal=downloader_b, application_id=app_id
        )
