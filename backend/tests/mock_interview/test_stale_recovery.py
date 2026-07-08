"""Abandoned-session auto-recovery on create."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.mock_interview.application import caps, session_service
from app.modules.mock_interview.domain.models import STATUS_EXPIRED
from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.exceptions import ConflictError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv


async def _create(db_session, student, job_id, cv_id):
    return await session_service.create_session(
        db_session,
        principal=student,
        ctx=CTX,
        job_id=job_id,
        cv_id=uuid.UUID(cv_id),
        modality="text",
        locale="vi",
    )


async def test_stale_active_session_is_auto_recovered(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)

    first = await _create(db_session, student, job_id, cv_id)
    sid1 = uuid.UUID(first["session_id"])

    # Simulate an abandoned tab: backdate the active session beyond cap + grace.
    row = await repo.get_session(db_session, session_id=sid1, user_id=student.user_id)
    assert row is not None
    row.started_at = datetime.now(tz=UTC) - timedelta(
        seconds=caps.MAX_SESSION_SECONDS + 600
    )
    await db_session.commit()

    # A new session now succeeds instead of raising 409.
    second = await _create(db_session, student, job_id, cv_id)
    assert second["session_id"] != first["session_id"]

    stale = await repo.get_session(db_session, session_id=sid1, user_id=student.user_id)
    assert stale is not None
    assert stale.status == STATUS_EXPIRED


async def test_recent_active_session_still_blocks(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)

    await _create(db_session, student, job_id, cv_id)
    with pytest.raises(ConflictError):
        await _create(db_session, student, job_id, cv_id)
