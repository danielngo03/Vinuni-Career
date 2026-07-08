"""Student progress read model + extended university stats."""

from __future__ import annotations

import uuid

import pytest
from app.modules.mock_interview.application import (
    governance_service,
    progress_service,
    session_service,
)
from app.shared.exceptions import PermissionDeniedError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv
from tests.org_utils import make_org_with_admin


async def _complete(db_session, student, job_id: uuid.UUID, cv_id: str) -> None:
    created = await session_service.create_session(
        db_session,
        principal=student,
        ctx=CTX,
        job_id=job_id,
        cv_id=uuid.UUID(cv_id),
        modality="text",
        locale="vi",
    )
    sid = uuid.UUID(created["session_id"])
    async for _ in session_service.stream_turn(
        db_session,
        principal=student,
        session_id=sid,
        answer="I built REST APIs with Python and FastAPI.",
    ):
        pass
    await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )


async def test_progress_is_student_scoped_and_themed(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)
    await _complete(db_session, student, job_id, cv_id)

    prog = await progress_service.build_progress(db_session, principal=student)
    assert prog["completed"] >= 1
    for key in ("recurring_gaps", "top_strengths", "by_focus", "recent"):
        assert key in prog
    # focus was auto-inferred as technical for a Python/FastAPI role
    assert "technical" in prog["by_focus"]

    _pu, _po, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await progress_service.build_progress(db_session, principal=partner)


async def test_university_stats_has_trend_topjobs_focus(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)
    await _complete(db_session, student, job_id, cv_id)

    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    stats = await governance_service.stats(db_session, principal=uni, days=30)
    assert "trend" in stats
    assert "by_focus" in stats
    assert isinstance(stats["top_jobs"], list)
    assert stats["top_jobs"] and stats["top_jobs"][0]["count"] >= 1
