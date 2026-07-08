"""Interview simulator persistence + readiness (WS-6, Task K).

Durable, STUDENT-SCOPED store for interview practice attempts. Every read and
write is RBAC-gated (student persona), owner-checked (a session/turn belongs to
the acting student), and audited (metadata only — never the raw answer text).

The simulator's AI service (:mod:`interview_sim_service`) calls
:func:`record_prep_session` when it generates a question set and
:func:`record_answer_turn` after it evaluates an answer; the AI energy is metered
by the gateway, so persistence here does NOT re-charge. :func:`get_history`
returns the "my interview history / progress" read with a deterministic,
honest readiness signal (see :mod:`opportunities.domain.interview_readiness`).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.domain.interview_readiness import compute_readiness
from app.modules.opportunities.domain.interview_sim_models import (
    InterviewSimSession,
    InterviewSimTurn,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal

# Personas allowed to use the interview simulator (student self-preparation).
_STUDENT_PERSONAS = frozenset({"student", "alumni"})
# Cap the history list so the read stays a bounded, indexed scan.
_MAX_SESSIONS_IN_HISTORY = 50


def require_student(principal: Principal) -> None:
    """RBAC gate: interview simulator is student-only.

    - Unauthenticated (guest) -> ``AuthRequiredError`` (clean 401 gate).
    - Authenticated non-student (partner/university) -> ``PermissionDeniedError`` (403).
    - Superadmin is allowed (support/QA).
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if principal.persona not in _STUDENT_PERSONAS:
        raise PermissionDeniedError()


def _audit_ctx(principal: Principal, ctx: RequestContext | None) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip if ctx else None,
        user_agent=ctx.user_agent if ctx else None,
    )


async def record_prep_session(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    job_title: str | None,
    org_id: uuid.UUID | None,
    questions_count: int,
    ctx: RequestContext | None = None,
) -> uuid.UUID:
    """Persist a new practice attempt (question set generated) and return its id.

    Student-scoped: the row is owned by ``principal.user_id``. Audited with
    metadata only (no question text). Commits so the attempt is durable
    independent of the request path.
    """
    require_student(principal)
    assert principal.user_id is not None  # guaranteed by require_student

    row = InterviewSimSession(
        user_id=principal.user_id,
        job_id=job_id,
        job_title=(job_title or None),
        org_id=org_id,
        questions_count=max(0, int(questions_count)),
        answered_count=0,
        avg_score=None,
    )
    session.add(row)
    await session.flush()

    await write_audit(
        session,
        action="interview_sim.session_started",
        resource_type="interview_sim_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={
            "job_id": str(job_id),
            "questions_count": row.questions_count,
        },
    )
    await session.commit()
    return row.id


async def _resolve_owned_session(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID | None,
    job_id: uuid.UUID,
    org_id: uuid.UUID | None,
    job_title: str | None,
) -> InterviewSimSession:
    """Return the owned session for a turn, creating one if none is supplied.

    Owner-check: an explicit ``session_id`` that is missing raises 404; one owned
    by a different user raises 403. When no id is given we reuse the student's
    most-recent attempt for the job, or open a fresh attempt.
    """
    if session_id is not None:
        owned = (
            await session.execute(
                select(InterviewSimSession).where(
                    InterviewSimSession.id == session_id
                )
            )
        ).scalar_one_or_none()
        if owned is None:
            raise ResourceNotFoundError()
        if owned.user_id != principal.user_id and not principal.is_superadmin:
            raise PermissionDeniedError()
        return owned

    # No explicit session — reuse the latest attempt for this (student, job).
    latest = (
        await session.execute(
            select(InterviewSimSession)
            .where(
                InterviewSimSession.user_id == principal.user_id,
                InterviewSimSession.job_id == job_id,
            )
            .order_by(InterviewSimSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None:
        return latest

    created = InterviewSimSession(
        user_id=principal.user_id,
        job_id=job_id,
        job_title=(job_title or None),
        org_id=org_id,
        questions_count=0,
        answered_count=0,
        avg_score=None,
    )
    session.add(created)
    await session.flush()
    return created


async def record_answer_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    org_id: uuid.UUID | None,
    job_title: str | None,
    session_id: uuid.UUID | None,
    question_number: int,
    question_type: str,
    question: str,
    rubric: str | None,
    answer: str,
    feedback: dict,
    ctx: RequestContext | None = None,
) -> uuid.UUID:
    """Persist one answered question (Q + student answer + coaching feedback).

    Owner-checked + student-scoped. Recomputes the session aggregates
    (``answered_count`` / ``avg_score``) deterministically from the turns so a
    retry never drifts the running average. Audited (metadata only). Commits.
    """
    require_student(principal)
    assert principal.user_id is not None

    owned = await _resolve_owned_session(
        session,
        principal=principal,
        session_id=session_id,
        job_id=job_id,
        org_id=org_id,
        job_title=job_title,
    )

    score = feedback.get("score")
    turn = InterviewSimTurn(
        session_id=owned.id,
        user_id=principal.user_id,
        question_number=max(0, int(question_number)),
        question_type=(question_type or "behavioral")[:32],
        question=question[:2000],
        rubric=(rubric or None),
        answer=answer[:4000],
        score=int(score) if isinstance(score, int) else None,
        praise=(str(feedback.get("praise") or "") or None),
        improve=(str(feedback.get("improve") or "") or None),
        hint=(str(feedback.get("hint") or "") or None),
        is_fallback=bool(feedback.get("is_fallback", False)),
    )
    session.add(turn)
    await session.flush()

    # Deterministic aggregate recompute (idempotent under retries).
    agg = (
        await session.execute(
            select(
                func.count(InterviewSimTurn.id),
                func.avg(InterviewSimTurn.score),
            ).where(InterviewSimTurn.session_id == owned.id)
        )
    ).one()
    owned.answered_count = int(agg[0] or 0)
    owned.avg_score = round(float(agg[1]), 2) if agg[1] is not None else None

    await write_audit(
        session,
        action="interview_sim.answer_recorded",
        resource_type="interview_sim_turn",
        resource_id=turn.id,
        context=_audit_ctx(principal, ctx),
        after={
            "session_id": str(owned.id),
            "question_number": turn.question_number,
            "question_type": turn.question_type,
            "score": turn.score,
            "is_fallback": turn.is_fallback,
        },
    )
    await session.commit()
    return turn.id


def _session_public(row: InterviewSimSession) -> dict:
    return {
        "id": str(row.id),
        "job_id": str(row.job_id) if row.job_id else None,
        "job_title": row.job_title,
        "questions_count": row.questions_count,
        "answered_count": row.answered_count,
        "avg_score": float(row.avg_score) if row.avg_score is not None else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def get_history(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Return the student's own interview history + deterministic readiness.

    Student-scoped: only the caller's own attempts are visible. Never raises on
    low data — it returns an honest ``not_enough_data`` readiness status instead.
    """
    require_student(principal)

    sessions = list(
        (
            await session.execute(
                select(InterviewSimSession)
                .where(InterviewSimSession.user_id == principal.user_id)
                .order_by(InterviewSimSession.created_at.desc())
                .limit(_MAX_SESSIONS_IN_HISTORY)
            )
        )
        .scalars()
        .all()
    )

    scores_chrono = list(
        (
            await session.execute(
                select(InterviewSimTurn.score)
                .where(
                    InterviewSimTurn.user_id == principal.user_id,
                    InterviewSimTurn.score.is_not(None),
                )
                .order_by(InterviewSimTurn.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    attempts = len(sessions)
    readiness = compute_readiness(
        attempts=attempts,
        answer_scores_chrono=[int(s) for s in scores_chrono if s is not None],
    )

    return {
        "readiness": readiness.to_public(),
        "sessions": [_session_public(r) for r in sessions],
    }


async def get_session_detail(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> dict:
    """Return one attempt with its answered turns (owner-checked, student-scoped)."""
    require_student(principal)

    owned = (
        await session.execute(
            select(InterviewSimSession).where(InterviewSimSession.id == session_id)
        )
    ).scalar_one_or_none()
    if owned is None:
        raise ResourceNotFoundError()
    if owned.user_id != principal.user_id and not principal.is_superadmin:
        raise PermissionDeniedError()

    turns = list(
        (
            await session.execute(
                select(InterviewSimTurn)
                .where(InterviewSimTurn.session_id == owned.id)
                .order_by(InterviewSimTurn.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    return {
        "session": _session_public(owned),
        "turns": [
            {
                "id": str(t.id),
                "question_number": t.question_number,
                "question_type": t.question_type,
                "question": t.question,
                "rubric": t.rubric,
                "answer": t.answer,
                "score": t.score,
                "praise": t.praise,
                "improve": t.improve,
                "hint": t.hint,
                "is_fallback": t.is_fallback,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in turns
        ],
    }
