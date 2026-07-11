"""RBAC, tenant/owner isolation, and failure-mode tests for mock interviews.

Covers the security + edge invariants: partner denied (student-only), guest 401,
cross-student 404 (non-enumerable), job-not-public 404, no-ready-CV validation,
unowned requested-CV 404, single-active concurrency conflict, and the daily
session cap.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.mock_interview.application import session_service
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    QuotaExceededError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import GUEST

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv
from tests.org_utils import make_org_with_admin


async def _create(db, student, job_id, **over):
    return await session_service.create_session(
        db, principal=student, ctx=CTX, job_id=job_id, cv_id=None, **over
    )


# --------------------------------------------------------------------------- #
# Persona RBAC                                                                  #
# --------------------------------------------------------------------------- #
async def test_partner_is_denied_student_only(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)
    job_id = await make_public_job(db_session)

    with pytest.raises(PermissionDeniedError) as exc:
        await _create(db_session, partner, job_id)
    assert exc.value.details.get("reason") == "student_only"


async def test_guest_requires_auth(db_session) -> None:
    job_id = await make_public_job(db_session)
    with pytest.raises(AuthRequiredError):
        await session_service.prep(db_session, principal=GUEST, job_id=job_id)
    with pytest.raises(AuthRequiredError):
        await _create(db_session, GUEST, job_id)


# --------------------------------------------------------------------------- #
# Owner isolation — cross-student is a NON-enumerable 404                       #
# --------------------------------------------------------------------------- #
async def test_second_student_cannot_read_others_session(db_session) -> None:
    owner, job_id = await _owner_with_session(db_session)
    _u2, other = await make_student(db_session, prefix="other")

    with pytest.raises(ResourceNotFoundError):
        await session_service.get_session(
            db_session, principal=other, session_id=owner["sid"]
        )


async def test_second_student_cannot_turn_others_session(db_session) -> None:
    owner, _job_id = await _owner_with_session(db_session)
    _u2, other = await make_student(db_session, prefix="other")

    with pytest.raises(ResourceNotFoundError):
        await session_service.assert_turnable(
            db_session, principal=other, session_id=owner["sid"]
        )
    with pytest.raises(ResourceNotFoundError):
        async for _ in session_service.stream_turn(
            db_session, principal=other, session_id=owner["sid"], answer="hi"
        ):
            pass


async def _owner_with_session(db):
    _u, owner = await make_student(db, prefix="owner")
    await make_strong_cv(db, owner)
    job_id = await make_public_job(db)
    created = await _create(db, owner, job_id)
    return {"principal": owner, "sid": uuid.UUID(created["session_id"])}, job_id


# --------------------------------------------------------------------------- #
# Job visibility gate                                                          #
# --------------------------------------------------------------------------- #
async def test_non_public_job_is_404(db_session) -> None:
    _u, student = await make_student(db_session)
    await make_strong_cv(db_session, student)
    draft_id = await make_public_job(db_session, publish=False)

    with pytest.raises(ResourceNotFoundError):
        await _create(db_session, student, draft_id)
    with pytest.raises(ResourceNotFoundError):
        await session_service.prep(db_session, principal=student, job_id=draft_id)
    # Unknown job id too.
    with pytest.raises(ResourceNotFoundError):
        await _create(db_session, student, uuid.uuid4())


# --------------------------------------------------------------------------- #
# CV gates                                                                     #
# --------------------------------------------------------------------------- #
async def test_no_ready_cv_is_validation_error(db_session) -> None:
    _u, student = await make_student(db_session)  # no CV finalized
    job_id = await make_public_job(db_session)

    with pytest.raises(ValidationFailedError) as exc:
        await _create(db_session, student, job_id)
    assert exc.value.details.get("reason") == "NO_READY_CV"


async def test_requested_cv_not_owned_is_404(db_session) -> None:
    _u, student = await make_student(db_session)
    await make_strong_cv(db_session, student)  # owns a ready CV, but not THIS one
    job_id = await make_public_job(db_session)

    with pytest.raises(ResourceNotFoundError):
        await session_service.create_session(
            db_session,
            principal=student,
            ctx=CTX,
            job_id=job_id,
            cv_id=uuid.uuid4(),  # not owned
        )


# --------------------------------------------------------------------------- #
# Concurrency — one live session at a time                                     #
# --------------------------------------------------------------------------- #
async def test_second_active_session_conflicts(db_session) -> None:
    _u, student = await make_student(db_session)
    await make_strong_cv(db_session, student)
    job_id = await make_public_job(db_session)

    await _create(db_session, student, job_id)  # first session is active
    with pytest.raises(ConflictError) as exc:
        await _create(db_session, student, job_id)
    assert exc.value.details.get("reason") == "ACTIVE_SESSION_EXISTS"


# --------------------------------------------------------------------------- #
# Session cap — daily                                                          #
# --------------------------------------------------------------------------- #
async def test_daily_session_cap_enforced(db_session) -> None:
    from app.modules.mock_interview.application import caps

    _u, student = await make_student(db_session)
    await make_strong_cv(db_session, student)
    job_id = await make_public_job(db_session)

    # Start DAILY_SESSION_CAP sessions, aborting each so concurrency stays clear.
    for _ in range(caps.DAILY_SESSION_CAP):
        created = await _create(db_session, student, job_id)
        await session_service.abort_session(
            db_session,
            principal=student,
            ctx=CTX,
            session_id=uuid.UUID(created["session_id"]),
        )

    with pytest.raises(QuotaExceededError) as exc:
        await _create(db_session, student, job_id)
    assert exc.value.details.get("reason") == "MOCK_INTERVIEW_SESSION_CAP"
