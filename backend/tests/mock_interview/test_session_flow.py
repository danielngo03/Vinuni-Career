"""Integration tests for the mock-interview happy path (offline provider).

DB-backed, SQLite, no network: every LLM call degrades to the deterministic static
fallbacks. Exercises the full lifecycle — create (opening turn persisted) -> stream
a turn (candidate + interviewer turns persisted, ``done`` event) -> end (fallback
coaching report, no score) -> read / list / share / delete — plus the presenter
no-leak invariant.
"""

from __future__ import annotations

import json
import uuid

from app.modules.mock_interview.api import presenters
from app.modules.mock_interview.application import session_service
from app.modules.mock_interview.domain.models import (
    SPEAKER_CANDIDATE,
    SPEAKER_INTERVIEWER,
    STATUS_ABORTED,
    STATUS_COMPLETED,
)
from app.modules.mock_interview.infrastructure import repository as repo

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

_SCORE_KEYS = ("score", "rating", "grade", "percentage", "pass_fail")
_INTERNAL_FIELDS = (
    "provider_ref",
    "model_ref",
    "grounding_json",
    "grounding_version",
    "text_redacted",
    "flagged",
)


async def _seed_student_job(db):
    _u, student = await make_student(db)
    await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    return student, job_id


async def _create(db, student, job_id, **over):
    return await session_service.create_session(
        db, principal=student, ctx=CTX, job_id=job_id, cv_id=None, **over
    )


# --------------------------------------------------------------------------- #
# create -> opening turn                                                        #
# --------------------------------------------------------------------------- #
async def test_create_session_persists_opening_interviewer_turn(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)

    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])

    assert created["opening"]["seq"] == 1
    assert created["opening"]["speaker"] == SPEAKER_INTERVIEWER
    assert created["opening"]["text"]  # static fallback opening (offline)

    turns = await repo.load_turns(db_session, session_id=sid)
    assert len(turns) == 1
    assert turns[0].seq == 1
    assert turns[0].speaker == SPEAKER_INTERVIEWER
    assert turns[0].text_redacted is not None  # pseudonymized copy stored
    # created row is active with the frozen grounding.
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None
    assert row.status == "active"
    assert row.grounding_json is not None
    assert row.question_count == 1


# --------------------------------------------------------------------------- #
# stream a turn -> candidate + interviewer persisted, done event               #
# --------------------------------------------------------------------------- #
async def test_stream_turn_persists_both_turns_and_yields_done(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])

    events = [
        e
        async for e in session_service.stream_turn(
            db_session,
            principal=student,
            session_id=sid,
            answer="I built REST APIs with FastAPI and shipped them to production.",
        )
    ]

    assert events, "stream produced no events"
    done = events[-1]
    assert done["type"] == "done"
    assert done["seq"] == 3  # opening=1, candidate=2, interviewer=3
    assert done["text"]
    assert done["question_count"] == 2
    assert isinstance(done["ended"], bool)
    # at least one token chunk before done (static fallback chunk)
    assert any(e["type"] == "token" for e in events)

    turns = await repo.load_turns(db_session, session_id=sid)
    assert [t.speaker for t in turns] == [
        SPEAKER_INTERVIEWER,
        SPEAKER_CANDIDATE,
        SPEAKER_INTERVIEWER,
    ]
    assert [t.seq for t in turns] == [1, 2, 3]
    assert "FastAPI" in turns[1].text


# --------------------------------------------------------------------------- #
# end -> fallback coaching report, no score, completed                         #
# --------------------------------------------------------------------------- #
async def test_end_session_produces_fallback_report_without_score(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])
    async for _ in session_service.stream_turn(
        db_session, principal=student, session_id=sid, answer="My relevant project."
    ):
        pass

    detail = await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid, duration_seconds=123
    )

    assert detail["status"] == STATUS_COMPLETED
    assert detail["duration_seconds"] == 123
    report = detail["report"]
    assert report is not None
    assert report["is_fallback"] is True
    for key in _SCORE_KEYS:
        assert key not in report
    assert report["overall_observations"]
    # question_count recomputed from interviewer turns (opening + one reply).
    assert detail["question_count"] == 2

    # Ending an already-completed session is idempotent.
    again = await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )
    assert again["status"] == STATUS_COMPLETED


# --------------------------------------------------------------------------- #
# presenter no-leak invariant                                                  #
# --------------------------------------------------------------------------- #
async def test_presenters_never_leak_internal_fields(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])
    await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )

    detail = await session_service.get_session(
        db_session, principal=student, session_id=sid
    )
    summaries = await session_service.list_sessions(db_session, principal=student)

    for payload in (detail, summaries):
        blob = json.dumps(payload, ensure_ascii=False)
        for field in _INTERNAL_FIELDS:
            assert field not in blob, f"presenter leaked internal field: {field}"

    # The detail exposes only student-safe keys.
    assert set(detail.keys()) == {
        "id",
        "job_id",
        "job_title",
        "cv_id",
        "locale",
        "modality",
        "status",
        "started_at",
        "ended_at",
        "duration_seconds",
        "question_count",
        "has_report",
        "created_at",
        "share_opt_in",
        "transcript",
        "report",
    }
    # Direct presenter call on the raw row is also clean (no flagged/model_ref).
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None
    turns = await repo.load_turns(db_session, session_id=sid)
    raw = json.dumps(presenters.session_detail(row, turns), ensure_ascii=False)
    for field in _INTERNAL_FIELDS:
        assert field not in raw


# --------------------------------------------------------------------------- #
# realtime transcript flush                                                    #
# --------------------------------------------------------------------------- #
async def test_record_turns_appends_realtime_transcript(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id, modality="realtime")
    sid = uuid.UUID(created["session_id"])

    out = await session_service.record_turns(
        db_session,
        principal=student,
        session_id=sid,
        turns_in=[
            {"speaker": SPEAKER_CANDIDATE, "text": "My answer to the first question."},
            {"speaker": SPEAKER_INTERVIEWER, "text": "Good, tell me about a challenge."},
            {"speaker": SPEAKER_CANDIDATE, "text": "   "},  # blank -> skipped
        ],
    )
    assert out["added"] == 2
    turns = await repo.load_turns(db_session, session_id=sid)
    # opening(1) + 2 appended = 3, contiguous seq.
    assert [t.seq for t in turns] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# abort / delete / share                                                       #
# --------------------------------------------------------------------------- #
async def test_abort_session_marks_aborted(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])

    detail = await session_service.abort_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )
    assert detail["status"] == STATUS_ABORTED
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None and row.status == STATUS_ABORTED
    assert row.ended_at is not None


async def test_delete_session_removes_row_and_turns(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])
    # sanity: opening turn exists
    assert await repo.load_turns(db_session, session_id=sid)

    await session_service.delete_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )

    assert await repo.get_session(db_session, session_id=sid) is None
    assert await repo.load_turns(db_session, session_id=sid) == []  # cascade


async def test_set_share_opt_in_flips_flag(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])

    on = await session_service.set_share_opt_in(
        db_session, principal=student, ctx=CTX, session_id=sid, opt_in=True
    )
    assert on["share_opt_in"] is True
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None and row.share_opt_in is True

    off = await session_service.set_share_opt_in(
        db_session, principal=student, ctx=CTX, session_id=sid, opt_in=False
    )
    assert off["share_opt_in"] is False


async def test_list_and_get_are_owner_scoped(db_session) -> None:
    student, job_id = await _seed_student_job(db_session)
    created = await _create(db_session, student, job_id)
    sid = uuid.UUID(created["session_id"])

    listed = await session_service.list_sessions(db_session, principal=student)
    assert [s["id"] for s in listed] == [str(sid)]

    got = await session_service.get_session(
        db_session, principal=student, session_id=sid
    )
    assert got["id"] == str(sid)
