"""Write + read path for the ``job_competition_daily`` projection (WS-5, Task B).

Recompute-and-UPSERT projection of the caliber-of-real-applicants competition
inputs. Two producers keep it fresh:

- :func:`refresh_job_competition` — called on each apply event (best-effort,
  isolated in a savepoint via :func:`refresh_job_competition_safe`) so a new
  applicant is reflected immediately.
- :func:`sweep_refresh` — the nightly scheduled sweep that recomputes every job
  with at least one active application (self-healing / catches withdrawals /
  rejections / deadline closes that shrink the active set).

One consumer, the hot path:

- :func:`stats_for_read` — the student-facing competition read hits the
  projection row (ONE indexed lookup). On a projection MISS it falls back to a
  single bounded live compute for that one job (never a heavy dashboard join) —
  the row is populated by the next apply event / sweep.

Cross-module read contract: the applicant pool aggregation reads the
``applications`` (recruitment) and ``application_cv_snapshots`` (documents) tables
via a raw ``text()`` query — the same no-cross-module-ORM-import pattern
``competition_service`` already uses. The projection ORM model itself is
opportunities-owned.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Uuid, bindparam, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import competition_scoring as scoring
from app.modules.opportunities.domain.competition_read_models import JobCompetitionDaily
from app.modules.opportunities.domain.models import Job

logger = logging.getLogger(__name__)

# Kept in sync with recruitment.domain.lifecycle.ACTIVE_STATUSES (copied to avoid
# a cross-module implementation import — same contract as competition_service).
_ACTIVE_SQL = "('submitted', 'under_review')"

_UPSERT_COLUMNS = (
    "org_id",
    "seats",
    "active_applications",
    "dist_developing",
    "dist_mixed",
    "dist_strong",
    "dist_top",
    "refreshed_at",
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_uuid(value: object) -> uuid.UUID:
    """Normalise a driver-returned id (native UUID on PG, hex str on SQLite)."""

    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def _compute_pool(
    session: AsyncSession, *, job_id: uuid.UUID
) -> tuple[int, list[int]]:
    """Return ``(active_applications, scored_fits)`` for a job from REAL applicants.

    LEFT JOINs each active application to its immutable snapshot ``fit_score``:
    every active application counts toward ``active_applications``; only those
    with a non-NULL ``fit_score`` contribute to ``scored_fits`` (the caliber
    pool). NULL-fit applicants (uploaded-document applies / pre-migration
    history) are UNKNOWN quality — excluded from ``scored_fits``, never fit 0.

    The active-per-(job, applicant) unique index guarantees one row per
    applicant, so no de-duplication is needed.
    """

    result = await session.execute(
        text(
            "SELECT s.fit_score AS fit_score"
            " FROM applications a"
            " LEFT JOIN application_cv_snapshots s ON a.snapshot_id = s.id"
            " WHERE a.job_id = :job_id"
            f" AND a.status IN {_ACTIVE_SQL}"
            " AND a.deleted_at IS NULL"
        ).bindparams(bindparam("job_id", type_=Uuid(as_uuid=True))),
        {"job_id": job_id},
    )
    rows = result.all()
    active = len(rows)
    scored = [int(r[0]) for r in rows if r[0] is not None]
    return active, scored


def _dialect_insert(session: AsyncSession):
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    return pg_insert if dialect == "postgresql" else sqlite_insert


async def _upsert(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    stats: scoring.CompetitionStats,
    now: datetime,
) -> None:
    insert = _dialect_insert(session)
    values = {
        "job_id": job_id,
        "org_id": org_id,
        "seats": stats.seats,
        "active_applications": stats.active_applications,
        "dist_developing": stats.dist_developing,
        "dist_mixed": stats.dist_mixed,
        "dist_strong": stats.dist_strong,
        "dist_top": stats.dist_top,
        "refreshed_at": now,
    }
    stmt = insert(JobCompetitionDaily).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["job_id"],
        set_={col: values[col] for col in _UPSERT_COLUMNS},
    )
    await session.execute(stmt)


async def refresh_job_competition(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    seats: int,
    now: datetime | None = None,
) -> scoring.CompetitionStats:
    """Recompute + upsert the projection row for one job. Returns the fresh stats."""

    stamp = now or _now()
    active, scored = await _compute_pool(session, job_id=job_id)
    stats = scoring.stats_from_pool(
        seats=seats, active_applications=active, scored_fits=scored
    )
    await _upsert(session, job_id=job_id, org_id=org_id, stats=stats, now=stamp)
    return stats


async def refresh_job_competition_safe(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    seats: int,
    now: datetime | None = None,
) -> None:
    """Best-effort refresh, isolated in a savepoint.

    Called from the apply flow: a projection-write failure must never poison or
    abort the applicant's own transaction (mirrors ``partner_job_metrics``).
    """

    try:
        async with session.begin_nested():
            await refresh_job_competition(
                session, job_id=job_id, org_id=org_id, seats=seats, now=now
            )
    except Exception:  # noqa: BLE001 — projection refresh is best-effort telemetry
        logger.warning(
            "job_competition.refresh_failed", extra={"job_id": str(job_id)}
        )


async def _get_row(
    session: AsyncSession, *, job_id: uuid.UUID
) -> JobCompetitionDaily | None:
    return (
        await session.execute(
            select(JobCompetitionDaily).where(JobCompetitionDaily.job_id == job_id)
        )
    ).scalar_one_or_none()


async def stats_for_read(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    org_id: uuid.UUID,
    seats: int,
) -> scoring.CompetitionStats:
    """Hot-path competition inputs for one job.

    Prefers the projection row (ONE indexed lookup, no multi-domain join). The
    stored applicant distribution is used verbatim; ``seats`` is overridden with
    the LIVE headcount so a seat edit is reflected immediately. On a projection
    MISS falls back to a single bounded live compute for THIS job (the row is
    materialized later by the next apply event / nightly sweep) so the read is
    never empty and never fabricates.
    """

    row = await _get_row(session, job_id=job_id)
    if row is not None:
        return scoring.CompetitionStats(
            seats=max(seats, 0),
            active_applications=row.active_applications,
            dist_developing=row.dist_developing,
            dist_mixed=row.dist_mixed,
            dist_strong=row.dist_strong,
            dist_top=row.dist_top,
        )
    active, scored = await _compute_pool(session, job_id=job_id)
    return scoring.stats_from_pool(
        seats=seats, active_applications=active, scored_fits=scored
    )


async def _active_job_ids(session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(
        text(
            "SELECT DISTINCT a.job_id AS job_id"
            " FROM applications a"
            f" WHERE a.status IN {_ACTIVE_SQL}"
            " AND a.deleted_at IS NULL"
        )
    )
    return [_as_uuid(r[0]) for r in result.all() if r[0] is not None]


async def sweep_refresh(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Nightly self-healing refresh of every job with an active application.

    Idempotent (a re-tick recomputes to the same values). Each job is refreshed
    in its own savepoint so one bad job never aborts the whole sweep. Returns a
    ``{"refreshed": n, "errors": m}`` summary for the scheduler log.
    """

    stamp = now or _now()
    job_ids = await _active_job_ids(session)
    refreshed = 0
    errors = 0
    for job_id in job_ids:
        job = await session.get(Job, job_id)
        if job is None:
            continue
        try:
            async with session.begin_nested():
                await refresh_job_competition(
                    session,
                    job_id=job_id,
                    org_id=job.org_id,
                    seats=job.headcount,
                    now=stamp,
                )
            refreshed += 1
        except Exception:  # noqa: BLE001 — one job must not abort the sweep
            errors += 1
            logger.warning(
                "job_competition.sweep_job_failed", extra={"job_id": str(job_id)}
            )
    await session.commit()
    return {"refreshed": refreshed, "errors": errors}
