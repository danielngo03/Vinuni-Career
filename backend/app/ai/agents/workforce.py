"""Public entrypoint for the workforce (multi-agent) pattern.

Other modules/routers should only ever import from here, never reach into
``coordinator``/``worker_tasks`` directly — this is the thin facade the rest
of the codebase depends on (``docs/AI_PRODUCT_SPEC.md`` §4.2).

Exposes two real consumers:

- **Bulk screening-brief** generation for a partner reviewing many applicants on
  one job (fan-out: one subtask per applicant).
- **University operations deep-analysis** — a granted university staffer starts a
  bounded, READ-ONLY multi-agent analysis on a partner employer's hiring quality
  (fan-out: 4 fixed deterministic sub-passes → a synthesized, privacy-safe
  report). See ``app.ai.agents.operations_analysis``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator, operations_analysis
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


async def start_operations_analysis_run(
    session: AsyncSession,
    *,
    principal: Principal,
    target_org_id: uuid.UUID,
    target_type: str = operations_analysis.TARGET_PARTNER_HIRING_QUALITY,
) -> dict:
    """Kick off a university operations deep-analysis run on a partner target.

    Returns immediately with ``{run_id, status, total_subtasks, target_type}`` —
    the caller polls ``get_operations_analysis_status`` (or the
    ``GET /ai/workforce/runs/{run_id}`` route) for progress + the report.
    RBAC-gated in the service layer (university-org staffer with ``partners:read``,
    or superadmin). Read-only + advisory — no consequential domain write.
    """

    run = await operations_analysis.start_operations_analysis_run(
        session,
        principal=principal,
        target_type=target_type,
        target_org_id=target_org_id,
    )
    return {
        "run_id": str(run.id),
        "status": run.status,
        "total_subtasks": len(run.subtask_keys_json),
        "target_type": target_type,
    }


async def get_operations_analysis_status(
    session: AsyncSession, *, principal: Principal, run_id: uuid.UUID
) -> dict:
    """Current status + (if terminal) the synthesized operations report.

    Reuses the shared, owner/org/superadmin-scoped run read — a cross-user /
    cross-org run id 404s exactly like the bulk-screening consumer.
    """

    return await coordinator.get_run(session, principal=principal, run_id=run_id)
