"""Platform-wide stale mock-interview session sweeper (P0-3).

The abandoned-``active`` recovery used to be LAZY (only the same user's next
``create_session`` expired their stale rows). These tests lock in the periodic
platform-wide sweeper: it expires abandoned ``active`` sessions past the hard cap
plus grace for EVERY user, never touches a session still within the cap, is
idempotent, and runs as a REGISTERED scheduler job (driven through the runner,
per the testing rule — never the sweep function alone for that assertion).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import runner
from app.modules.mock_interview.application import caps, session_service
from app.modules.mock_interview.application.stale_sweep_service import (
    STALE_GRACE_SECONDS,
    sweep_stale_active,
)
from app.modules.mock_interview.domain.models import STATUS_ACTIVE, STATUS_EXPIRED
from app.modules.mock_interview.infrastructure import repository as repo

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

_STALE_SECONDS = caps.MAX_SESSION_SECONDS + STALE_GRACE_SECONDS + 60


async def _active_session(db, *, prefix: str):
    _u, student = await make_student(db, prefix=prefix)
    cv_id = await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    created = await session_service.create_session(
        db, principal=student, ctx=CTX, job_id=job_id, cv_id=uuid.UUID(cv_id),
        modality="text", locale="vi",
    )
    return student, uuid.UUID(created["session_id"])


async def _backdate(db, sid, student, seconds: int) -> None:
    row = await repo.get_session(db, session_id=sid, user_id=student.user_id)
    assert row is not None
    row.started_at = datetime.now(tz=UTC) - timedelta(seconds=seconds)
    await db.commit()


async def test_sweep_expires_stale_active_and_leaves_fresh(db_session):
    stale_student, stale_sid = await _active_session(db_session, prefix="stale")
    _fresh_student, fresh_sid = await _active_session(db_session, prefix="fresh")
    # Only the stale one is backdated beyond cap + grace (platform-wide, not
    # scoped to the stale user's own create call).
    await _backdate(db_session, stale_sid, stale_student, _STALE_SECONDS)

    result = await sweep_stale_active(db_session)
    await db_session.commit()
    assert result == {"expired": 1}

    stale = await repo.get_session(db_session, session_id=stale_sid)
    fresh = await repo.get_session(db_session, session_id=fresh_sid)
    assert stale is not None and stale.status == STATUS_EXPIRED
    assert stale.ended_at is not None
    assert fresh is not None and fresh.status == STATUS_ACTIVE  # untouched


async def test_sweep_is_idempotent(db_session):
    student, sid = await _active_session(db_session, prefix="idem")
    await _backdate(db_session, sid, student, _STALE_SECONDS)

    first = await sweep_stale_active(db_session)
    await db_session.commit()
    assert first == {"expired": 1}

    # A re-tick finds no newly-stale rows — the already-expired row is skipped.
    second = await sweep_stale_active(db_session)
    await db_session.commit()
    assert second == {"expired": 0}


async def test_sweep_leaves_session_within_cap(db_session):
    student, sid = await _active_session(db_session, prefix="within")
    # Backdated but still inside the hard cap: legitimately live, never expired.
    await _backdate(db_session, sid, student, caps.MAX_SESSION_SECONDS - 10)

    result = await sweep_stale_active(db_session)
    await db_session.commit()
    assert result == {"expired": 0}

    row = await repo.get_session(db_session, session_id=sid)
    assert row is not None and row.status == STATUS_ACTIVE


async def test_sweep_runs_as_registered_scheduler_job(db_session):
    """Prove the sweeper is wired onto the periodic scheduler (registration)."""

    student, sid = await _active_session(db_session, prefix="sched")
    await _backdate(db_session, sid, student, _STALE_SECONDS)

    # Drive through the runner (its own session + commit), never the sweep fn.
    result = await runner.run_job("mock_interview.stale_session_sweep")
    assert result.get("expired") == 1

    # Verify in a FRESH session so we read the committed state, not a cached row.
    async with get_sessionmaker()() as verify:
        row = await repo.get_session(verify, session_id=sid)
        assert row is not None and row.status == STATUS_EXPIRED
