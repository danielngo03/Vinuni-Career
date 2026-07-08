"""End-to-end tests for the workforce pattern's student consumer: the
background CV re-score job (Task O / WS-11).

For a student, the job re-scores their active CVs against recently posted jobs
DETERMINISTICALLY (no LLM in the loop) and refreshes the version-stamped
``cv_job_fit_scores`` rows, so their job intelligence stays fresh without a
foreground request. Runs Celery in eager mode (no broker), and proves:

  (a) the run re-scores a student's CVs vs new jobs deterministically + persists;
  (b) idempotency — a re-run yields the same rows, no duplicates;
  (c) the batch cap is logged (never silently truncated);
  (d) the run is audited;
  (e) no unconfirmed consequential write (no applications / notifications);
plus RBAC (non-student rejected) and the no-active-CV empty-run path.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from app.ai.agents import coordinator, workforce
from app.modules.documents.domain.models import CvJobFitScore
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import PermissionDeniedError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job


@pytest.fixture(autouse=True)
def _eager_celery():
    """Run workforce Celery tasks synchronously, in-process — no real broker."""

    from app.modules.automation.workers.celery_app import celery_app

    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


async def _publish_jobs(db_session, *, n: int) -> list[uuid.UUID]:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Rescore Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_ids = []
    for i in range(n):
        job_ids.append(
            await publish_job(
                db_session,
                partner_principal=partner,
                uni_principal=uni,
                title=f"Rescore Job {i}",
            )
        )
    return job_ids


async def _fit_rows(db_session, *, user_id: uuid.UUID) -> list[CvJobFitScore]:
    rows = (
        await db_session.execute(
            select(CvJobFitScore).where(CvJobFitScore.user_id == user_id)
        )
    ).scalars().all()
    return list(rows)


async def test_rescore_run_scores_cvs_vs_new_jobs_and_persists(db_session) -> None:
    _su, student = await make_student(db_session, prefix="rescore_a")
    await make_ready_cv(db_session, student=student, title="My CV")
    job_ids = await _publish_jobs(db_session, n=3)

    started = await workforce.start_student_cv_rescore_run(
        db_session, principal=student
    )
    assert started["total_subtasks"] == 3
    # The returned status reflects creation time ("running" with subtasks); the
    # eager subtasks complete the run in their own worker session, observed via
    # get_workforce_run_status (same contract as the bulk-screening consumer).
    assert started["status"] in {"running", "complete"}

    status = await workforce.get_workforce_run_status(
        db_session, principal=student, run_id=uuid.UUID(started["run_id"])
    )
    assert status["status"] == "complete"
    assert status["completed_subtasks"] == 3
    assert status["summary"]["total"] == 3
    assert status["summary"]["refreshed"] == 3
    assert status["summary"]["failed"] == 0

    # One persisted deterministic fit row per (active CV, job) — the whole point:
    # the student's job intelligence is now warm without a foreground request.
    rows = await _fit_rows(db_session, user_id=student.user_id)
    persisted_job_ids = {r.job_id for r in rows}
    assert persisted_job_ids == set(job_ids)

    # Never leak provider/model/token internals through the run status/summary.
    dumped = str(status).lower()
    for forbidden in ("openai", "anthropic", "gpt", "claude", "api_key", "provider"):
        assert forbidden not in dumped


async def test_rescore_run_is_idempotent_no_duplicate_rows(db_session) -> None:
    _su, student = await make_student(db_session, prefix="rescore_idem")
    await make_ready_cv(db_session, student=student, title="My CV")
    await _publish_jobs(db_session, n=2)

    first = await workforce.start_student_cv_rescore_run(db_session, principal=student)
    assert first["total_subtasks"] == 2
    rows_1 = await _fit_rows(db_session, user_id=student.user_id)
    snapshot_1 = {
        (r.cv_id, r.job_id): (r.score, r.cv_version, r.job_version, r.scorer_version)
        for r in rows_1
    }
    assert len(snapshot_1) == 2

    # Re-run against the SAME unchanged jobs/CVs: fresh rows short-circuit; the
    # recompute (if any) yields identical rows; the upsert never duplicates.
    second = await workforce.start_student_cv_rescore_run(db_session, principal=student)
    assert second["total_subtasks"] == 2
    rows_2 = await _fit_rows(db_session, user_id=student.user_id)
    snapshot_2 = {
        (r.cv_id, r.job_id): (r.score, r.cv_version, r.job_version, r.scorer_version)
        for r in rows_2
    }

    assert len(rows_2) == len(rows_1)  # no duplicate rows
    assert snapshot_2 == snapshot_1  # identical deterministic scores/stamps


async def test_rescore_run_is_audited(db_session) -> None:
    _su, student = await make_student(db_session, prefix="rescore_audit")
    await make_ready_cv(db_session, student=student, title="My CV")
    await _publish_jobs(db_session, n=1)

    started = await workforce.start_student_cv_rescore_run(
        db_session, principal=student
    )
    run_id = uuid.UUID(started["run_id"])

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "ai.workforce.student_cv_rescore.start",
                AuditLog.resource_id == run_id,
            )
        )
    ).scalar_one()
    assert audit.actor_id == student.user_id
    assert audit.after_snapshot["task_type"] == "student_cv_rescore"
    assert audit.after_snapshot["subtasks"] == 1
    assert audit.after_snapshot["capped"] is False


async def test_rescore_run_makes_no_consequential_write(db_session) -> None:
    """The background job must ONLY refresh the student's own fit scores — never
    apply, message, or enqueue a notification (those stay confirmation-gated)."""

    _su, student = await make_student(db_session, prefix="rescore_safe")
    await make_ready_cv(db_session, student=student, title="My CV")
    await _publish_jobs(db_session, n=2)

    async def _count(model) -> int:
        return (
            await db_session.execute(select(func.count()).select_from(model))
        ).scalar_one()

    # Baseline AFTER setup (publishing jobs may itself enqueue partner notices) —
    # the rescore run must not add a single consequential write on top.
    apps_before = await _count(Application)
    outbox_before = await _count(NotificationOutbox)

    await workforce.start_student_cv_rescore_run(db_session, principal=student)

    assert await _count(Application) == apps_before
    assert await _count(NotificationOutbox) == outbox_before


async def test_rescore_run_no_active_cv_completes_empty(db_session) -> None:
    _su, student = await make_student(db_session, prefix="rescore_nocv")
    await _publish_jobs(db_session, n=2)

    started = await workforce.start_student_cv_rescore_run(
        db_session, principal=student
    )
    # No matchable CV -> nothing to score -> immediately-complete empty run.
    assert started["total_subtasks"] == 0
    assert started["status"] == "complete"
    rows = await _fit_rows(db_session, user_id=student.user_id)
    assert rows == []


async def test_rescore_run_rejects_non_student_principal(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Not A Student")

    # A partner principal has no ``cv:read`` grant -> owner-check rejects planning.
    with pytest.raises(PermissionDeniedError):
        await workforce.start_student_cv_rescore_run(db_session, principal=partner)


async def test_rescore_run_caps_and_logs_when_candidates_exceed_cap(
    db_session, monkeypatch, caplog
) -> None:
    """The candidate set is bounded + LOGGED (never silently truncated), and the
    audit row records the ``capped`` flag."""

    _su, student = await make_student(db_session, prefix="rescore_cap")
    await make_ready_cv(db_session, student=student, title="My CV")

    # Simulate a large candidate pool without publishing 40+ real jobs: the extra
    # (non-visible) ids fall through to a "job_not_visible" skip in the executor,
    # so the run still completes — we only assert the cap + log + audit flag.
    overflow = coordinator.MAX_RESCORE_SUBTASKS_PER_RUN + 6
    fake_ids = [uuid.uuid4() for _ in range(overflow)]

    async def _fake_recent(*_args, **_kwargs):
        return fake_ids

    monkeypatch.setattr(
        coordinator.job_fit_read, "recent_candidate_job_ids", _fake_recent
    )

    with caplog.at_level(logging.WARNING, logger="app.ai.agents.coordinator"):
        started = await workforce.start_student_cv_rescore_run(
            db_session, principal=student
        )

    assert started["total_subtasks"] == coordinator.MAX_RESCORE_SUBTASKS_PER_RUN
    assert any(
        "rescore_candidates_capped" in rec.message for rec in caplog.records
    )

    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "ai.workforce.student_cv_rescore.start",
                AuditLog.resource_id == uuid.UUID(started["run_id"]),
            )
        )
    ).scalar_one()
    assert audit.after_snapshot["capped"] is True
    assert audit.after_snapshot["candidate_jobs"] == overflow


async def test_scheduler_sweep_starts_runs_for_active_students(db_session) -> None:
    """The autonomous trigger: the registered scheduler job starts a per-student
    run (no foreground request) and refreshes that student's fit rows."""

    from app.modules.automation.scheduler import runner

    _su, student = await make_student(db_session, prefix="rescore_sweep")
    await make_ready_cv(db_session, student=student, title="My CV")
    await _publish_jobs(db_session, n=2)

    # Drive it exactly as scheduled (through the registry entry), never the
    # sweep function directly — proving the job is really registered + runs.
    result = await runner.run_job("ai.student_cv_rescore_sweep")
    assert result.get("students", 0) >= 1
    assert result.get("runs_started", 0) >= 1
    assert result.get("capped") == 0

    rows = await _fit_rows(db_session, user_id=student.user_id)
    assert len(rows) == 2  # both recent jobs scored for the student's active CV
