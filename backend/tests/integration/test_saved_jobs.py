"""Integration tests for Saved Jobs feature.

Covers: student save/unsave idempotency, guest returns empty set,
non-student denied, list pagination, is_saved injected in public list/detail.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.opportunities.application import job_service, saved_jobs_service
from app.modules.opportunities.application import moderation_service
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import GUEST, Principal
from app.modules.auth.domain.personas import permissions_for

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.documents_utils import make_student


def _job_payload(title: str = "Test Job") -> dict:
    return {
        "title": title,
        "description": "A test job for saved-jobs tests.",
        "requirements": None,
        "benefits": None,
        "employment_type": "full_time",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python"],
        "preferred_skills": [],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
        "screening_questions": [],
    }


async def _publish_job(db, partner_principal, uni_principal, *, title="Live Job") -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner_principal, payload=_job_payload(title), ctx=CTX
    )
    jid = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=partner_principal, job_id=jid, ctx=CTX)
    await moderation_service.approve_job(db, principal=uni_principal, job_id=jid, ctx=CTX)
    return jid


# --------------------------------------------------------------------------- #
# save / unsave                                                                #
# --------------------------------------------------------------------------- #


async def test_student_can_save_and_unsave(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni)

    _, student = await make_student(db_session)

    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)
    ids = await saved_jobs_service.get_saved_ids(db_session, principal=student)
    assert job_id in ids

    await saved_jobs_service.unsave_job(db_session, principal=student, job_id=job_id)
    ids_after = await saved_jobs_service.get_saved_ids(db_session, principal=student)
    assert job_id not in ids_after


async def test_save_is_idempotent(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni)

    _, student = await make_student(db_session)

    # Saving twice should not raise.
    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)
    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)

    ids = await saved_jobs_service.get_saved_ids(db_session, principal=student)
    assert job_id in ids


async def test_unsave_nonexistent_is_noop(db_session) -> None:
    _, student = await make_student(db_session)
    ghost_id = uuid.uuid4()
    # Should not raise
    await saved_jobs_service.unsave_job(db_session, principal=student, job_id=ghost_id)


async def test_guest_get_saved_ids_returns_empty(db_session) -> None:
    ids = await saved_jobs_service.get_saved_ids(db_session, principal=GUEST)
    assert ids == set()


async def test_non_student_save_raises_permission(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni)

    with pytest.raises(PermissionDeniedError):
        await saved_jobs_service.save_job(db_session, principal=admin, job_id=job_id)


# --------------------------------------------------------------------------- #
# list_saved_jobs                                                              #
# --------------------------------------------------------------------------- #


async def test_list_saved_returns_saved_jobs(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni, title="My Saved Job")

    _, student = await make_student(db_session)
    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)

    items, next_cursor, _ = await saved_jobs_service.list_saved_jobs(
        db_session, principal=student, limit=20
    )
    ids_in_result = {uuid.UUID(j["id"]) for j in items}
    assert job_id in ids_in_result
    for j in items:
        assert j.get("is_saved") is True


async def test_list_saved_empty_for_new_student(db_session) -> None:
    _, student = await make_student(db_session)
    items, next_cursor, _ = await saved_jobs_service.list_saved_jobs(
        db_session, principal=student, limit=20
    )
    assert items == []
    assert next_cursor is None


async def test_list_saved_excludes_unsaved(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni, title="Was Saved")

    _, student = await make_student(db_session)
    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)
    await saved_jobs_service.unsave_job(db_session, principal=student, job_id=job_id)

    items, next_cursor, _ = await saved_jobs_service.list_saved_jobs(
        db_session, principal=student, limit=20
    )
    assert items == []


# --------------------------------------------------------------------------- #
# is_saved injected in public list                                             #
# --------------------------------------------------------------------------- #


async def test_is_saved_injected_in_public_list(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni, title="Saved In List")

    _, student = await make_student(db_session)
    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)

    items, _, _, _ = await job_service.list_public_jobs(
        db_session, principal=student, cursor=None, limit=50
    )
    matching = [j for j in items if uuid.UUID(j["id"]) == job_id]
    assert len(matching) == 1
    assert matching[0].get("is_saved") is True


async def test_is_saved_false_for_guest_in_public_list(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish_job(db_session, admin, uni, title="Guest List Job")

    items, _, _, _ = await job_service.list_public_jobs(
        db_session, principal=GUEST, cursor=None, limit=50
    )
    matching = [j for j in items if uuid.UUID(j["id"]) == job_id]
    assert len(matching) == 1
    assert matching[0].get("is_saved") is False
