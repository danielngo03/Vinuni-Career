"""``jobs.view_count`` lifetime counter wiring (design spec §6).

The counter was dead (always 0). It must bump on a genuine PUBLIC job-detail view
and stay coarse (owner / moderator views never count) — and surface in the partner
job read.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import job_service
from app.modules.opportunities.domain.models import Job
from app.modules.recruitment.application import access
from sqlalchemy import select

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _view_count(db, job_id: uuid.UUID) -> int:
    return (
        await db.execute(select(Job.view_count).where(Job.id == job_id))
    ).scalar_one()


async def _setup(db):
    _pu, _porg, admin = await make_org_with_admin(db, display_name="Views Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)
    return admin, job_id


async def test_public_view_increments_view_count(db_session) -> None:
    admin, job_id = await _setup(db_session)
    assert await _view_count(db_session, job_id) == 0

    _su, student = await make_student(db_session)
    detail = await job_service.get_job(db_session, principal=student, job_id=job_id)
    assert await _view_count(db_session, job_id) == 1
    # Surfaced in the public detail projection.
    assert detail["view_count"] == 1

    await job_service.get_job(db_session, principal=student, job_id=job_id)
    assert await _view_count(db_session, job_id) == 2


async def test_owner_and_moderator_views_do_not_count(db_session) -> None:
    admin, job_id = await _setup(db_session)

    # Owner viewing their own job is not a candidate engagement signal.
    await job_service.get_job(db_session, principal=admin, job_id=job_id)
    assert await _view_count(db_session, job_id) == 0
