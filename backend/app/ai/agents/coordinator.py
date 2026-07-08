"""Coordinator: task decomposition, subtask dispatch, and result aggregation.

Only the ``bulk_screening_brief`` task type is implemented (§4.2's first real
consumer — see ``docs/AI_PRODUCT_SPEC.md`` §4.2 "CV batch analysis (>1 CV)" /
analogous "screen multiple candidates" trigger). Adding a second workforce
task type means: (1) a new ``decompose_*`` function here, (2) a new executor
registered in ``worker_tasks.EXECUTORS``, (3) a new ``aggregate_*`` function —
never branching an existing function on ``task_type``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.models import (
    TERMINAL_SUBTASK_STATUSES,
    RunStatus,
    SubtaskResult,
    SubtaskSpec,
    SubtaskStatus,
    WorkforceRun,
)
from app.modules.recruitment.application import apply_service
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

_RESOURCE = "ai_workforce"

# Cost/latency guard: a single bulk run fans out at most this many LLM calls.
# Larger applicant pools can re-run against the remainder (no data loss — the
# request is simply capped, not silently truncated without saying so).
MAX_SUBTASKS_PER_RUN = 25

BULK_SCREENING_TASK_TYPE = "bulk_screening_brief"
SCREENING_BRIEF_SUBTASK_TYPE = "screening_brief"


# --------------------------------------------------------------------------- #
# Decomposition (pure)                                                        #
# --------------------------------------------------------------------------- #


def decompose_bulk_screening_brief(application_ids: list[str]) -> list[SubtaskSpec]:
    """One subtask per application. Deterministic key -> safe to retry/redispatch."""

    capped = application_ids[:MAX_SUBTASKS_PER_RUN]
    return [
        SubtaskSpec(
            key=application_id,
            subtask_type=SCREENING_BRIEF_SUBTASK_TYPE,
            payload={"application_id": application_id},
        )
        for application_id in capped
    ]


# --------------------------------------------------------------------------- #
# Aggregation (pure)                                                          #
# --------------------------------------------------------------------------- #


def aggregate_screening_results(subtask_results_json: dict) -> dict:
    """Roll per-application screening briefs into a job-level summary.

    User-safe only: bullets/suitability already went through the underlying
    service's output guard; nothing here adds provider/model/token internals.
    """

    briefs: list[dict] = []
    succeeded = 0
    failed = 0
    strong = 0
    for application_id, entry in subtask_results_json.items():
        status = entry.get("status")
        if status == SubtaskStatus.SUCCESS.value:
            succeeded += 1
            result = entry.get("result") or {}
            if result.get("suitability") == "strong":
                strong += 1
            briefs.append(
                {
                    "application_id": application_id,
                    "bullets": result.get("bullets") or [],
                    "suitability": result.get("suitability"),
                    "is_fallback": bool(result.get("is_fallback")),
                }
            )
        else:
            failed += 1
            briefs.append(
                {
                    "application_id": application_id,
                    "bullets": [],
                    "suitability": None,
                    "is_fallback": True,
                }
            )
    return {
        "total": len(subtask_results_json),
        "succeeded": succeeded,
        "failed": failed,
        "strong_matches": strong,
        "briefs": briefs,
    }


def _next_run_status(subtask_keys: list[str], results: dict) -> RunStatus:
    terminal = [
        results[k]
        for k in subtask_keys
        if k in results and results[k].get("status") in {s.value for s in TERMINAL_SUBTASK_STATUSES}
    ]
    if len(terminal) < len(subtask_keys):
        return RunStatus.RUNNING
    if all(r["status"] == SubtaskStatus.SUCCESS.value for r in terminal):
        return RunStatus.COMPLETE
    if any(r["status"] == SubtaskStatus.SUCCESS.value for r in terminal):
        return RunStatus.PARTIAL
    return RunStatus.FAILED


# --------------------------------------------------------------------------- #
# Principal (de)serialization — reconstructed inside the Celery worker process #
# --------------------------------------------------------------------------- #


def _serialize_principal(principal: Principal) -> dict:
    return {
        "user_id": str(principal.user_id) if principal.user_id else None,
        "persona": principal.persona,
        "org_id": str(principal.org_id) if principal.org_id else None,
        "is_superadmin": principal.is_superadmin,
        "permissions": sorted(principal.permissions),
    }


def deserialize_principal(data: dict) -> Principal:
    return Principal(
        user_id=uuid.UUID(data["user_id"]) if data.get("user_id") else None,
        persona=data.get("persona", "guest"),
        org_id=uuid.UUID(data["org_id"]) if data.get("org_id") else None,
        is_superadmin=bool(data.get("is_superadmin")),
        permissions=frozenset(data.get("permissions") or []),
    )


# --------------------------------------------------------------------------- #
# Run lifecycle                                                               #
# --------------------------------------------------------------------------- #


async def start_bulk_screening_run(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> WorkforceRun:
    """Plan + dispatch a bulk screening-brief run for one of the caller org's jobs.

    Reuses ``apply_service.list_job_applications`` for the org-scope + RBAC
    check (cross-org job -> 404, same as the single-application endpoint) so
    this feature does not duplicate or drift from that authorization logic.
    """

    items, _next_cursor, _limit = await apply_service.list_job_applications(
        session,
        principal=principal,
        job_id=job_id,
        limit=MAX_SUBTASKS_PER_RUN,
    )
    application_ids = [item["id"] for item in items]
    subtasks = decompose_bulk_screening_brief(application_ids)

    assert principal.user_id is not None
    run = WorkforceRun(
        id=uuid.uuid4(),
        task_type=BULK_SCREENING_TASK_TYPE,
        status=(RunStatus.COMPLETE if not subtasks else RunStatus.RUNNING).value,
        requested_by_user_id=principal.user_id,
        org_id=principal.org_id,
        context_json={
            "job_id": str(job_id),
            "principal": _serialize_principal(principal),
        },
        subtask_keys_json=[s.key for s in subtasks],
        subtask_results_json={},
        summary_json=(
            aggregate_screening_results({}) if not subtasks else None
        ),
    )
    if not subtasks:
        run.completed_at = datetime.now(tz=UTC)
    session.add(run)
    await session.flush()
    await session.commit()

    logger.info(
        "workforce_run.start",
        extra={
            "run_id": str(run.id),
            "task_type": run.task_type,
            "subtask_count": len(subtasks),
        },
    )

    if subtasks:
        from app.ai.agents import worker_tasks

        for subtask in subtasks:
            worker_tasks.dispatch_subtask(run_id=run.id, subtask=subtask)
    else:
        logger.info("workforce_run.end", extra={"run_id": str(run.id), "status": run.status})

    return run


async def _load_run(session: AsyncSession, run_id: uuid.UUID) -> WorkforceRun:
    run = (
        await session.execute(select(WorkforceRun).where(WorkforceRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise ResourceNotFoundError()
    return run


async def get_run(
    session: AsyncSession, *, principal: Principal, run_id: uuid.UUID
) -> dict:
    """Owner/org-scoped read of a workforce run's current status + results."""

    run = await _load_run(session, run_id)
    is_owner = principal.user_id is not None and principal.user_id == run.requested_by_user_id
    is_org_match = (
        principal.org_id is not None and run.org_id is not None and principal.org_id == run.org_id
    )
    if not (principal.is_superadmin or is_owner or is_org_match):
        raise ResourceNotFoundError()

    return _present_run(run)


def _present_run(run: WorkforceRun) -> dict:
    return {
        "run_id": str(run.id),
        "task_type": run.task_type,
        "status": run.status,
        "total_subtasks": len(run.subtask_keys_json),
        "completed_subtasks": sum(
            1
            for k in run.subtask_keys_json
            if k in run.subtask_results_json
            and run.subtask_results_json[k].get("status")
            in {s.value for s in TERMINAL_SUBTASK_STATUSES}
        ),
        "summary": run.summary_json,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


async def record_subtask_result(
    session: AsyncSession, *, run_id: uuid.UUID, result: SubtaskResult
) -> None:
    """Idempotently write one subtask's terminal result and re-aggregate.

    Called by the worker task. If the subtask already has a terminal result
    (a Celery at-least-once redelivery, not a legitimate re-run), the caller
    is expected to have already skipped re-executing the AI call — this just
    persists whatever was computed (or the no-op skip result the caller built
    from the existing row; see ``worker_tasks``).
    """

    run = await _load_run(session, run_id)
    results = dict(run.subtask_results_json)
    results[result.key] = result.to_json()
    run.subtask_results_json = results

    new_status = _next_run_status(run.subtask_keys_json, results)
    run.status = new_status.value
    logger.info(
        "workforce_run.subtask_recorded",
        extra={
            "run_id": str(run_id),
            "subtask_status": result.status.value,
            "duration_ms": result.duration_ms,
        },
    )
    if new_status in {RunStatus.COMPLETE, RunStatus.PARTIAL, RunStatus.FAILED}:
        run.summary_json = aggregate_screening_results(results)
        run.completed_at = datetime.now(tz=UTC)
        logger.info(
            "workforce_run.end", extra={"run_id": str(run_id), "status": new_status.value}
        )
    await session.flush()
    await session.commit()


async def load_run_principal(session: AsyncSession, run_id: uuid.UUID) -> Principal:
    """Reconstruct the acting principal stored at run-creation time.

    Called from the (separate-process) Celery worker task — it has no HTTP
    request/session context of its own, so the principal captured when the
    run was planned (already RBAC-checked in ``start_bulk_screening_run``) is
    the source of truth for the subtask's own permission checks.
    """

    run = await _load_run(session, run_id)
    return deserialize_principal(run.context_json.get("principal", {}))


async def get_terminal_result(
    session: AsyncSession, *, run_id: uuid.UUID, subtask_key: str
) -> dict | None:
    """Return the persisted result for ``subtask_key`` if it is already terminal.

    Used by the worker task for idempotency: if a redelivered Celery message
    finds a terminal result already recorded, it must not call the AI service
    again (no double cost, no double write).
    """

    run = await _load_run(session, run_id)
    entry = run.subtask_results_json.get(subtask_key)
    if entry and entry.get("status") in {s.value for s in TERMINAL_SUBTASK_STATUSES}:
        return entry
    return None
