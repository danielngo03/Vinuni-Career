"""Enterprise multi-person pipeline: candidate ownership (assignee) + team filters.

Proves the durable candidate-owner workflow an enterprise recruiting team needs:
- assign / unassign a candidate to an ACTIVE member of the same org;
- assignment is gated on ``applications:update`` (not just read) and is
  tenant-isolated (cross-org application -> 404; cross-org assignee -> 422);
- the assignee block surfaces in the partner projection;
- the job applications list filters by ``status`` and by ``assignee`` ("me" /
  "unassigned" / a membership id).
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    assignment_service,
    decision_service,
)
from app.modules.recruitment.application.errors import InvalidApplicationFieldError
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


async def _setup(db):
    """Published job + a student applied + partner review (candidate under_review)."""

    _pu, porg, admin = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)
    _su, student = await make_student(db, prefix="applicant")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(db, principal=admin, application_id=app_id, ctx=CTX)
    return porg, admin, job_id, app_id


async def _add_recruiter(db, org, *, can_update=True):
    perms = [("applications", "read")]
    if can_update:
        perms.append(("applications", "update"))
    return await add_member(db, org=org, permissions=perms)


async def _assign(db, *, principal, app_id, membership_id):
    return await assignment_service.assign_application(
        db,
        principal=principal,
        application_id=app_id,
        assignee_membership_id=membership_id,
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Assign / unassign                                                            #
# --------------------------------------------------------------------------- #


async def test_assign_sets_owner_and_surfaces_in_view(db_session) -> None:
    porg, admin, _job, app_id = await _setup(db_session)
    _u, membership, _principal = await _add_recruiter(db_session, porg)

    out = await _assign(db_session, principal=admin, app_id=app_id, membership_id=membership.id)
    assert out["assignee"]["membership_id"] == str(membership.id)
    assert out["assignee"]["display_name"]  # resolved staff name, non-empty

    view = await apply_service.get_application(db_session, principal=admin, application_id=app_id)
    assert view["assignee"]["membership_id"] == str(membership.id)


async def test_unassign_clears_owner(db_session) -> None:
    porg, admin, _job, app_id = await _setup(db_session)
    _u, membership, _p = await _add_recruiter(db_session, porg)
    await _assign(db_session, principal=admin, app_id=app_id, membership_id=membership.id)
    out = await _assign(db_session, principal=admin, app_id=app_id, membership_id=None)
    assert out["assignee"] is None


async def test_assign_requires_update_capability(db_session) -> None:
    porg, _admin, _job, app_id = await _setup(db_session)
    _u, membership, reader = await _add_recruiter(db_session, porg, can_update=False)
    with pytest.raises(PermissionDeniedError):
        await _assign(db_session, principal=reader, app_id=app_id, membership_id=membership.id)


async def test_assign_rejects_cross_org_member(db_session) -> None:
    porg, admin, _job, app_id = await _setup(db_session)
    _bu, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    _u, membership_b, _rb = await _add_recruiter(db_session, org_b)
    with pytest.raises(InvalidApplicationFieldError):
        await _assign(db_session, principal=admin, app_id=app_id, membership_id=membership_b.id)


async def test_assign_cross_org_application_is_404(db_session) -> None:
    _porg, _admin, _job, app_id = await _setup(db_session)
    _bu, org_b, admin_b = await make_org_with_admin(db_session, display_name="Org B2")
    _u, membership_b, _rb = await _add_recruiter(db_session, org_b)
    with pytest.raises(ResourceNotFoundError):
        await _assign(db_session, principal=admin_b, app_id=app_id, membership_id=membership_b.id)


# --------------------------------------------------------------------------- #
# List filters                                                                 #
# --------------------------------------------------------------------------- #


async def test_list_filters_by_status(db_session) -> None:
    _porg, admin, job_id, app_id = await _setup(db_session)  # under_review
    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id, status="under_review"
    )
    assert any(i["id"] == str(app_id) for i in items)
    none, _c2, _l2 = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id, status="hired"
    )
    assert all(i["id"] != str(app_id) for i in none)


async def test_list_filters_by_assignee_me_and_unassigned(db_session) -> None:
    porg, admin, job_id, app_id = await _setup(db_session)
    _u, membership, recruiter = await _add_recruiter(db_session, porg)

    # Initially unassigned.
    un, _c, _l = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id, assignee="unassigned"
    )
    assert any(i["id"] == str(app_id) for i in un)

    await _assign(db_session, principal=admin, app_id=app_id, membership_id=membership.id)

    # The assigned recruiter sees it under "me"; it drops out of "unassigned".
    mine, _c2, _l2 = await apply_service.list_job_applications(
        db_session, principal=recruiter, job_id=job_id, assignee="me"
    )
    assert any(i["id"] == str(app_id) for i in mine)
    un2, _c3, _l3 = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id, assignee="unassigned"
    )
    assert all(i["id"] != str(app_id) for i in un2)


# --------------------------------------------------------------------------- #
# List projection surfaces the current pipeline stage                          #
# --------------------------------------------------------------------------- #


async def test_list_projection_includes_current_stage(db_session) -> None:
    """A reviewed candidate carries its current pipeline stage on the LIST item."""

    _porg, admin, job_id, app_id = await _setup(db_session)  # reviewed -> stage 1
    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id
    )
    item = next(i for i in items if i["id"] == str(app_id))
    assert item["stage"] is not None
    assert item["stage"]["stage_id"]
    assert item["stage"]["stage_name"]


async def test_list_projection_stage_none_for_submitted(db_session) -> None:
    """A still-submitted (pre-pipeline) application carries ``stage = None``."""

    _porg, admin, job_id, _reviewed_id = await _setup(db_session)
    _su, student = await make_student(db_session, prefix="unreviewed")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id
    )
    item = next(i for i in items if i["id"] == app["id"])
    assert item["stage"] is None
