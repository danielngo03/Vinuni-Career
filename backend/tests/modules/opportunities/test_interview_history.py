"""Interview simulator persistence + history + RBAC (WS-6, Task K).

Covers:
- The full AI path persists a practice attempt and returns its ``session_id``.
- Answer feedback persists a turn and updates session aggregates.
- ``get_history`` is student-scoped and returns a deterministic readiness signal.
- Honest low-data state (``not_enough_data``) before the minimum answers.
- ``ready_signal`` once enough answers exist, with an improving-trend read.
- Ownership: another student cannot read someone else's attempt detail.
- RBAC gate: guests get 401, partners get 403.
- Every write is audited.

Run:
    cd backend && uv run pytest tests/modules/opportunities/test_interview_history.py -q
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.ai.gateway import task_runner as tr
from app.ai.gateway.base import AICompletion
from app.modules.opportunities.application import (
    interview_history_service,
    interview_sim_service,
)
from app.modules.opportunities.domain.interview_readiness import (
    STATUS_NOT_ENOUGH,
    STATUS_READY,
    TREND_IMPROVING,
)
from app.modules.opportunities.domain.interview_sim_models import (
    InterviewSimSession,
    InterviewSimTurn,
)
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.models import AuditLog
from app.shared.permissions import GUEST, Principal
from sqlalchemy import func, select
from tests.documents_utils import make_student
from tests.integration.test_cv_job_fit import _create_job

_PREP_JSON = {
    "questions": [
        {"type": "behavioral", "question": "Tell me about a project.",
         "hint": "STAR", "rubric": "structured"},
    ],
    "prep_tips": "Prepare STAR stories.",
}
_FEEDBACK_JSON = {
    "score": 4,
    "praise": "Clear structure.",
    "improve": "Add a measurable outcome.",
    "hint": "Quantify impact.",
}


def _patch_json(monkeypatch, payload: dict) -> None:
    async def _complete(self, messages, *, temperature=0.2, max_tokens=1024):
        return AICompletion(text=json.dumps(payload), model_alias="x")

    monkeypatch.setattr(tr.AiTaskRunner, "complete", _complete)


async def _feedback(feedback: dict) -> dict:
    base = dict(_FEEDBACK_JSON)
    base.update(feedback)
    base.setdefault("is_fallback", False)
    return base


# --------------------------------------------------------------------------- #
# Full AI path persists a session + turn                                       #
# --------------------------------------------------------------------------- #


async def test_generate_persists_session_and_returns_id(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)
    _patch_json(monkeypatch, _PREP_JSON)

    out = await interview_sim_service.generate_interview_prep(
        db_session, principal=student, job_id=job_id
    )

    assert out["is_fallback"] is False
    assert "session_id" in out
    sid = uuid.UUID(out["session_id"])

    row = (
        await db_session.execute(
            select(InterviewSimSession).where(InterviewSimSession.id == sid)
        )
    ).scalar_one()
    assert row.user_id == student.user_id
    assert row.job_id == job_id
    assert row.questions_count == 1
    assert row.answered_count == 0

    # Audited.
    n_audit = (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "interview_sim.session_started"
            )
        )
    ).scalar_one()
    assert n_audit == 1


async def test_answer_feedback_persists_turn_and_updates_aggregates(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    _patch_json(monkeypatch, _PREP_JSON)
    prep = await interview_sim_service.generate_interview_prep(
        db_session, principal=student, job_id=job_id
    )
    sid = uuid.UUID(prep["session_id"])

    _patch_json(monkeypatch, _FEEDBACK_JSON)
    out = await interview_sim_service.evaluate_answer(
        db_session, principal=student, job_id=job_id,
        question="Tell me about a project.", question_type="behavioral",
        rubric="structured", answer="I built a REST API.",
        session_id=sid, question_number=1,
    )
    assert out["is_fallback"] is False

    turns = list(
        (
            await db_session.execute(
                select(InterviewSimTurn).where(InterviewSimTurn.session_id == sid)
            )
        ).scalars().all()
    )
    assert len(turns) == 1
    assert turns[0].user_id == student.user_id
    assert turns[0].score == 4
    # the student's own answer is stored (never surfaced to a partner)
    assert turns[0].answer == "I built a REST API."

    sess = (
        await db_session.execute(
            select(InterviewSimSession).where(InterviewSimSession.id == sid)
        )
    ).scalar_one()
    assert sess.answered_count == 1
    assert float(sess.avg_score) == 4.0

    n_audit = (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "interview_sim.answer_recorded"
            )
        )
    ).scalar_one()
    assert n_audit == 1


# --------------------------------------------------------------------------- #
# History read + readiness                                                      #
# --------------------------------------------------------------------------- #


async def test_history_low_data_is_honest(db_session) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    sid = await interview_history_service.record_prep_session(
        db_session, principal=student, job_id=job_id, job_title="Backend Intern",
        org_id=None, questions_count=3,
    )
    await interview_history_service.record_answer_turn(
        db_session, principal=student, job_id=job_id, org_id=None,
        job_title="Backend Intern", session_id=sid, question_number=1,
        question_type="behavioral", question="Q1", rubric="r",
        answer="a", feedback=await _feedback({"score": 4}),
    )

    hist = await interview_history_service.get_history(db_session, principal=student)
    assert hist["readiness"]["status"] == STATUS_NOT_ENOUGH
    assert hist["readiness"]["readiness_pct"] is None
    assert hist["readiness"]["answers_evaluated"] == 1
    assert hist["readiness"]["answers_needed"] == 2
    assert len(hist["sessions"]) == 1
    assert hist["sessions"][0]["job_title"] == "Backend Intern"


async def test_history_ready_signal_and_trend(db_session) -> None:
    _u, student = await make_student(db_session)
    job_id = await _create_job(db_session)

    sid = await interview_history_service.record_prep_session(
        db_session, principal=student, job_id=job_id, job_title="J",
        org_id=None, questions_count=8,
    )
    # Insert turns with explicit, spaced timestamps so the chronological trend is
    # deterministic: weak earlier answers, strong recent answers -> improving.
    base = datetime(2026, 1, 1, tzinfo=UTC)
    scores = [2, 2, 2, 2, 5, 5, 5, 5]
    for i, sc in enumerate(scores):
        db_session.add(
            InterviewSimTurn(
                session_id=sid, user_id=student.user_id, question_number=i + 1,
                question_type="behavioral", question=f"Q{i}", rubric="r",
                answer="a", score=sc, praise="p", improve="im", hint="h",
                is_fallback=False, created_at=base + timedelta(minutes=i),
            )
        )
    await db_session.commit()

    hist = await interview_history_service.get_history(db_session, principal=student)
    r = hist["readiness"]
    assert r["status"] == STATUS_READY
    assert r["answers_evaluated"] == 8
    assert r["trend"] == TREND_IMPROVING
    assert isinstance(r["readiness_pct"], int)


# --------------------------------------------------------------------------- #
# Ownership + RBAC                                                              #
# --------------------------------------------------------------------------- #


async def test_history_is_student_scoped(db_session) -> None:
    """Student B never sees student A's attempts."""
    _ua, student_a = await make_student(db_session, prefix="stud-a")
    _ub, student_b = await make_student(db_session, prefix="stud-b")
    job_id = await _create_job(db_session)

    await interview_history_service.record_prep_session(
        db_session, principal=student_a, job_id=job_id, job_title="J",
        org_id=None, questions_count=3,
    )

    hist_a = await interview_history_service.get_history(db_session, principal=student_a)
    hist_b = await interview_history_service.get_history(db_session, principal=student_b)
    assert len(hist_a["sessions"]) == 1
    assert len(hist_b["sessions"]) == 0


async def test_session_detail_owner_checked(db_session) -> None:
    _ua, student_a = await make_student(db_session, prefix="own-a")
    _ub, student_b = await make_student(db_session, prefix="own-b")
    job_id = await _create_job(db_session)

    sid = await interview_history_service.record_prep_session(
        db_session, principal=student_a, job_id=job_id, job_title="J",
        org_id=None, questions_count=3,
    )

    # Owner can read.
    detail = await interview_history_service.get_session_detail(
        db_session, principal=student_a, session_id=sid
    )
    assert detail["session"]["id"] == str(sid)

    # A different student is denied (403), not shown the data.
    with pytest.raises(PermissionDeniedError):
        await interview_history_service.get_session_detail(
            db_session, principal=student_b, session_id=sid
        )

    # Missing attempt -> 404.
    with pytest.raises(ResourceNotFoundError):
        await interview_history_service.get_session_detail(
            db_session, principal=student_a, session_id=uuid.uuid4()
        )


async def test_guest_is_gated_401(db_session) -> None:
    with pytest.raises(AuthRequiredError):
        await interview_history_service.get_history(db_session, principal=GUEST)


async def test_partner_is_gated_403(db_session) -> None:
    partner = Principal(
        user_id=uuid.uuid4(), persona="partner_member", org_id=uuid.uuid4(),
        is_superadmin=False, permissions=frozenset(),
    )
    with pytest.raises(PermissionDeniedError):
        await interview_history_service.get_history(db_session, principal=partner)


async def test_answer_turn_rejects_foreign_session(db_session) -> None:
    """Recording an answer against another student's session is denied."""
    _ua, student_a = await make_student(db_session, prefix="turn-a")
    _ub, student_b = await make_student(db_session, prefix="turn-b")
    job_id = await _create_job(db_session)

    sid = await interview_history_service.record_prep_session(
        db_session, principal=student_a, job_id=job_id, job_title="J",
        org_id=None, questions_count=3,
    )
    with pytest.raises(PermissionDeniedError):
        await interview_history_service.record_answer_turn(
            db_session, principal=student_b, job_id=job_id, org_id=None,
            job_title="J", session_id=sid, question_number=1,
            question_type="behavioral", question="Q1", rubric="r",
            answer="a", feedback=await _feedback({"score": 3}),
        )
