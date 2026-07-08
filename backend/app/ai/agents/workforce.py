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

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator
from app.modules.auth.domain.personas import permissions_for
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

# The scheduled sweep refreshes at most this many active students per tick. A
# larger active-student pool is not silently dropped: the overflow is LOGGED and
# picked up by the next scheduled run (idempotent — fresh rows short-circuit).
STUDENT_RESCORE_SWEEP_BATCH = 200


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


async def start_student_cv_rescore_run(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Kick off a background CV re-score run for the calling student.

    Deterministically refreshes the student's CV-JD fit scores against recently
    posted/amended jobs (NO LLM in the loop; the scoring is free) so their job
    intelligence stays fresh without a foreground request. Owner-checked +
    audited in the coordinator. Returns ``{run_id, status, total_subtasks}``.
    """

    run = await coordinator.start_student_cv_rescore_run(session, principal=principal)
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_subtasks": len(run.subtask_keys_json),
    }


async def sweep_student_cv_rescore(
    session: AsyncSession,
    now: datetime,
    *,
    limit: int = STUDENT_RESCORE_SWEEP_BATCH,
) -> dict[str, int]:
    """Scheduler entrypoint: start a CV re-score run for each active student.

    The autonomous trigger for the background freshness job (registered in the
    scheduler REGISTRY). For every active student it reconstructs a student
    :class:`Principal` (persona-baseline ``cv:*`` grants) and delegates to the
    owner-checked, audited coordinator. The whole job is bounded by ``limit``;
    when the active-student pool exceeds it the overflow is LOGGED (never silently
    dropped) and refreshed on the next tick.

    Idempotent + safe:
      - each run only refreshes that student's OWN version-stamped fit rows
        (fresh rows short-circuit, so a re-tick is cheap);
      - NO consequential write (no applying / messaging / notifications);
      - one student's failure never aborts the sweep.

    Returns ``{students, runs_started, runs_empty, capped}``.
    """
    from app.modules.users.application import user_read_facade

    contacts = await user_read_facade.list_active_persona_contacts(
        session, "student", limit=limit
    )
    capped = len(contacts) >= limit
    if capped:
        logger.warning(
            "student_cv_rescore.sweep_capped",
            extra={"limit": limit, "found": len(contacts)},
        )

    runs_started = 0
    runs_empty = 0
    student_permissions = permissions_for("student")
    for contact in contacts:
        principal = Principal(
            user_id=contact.id,
            persona="student",
            org_id=None,
            is_superadmin=False,
            permissions=student_permissions,
        )
        try:
            run = await coordinator.start_student_cv_rescore_run(
                session, principal=principal
            )
        except Exception:  # noqa: BLE001 - one student must not crash the sweep
            logger.warning(
                "student_cv_rescore.student_failed",
                extra={"student_id": str(contact.id)},
                exc_info=True,
            )
            continue
        if run.subtask_keys_json:
            runs_started += 1
        else:
            runs_empty += 1

    return {
        "students": len(contacts),
        "runs_started": runs_started,
        "runs_empty": runs_empty,
        "capped": int(capped),
    }


async def get_workforce_run_status(
    session: AsyncSession, *, principal: Principal, run_id: uuid.UUID
) -> dict:
    """Current status + (if terminal) aggregated results for a workforce run."""

    return await coordinator.get_run(session, principal=principal, run_id=run_id)
