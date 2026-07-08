"""Data access for mock-interview sessions/turns (ORM only, no business rules)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mock_interview.domain.models import (
    STATUS_ABORTED,
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    STATUS_EXPIRED,
    MockInterviewSession,
    MockInterviewTurn,
)


async def get_session(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> MockInterviewSession | None:
    """Load one session. When ``user_id`` is given, hard-scope to that owner."""

    stmt = select(MockInterviewSession).where(MockInterviewSession.id == session_id)
    if user_id is not None:
        stmt = stmt.where(MockInterviewSession.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def load_turns(
    session: AsyncSession, *, session_id: uuid.UUID
) -> list[MockInterviewTurn]:
    stmt = (
        select(MockInterviewTurn)
        .where(MockInterviewTurn.session_id == session_id)
        .order_by(MockInterviewTurn.seq)
    )
    return list((await session.execute(stmt)).scalars().all())


async def expire_stale_active(
    session: AsyncSession, *, user_id: uuid.UUID, cutoff: datetime, now: datetime
) -> int:
    """Mark this user's abandoned ``active`` sessions (started before ``cutoff``)
    as ``expired`` so a stuck tab never blocks a new session forever."""

    stmt = (
        update(MockInterviewSession)
        .where(
            MockInterviewSession.user_id == user_id,
            MockInterviewSession.status == STATUS_ACTIVE,
            MockInterviewSession.started_at < cutoff,
        )
        .values(status=STATUS_EXPIRED, ended_at=now)
    )
    result = await session.execute(stmt)
    # ``rowcount`` lives on CursorResult; the async execute return type is the
    # narrower ``Result``, so read it defensively for the type checker.
    return int(getattr(result, "rowcount", 0) or 0)


async def count_active(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(MockInterviewSession)
        .where(
            MockInterviewSession.user_id == user_id,
            MockInterviewSession.status == STATUS_ACTIVE,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def count_sessions_since(
    session: AsyncSession, *, user_id: uuid.UUID, since: datetime
) -> int:
    stmt = (
        select(func.count())
        .select_from(MockInterviewSession)
        .where(
            MockInterviewSession.user_id == user_id,
            MockInterviewSession.started_at >= since,
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def list_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int = 20
) -> list[MockInterviewSession]:
    stmt = (
        select(MockInterviewSession)
        .where(MockInterviewSession.user_id == user_id)
        .order_by(MockInterviewSession.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


# --- governance / ops read models (aggregate + flagged) -------------------- #
async def aggregate_stats(
    session: AsyncSession, *, since: datetime
) -> dict[str, Any]:
    """Privacy-safe aggregate over sessions since ``since`` (single table)."""

    s = MockInterviewSession
    # ``case``-based sums keep this portable across SQLite (test) and Postgres.
    stmt = select(
        func.count().label("total"),
        func.coalesce(
            func.sum(case((s.status == STATUS_COMPLETED, 1), else_=0)), 0
        ).label("completed"),
        func.coalesce(
            func.sum(case((s.status == STATUS_ABORTED, 1), else_=0)), 0
        ).label("aborted"),
        func.coalesce(
            func.sum(case((s.status == STATUS_ACTIVE, 1), else_=0)), 0
        ).label("active"),
        func.coalesce(
            func.sum(case((s.flagged.is_(True), 1), else_=0)), 0
        ).label("flagged"),
        func.coalesce(func.avg(s.question_count), 0).label("avg_questions"),
        func.coalesce(func.avg(s.duration_seconds), 0).label("avg_duration"),
        func.count(func.distinct(s.user_id)).label("students"),
    ).where(s.created_at >= since)
    row = (await session.execute(stmt)).one()
    mod_stmt = (
        select(s.modality, func.count())
        .where(s.created_at >= since)
        .group_by(s.modality)
    )
    by_modality = {m: int(c) for m, c in (await session.execute(mod_stmt)).all()}
    return {
        "total": int(row.total),
        "completed": int(row.completed),
        "aborted": int(row.aborted),
        "active": int(row.active),
        "flagged": int(row.flagged),
        "avg_questions": round(float(row.avg_questions), 1),
        "avg_duration_seconds": round(float(row.avg_duration), 1),
        "distinct_students": int(row.students),
        "by_modality": by_modality,
    }


async def list_flagged(
    session: AsyncSession, *, limit: int = 50
) -> list[MockInterviewSession]:
    stmt = (
        select(MockInterviewSession)
        .where(MockInterviewSession.flagged.is_(True))
        .order_by(MockInterviewSession.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
