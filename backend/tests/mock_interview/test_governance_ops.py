"""University governance + AI-ops debug surfaces (RBAC + privacy boundary)."""

from __future__ import annotations

import uuid

import pytest
from app.modules.mock_interview.application import (
    governance_service,
    ops_service,
    session_service,
)
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv
from tests.org_utils import make_org_with_admin


async def _completed_session(db_session, student, job_id: uuid.UUID, cv_id: str) -> uuid.UUID:
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
        answer="I built REST APIs with FastAPI.",
    ):
        pass
    await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )
    return sid


def _superadmin(*, grant: bool = False) -> Principal:
    perms = frozenset({"ai_settings:view_provider_identity"}) if grant else frozenset()
    return Principal(
        user_id=uuid.uuid4(),
        persona="university",
        is_superadmin=True,
        permissions=perms,
    )


async def test_governance_stats_is_university_only_and_aggregate(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)
    await _completed_session(db_session, student, job_id, cv_id)

    # A partner Admin (wildcard, but org_type=partner) is denied.
    _pu, _porg, partner_admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await governance_service.stats(db_session, principal=partner_admin, days=30)

    # A university Admin sees aggregate-only data.
    _uu, _uorg, uni_admin = await make_org_with_admin(db_session, org_type="university")
    data = await governance_service.stats(db_session, principal=uni_admin, days=30)
    assert data["total"] >= 1
    assert data["completed"] >= 1
    assert "completion_rate" in data
    # No PII / no transcript content ever leaves governance.
    assert "transcript" not in data
    assert "user_id" not in data
    assert isinstance(data["distinct_students"], int)


async def test_governance_config_masked(db_session):
    _uu, _uorg, uni_admin = await make_org_with_admin(db_session, org_type="university")
    cfg = await governance_service.config(db_session, principal=uni_admin)
    assert cfg["daily_session_cap"] >= 1
    assert "realtime_voice_enabled" in cfg
    # never leaks provider/model identity
    assert not any(
        k in cfg for k in ("provider", "model", "provider_ref", "model_ref")
    )


async def test_ops_flagged_requires_superadmin(db_session):
    _u, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await ops_service.list_flagged(db_session, principal=student)
    res = await ops_service.list_flagged(db_session, principal=_superadmin())
    assert isinstance(res, list)


async def test_ops_transcript_redacted_by_default_full_with_grant_and_optin(db_session):
    _u, student = await make_student(db_session)
    job_id = await make_public_job(db_session)
    cv_id = await make_strong_cv(db_session, student)
    sid = await _completed_session(db_session, student, job_id, cv_id)

    # A non-superadmin (even the owning student) cannot use the ops surface.
    with pytest.raises(PermissionDeniedError):
        await ops_service.view_transcript(
            db_session, principal=student, ctx=CTX, session_id=sid
        )

    # Superadmin WITHOUT the identity grant -> pseudonymized (redacted).
    red = await ops_service.view_transcript(
        db_session, principal=_superadmin(grant=False), ctx=CTX, session_id=sid
    )
    assert red["mode"] == "redacted"
    assert len(red["transcript"]) >= 2

    # Grant WITHOUT student opt-in still stays redacted.
    still_red = await ops_service.view_transcript(
        db_session, principal=_superadmin(grant=True), ctx=CTX, session_id=sid
    )
    assert still_red["mode"] == "redacted"

    # Student opts in -> grant + opt-in unlocks the full transcript.
    await session_service.set_share_opt_in(
        db_session, principal=student, ctx=CTX, session_id=sid, opt_in=True
    )
    full = await ops_service.view_transcript(
        db_session, principal=_superadmin(grant=True), ctx=CTX, session_id=sid
    )
    assert full["mode"] == "full"
    assert len(full["transcript"]) >= 2
