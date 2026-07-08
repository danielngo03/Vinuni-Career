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
from datetime import UTC, datetime, timedelta

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
from app.modules.documents.application import job_fit_batch_service
from app.modules.opportunities.application import job_fit_read
from app.modules.recruitment.application import apply_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

logger = logging.getLogger(__name__)

_RESOURCE = "ai_workforce"

# Cost/latency guard: a single bulk run fans out at most this many LLM calls.
# Larger applicant pools can re-run against the remainder (no data loss — the
# request is simply capped, not silently truncated without saying so).
MAX_SUBTASKS_PER_RUN = 25

BULK_SCREENING_TASK_TYPE = "bulk_screening_brief"
SCREENING_BRIEF_SUBTASK_TYPE = "screening_brief"

# --- Student CV re-score (Task O / WS-11) ---------------------------------- #
# A student-scoped background job: batch-refresh the deterministic CV-JD fit
# scores for the student's active CVs against recently posted/amended jobs so
# their job intelligence stays fresh without a foreground request. One subtask
# per candidate job; each subtask deterministically re-scores every active CV
# against that job (NO LLM — the scoring is free) and upserts the version-stamped
# ``cv_job_fit_scores`` rows. No consequential write beyond refreshing the
# student's OWN scores (no applying / messaging — those stay confirmation-gated
# in the foreground).
STUDENT_CV_RESCORE_TASK_TYPE = "student_cv_rescore"
CV_RESCORE_SUBTASK_TYPE = "cv_rescore_job"

# A single re-score run fans out at most this many per-job subtasks. The
# candidate set is bounded here and any overflow is LOGGED (never silently
# dropped) — the next scheduled run picks up jobs that missed the cap.
MAX_RESCORE_SUBTASKS_PER_RUN = 40

# Only jobs published or amended within this window are re-score candidates:
# "recently posted / newly matched" freshness, not the whole marketplace.
RESCORE_LOOKBACK_DAYS = 14

# Personas that own a personal CV library and are therefore eligible for the
# background re-score. An org-scoped principal (partner/university admin) holds a
# wildcard org grant that would otherwise satisfy the ``cv:read`` check, so the
# persona is gated explicitly — this is a student (CV-owner) background job.
_RESCORE_PERSONAS = frozenset({"student"})


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


def decompose_student_cv_rescore(job_ids: list[str]) -> list[SubtaskSpec]:
    """One subtask per candidate job. Deterministic key (job_id) -> retry-safe.

    Hard-capped at ``MAX_RESCORE_SUBTASKS_PER_RUN``. When the candidate set is
    larger the overflow is LOGGED (never silently truncated) so it is visible in
    logs that some jobs were deferred to the next scheduled run.
    """

    if len(job_ids) > MAX_RESCORE_SUBTASKS_PER_RUN:
        logger.warning(
            "workforce_run.rescore_candidates_capped",
            extra={
                "candidate_count": len(job_ids),
                "cap": MAX_RESCORE_SUBTASKS_PER_RUN,
                "deferred": len(job_ids) - MAX_RESCORE_SUBTASKS_PER_RUN,
            },
        )
    capped = job_ids[:MAX_RESCORE_SUBTASKS_PER_RUN]
    return [
        SubtaskSpec(
            key=job_id,
            subtask_type=CV_RESCORE_SUBTASK_TYPE,
            payload={"job_id": job_id},
        )
        for job_id in capped
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


def aggregate_rescore_results(subtask_results_json: dict) -> dict:
    """Roll per-job re-score outcomes into a run-level summary.

    User-safe / owner-scoped only: ``recommended_cv_id`` is the student's OWN CV;
    ``signal`` is the public fit signal. No score internals, provider/model, or
    token metadata is ever added here (the deterministic score itself is not even
    echoed — the authoritative value lives on the persisted ``cv_job_fit_scores``
    row the student reads through the normal fit endpoints).
    """

    jobs: list[dict] = []
    refreshed = 0
    failed = 0
    skipped = 0
    for job_id, entry in subtask_results_json.items():
        status = entry.get("status")
        if status == SubtaskStatus.SUCCESS.value:
            result = entry.get("result") or {}
            if result.get("skipped"):
                skipped += 1
            else:
                refreshed += 1
            jobs.append(
                {
                    "job_id": job_id,
                    "scored_cvs": int(result.get("scored_cvs") or 0),
                    "recommended_cv_id": result.get("recommended_cv_id"),
                    "signal": result.get("signal"),
                    "skipped": result.get("skipped"),
                }
            )
        else:
            failed += 1
            jobs.append(
                {
                    "job_id": job_id,
                    "scored_cvs": 0,
                    "recommended_cv_id": None,
                    "signal": None,
                    "skipped": None,
                }
            )
    return {
        "total": len(subtask_results_json),
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "jobs": jobs,
    }


# Register a new workforce task type's aggregator here — the run's ``task_type``
# selects it in ``record_subtask_result`` / ``start_*``. Never branch a single
# aggregator on ``task_type``.
_AGGREGATORS = {
    BULK_SCREENING_TASK_TYPE: aggregate_screening_results,
    STUDENT_CV_RESCORE_TASK_TYPE: aggregate_rescore_results,
}


def _aggregate(task_type: str, results: dict) -> dict:
    aggregator = _AGGREGATORS.get(task_type, aggregate_screening_results)
    return aggregator(results)


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


async def start_student_cv_rescore_run(
    session: AsyncSession, *, principal: Principal
) -> WorkforceRun:
    """Plan + dispatch a background CV re-score run for one student.

    RBAC: student-scoped + owner-checked. The principal must be a CV-owner
    persona AND hold ``cv:read`` (students hold ``cv:*``). A partner/university
    admin — whose wildcard org grant would otherwise satisfy ``cv:read`` — is
    rejected by the explicit persona gate (``PermissionDeniedError``) before any
    planning, so a run can only ever refresh the caller's OWN fit scores.

    Planning is deterministic and side-effect-light:
      1. Skip entirely (empty, immediately-complete run) when the student has no
         active CV — there is nothing to score.
      2. Discover recently posted/amended jobs the student can discover
         (``job_fit_read.recent_candidate_job_ids``), bounded + logged if capped.
      3. One subtask per candidate job; each subtask re-scores every active CV
         against that job deterministically (NO LLM) and refreshes the
         version-stamped ``cv_job_fit_scores`` rows.

    An audit row is written for the run (metadata only — candidate/subtask counts,
    lookback window, capped flag) in the SAME transaction as the run insert, so
    the audit and run commit atomically. No provider/model/token internals and no
    PII cross into the audit snapshot.
    """

    if principal.persona not in _RESCORE_PERSONAS:
        # A partner/university admin holds a wildcard grant that would pass the
        # ``cv:read`` check below — reject non-CV-owner personas up front so a
        # run can only ever be a student refreshing their own scores.
        raise PermissionDeniedError()
    permission_checker.require(principal, "cv", "read")
    assert principal.user_id is not None

    cv_count = await job_fit_batch_service.active_cv_count(session, principal=principal)
    if cv_count == 0:
        job_ids: list[str] = []
    else:
        since = datetime.now(tz=UTC) - timedelta(days=RESCORE_LOOKBACK_DAYS)
        candidate_ids = await job_fit_read.recent_candidate_job_ids(
            session,
            persona=principal.persona,
            since=since,
            # Fetch a little past the cap so ``decompose`` can see + log the overflow.
            limit=MAX_RESCORE_SUBTASKS_PER_RUN * 4,
        )
        job_ids = [str(jid) for jid in candidate_ids]

    subtasks = decompose_student_cv_rescore(job_ids)
    capped = len(job_ids) > MAX_RESCORE_SUBTASKS_PER_RUN

    run = WorkforceRun(
        id=uuid.uuid4(),
        task_type=STUDENT_CV_RESCORE_TASK_TYPE,
        status=(RunStatus.COMPLETE if not subtasks else RunStatus.RUNNING).value,
        requested_by_user_id=principal.user_id,
        org_id=principal.org_id,
        context_json={
            "principal": _serialize_principal(principal),
            "lookback_days": RESCORE_LOOKBACK_DAYS,
            "active_cv_count": cv_count,
        },
        subtask_keys_json=[s.key for s in subtasks],
        subtask_results_json={},
        summary_json=(aggregate_rescore_results({}) if not subtasks else None),
    )
    if not subtasks:
        run.completed_at = datetime.now(tz=UTC)
    session.add(run)
    await session.flush()

    # Audit the run (metadata only) in the run's own transaction.
    await write_audit(
        session,
        action="ai.workforce.student_cv_rescore.start",
        resource_type=_RESOURCE,
        resource_id=run.id,
        context=AuditContext(
            actor_id=principal.user_id, actor_org_id=principal.org_id
        ),
        after={
            "task_type": STUDENT_CV_RESCORE_TASK_TYPE,
            "candidate_jobs": len(job_ids),
            "subtasks": len(subtasks),
            "active_cv_count": cv_count,
            "lookback_days": RESCORE_LOOKBACK_DAYS,
            "capped": capped,
        },
    )
    await session.commit()

    logger.info(
        "workforce_run.start",
        extra={
            "run_id": str(run.id),
            "task_type": run.task_type,
            "subtask_count": len(subtasks),
            "candidate_jobs": len(job_ids),
            "capped": capped,
        },
    )

    if subtasks:
        from app.ai.agents import worker_tasks

        for subtask in subtasks:
            worker_tasks.dispatch_subtask(run_id=run.id, subtask=subtask)
    else:
        logger.info(
            "workforce_run.end", extra={"run_id": str(run.id), "status": run.status}
        )

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
        run.summary_json = _aggregate(run.task_type, results)
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
