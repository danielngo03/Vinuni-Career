"""Public entrypoint for the workforce (multi-agent) pattern.

Other modules/routers should only ever import from here, never reach into
``coordinator``/``worker_tasks`` directly — this is the thin facade the rest
of the codebase depends on (``docs/AI_PRODUCT_SPEC.md`` §4.2).

Currently exposes exactly one real consumer: bulk screening-brief generation
for a partner reviewing many applicants on one job. See
``docs/IMPLEMENTATION_STATUS.md`` / the ai-engineer handoff for what is
deliberately NOT built yet (a second consumer, a real running Celery worker
process, and a scheduled TTL-sweep of old runs).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator
from app.shared.permissions import Principal


async def start_bulk_screening_brief_run(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> dict:
    """Kick off a workforce run that screens every (capped) applicant on a job.

    Returns immediately with ``{run_id, status, total_subtasks}`` — the caller
    polls ``get_workforce_run_status`` (or the
    ``GET /ai/workforce/runs/{run_id}`` route) for progress/results.
    """

    run = await coordinator.start_bulk_screening_run(
        session, principal=principal, job_id=job_id
    )
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_subtasks": len(run.subtask_keys_json),
    }


async def get_workforce_run_status(
    session: AsyncSession, *, principal: Principal, run_id: uuid.UUID
) -> dict:
    """Current status + (if terminal) aggregated results for a workforce run."""

    return await coordinator.get_run(session, principal=principal, run_id=run_id)
