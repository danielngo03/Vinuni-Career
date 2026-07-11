"""Per-job application funnel counts for the owner (partner) jobs read-model.

The ``opportunities`` module's ``GET /jobs/mine`` list needs two live recruiting
signals per job that live in the ``recruitment`` domain: how many applications are
still waiting for a first screen (``unreviewed``) and how many are actively moving
through the pipeline (``in_pipeline``). This facade is the read seam other modules
call so they never import the ``Application`` / ``CandidateStage`` ORM directly
(`docs/ARCHITECTURE.md`: communicate through interfaces/read models).

Both counts are computed for a WHOLE page of jobs in a single grouped pass each
(no per-job N+1): one ``GROUP BY job_id`` over ``applications`` for the unreviewed
count and one over ``applications JOIN candidate_stages`` (ACTIVE stage row only)
for the in-pipeline count.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.domain import lifecycle, pipeline
from app.modules.recruitment.domain.models import Application, CandidateStage


@dataclass(frozen=True)
class JobAppStats:
    """Live funnel counts for one job (both default to 0 when absent)."""

    unreviewed: int = 0
    in_pipeline: int = 0


async def application_stats_for_jobs(
    session: AsyncSession, job_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, JobAppStats]:
    """Return ``{job_id: JobAppStats}`` for the given jobs (one grouped pass each).

    - ``unreviewed`` — applications still ``submitted`` (never reviewed): the "new
      to screen" number.
    - ``in_pipeline`` — applications with an ACTIVE ``candidate_stages`` row (moving
      through the configured pipeline).

    Jobs with no applications are simply absent from the map; the caller defaults
    them to ``JobAppStats()`` (both 0).
    """

    ids = {i for i in job_ids if i is not None}
    if not ids:
        return {}

    unreviewed_rows = (
        await session.execute(
            select(Application.job_id, func.count())
            .where(
                Application.job_id.in_(ids),
                Application.deleted_at.is_(None),
                Application.status == lifecycle.SUBMITTED,
            )
            .group_by(Application.job_id)
        )
    ).all()
    unreviewed = {job_id: int(count) for job_id, count in unreviewed_rows}

    in_pipeline_rows = (
        await session.execute(
            select(Application.job_id, func.count())
            .select_from(Application)
            .join(CandidateStage, CandidateStage.application_id == Application.id)
            .where(
                Application.job_id.in_(ids),
                Application.deleted_at.is_(None),
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
            .group_by(Application.job_id)
        )
    ).all()
    in_pipeline = {job_id: int(count) for job_id, count in in_pipeline_rows}

    return {
        job_id: JobAppStats(
            unreviewed=unreviewed.get(job_id, 0),
            in_pipeline=in_pipeline.get(job_id, 0),
        )
        for job_id in ids
        if job_id in unreviewed or job_id in in_pipeline
    }
