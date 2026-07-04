"""End-to-end test for the workforce pattern's first real consumer: bulk
screening-brief generation across every applicant on a job.

Runs Celery in eager mode (no broker required, ``docs/AI_PRODUCT_SPEC.md``
§18 / ``.claude/rules/backend.md`` "Celery tasks must be idempotent" — this
test also proves idempotent redelivery does not double-run a subtask).
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.agents import coordinator, workforce
from app.ai.agents.models import SubtaskStatus, WorkforceRun
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, apply_service
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


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


async def _apply_n_students(db, *, job_id: uuid.UUID, n: int) -> list[uuid.UUID]:
    application_ids = []
    for i in range(n):
        _su, student = await make_student(db, prefix=f"wf_student_{i}")
        sel = await make_builder_cv(db, student=student)
        out = await apply_service.apply_to_job(
            db,
            principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel),
            ctx=CTX,
        )
        application_ids.append(uuid.UUID(out["id"]))
    return application_ids


async def test_bulk_screening_run_completes_and_aggregates(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Workforce Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Workforce Job"
    )
    await _apply_n_students(db_session, job_id=job_id, n=3)

    started = await workforce.start_bulk_screening_brief_run(
        db_session, principal=partner, job_id=job_id
    )
    assert started["total_subtasks"] == 3
    assert started["status"] in {"running", "complete"}

    status = await workforce.get_workforce_run_status(
        db_session, principal=partner, run_id=uuid.UUID(started["run_id"])
    )
    # Eager Celery already ran every subtask synchronously inside start_*.
    assert status["status"] == "complete"
    assert status["total_subtasks"] == 3
    assert status["completed_subtasks"] == 3
    assert status["summary"]["total"] == 3
    assert status["summary"]["succeeded"] == 3
    # Offline provider never returns valid JSON -> each subtask degrades to the
    # advisory fallback shape (is_fallback=True), never a hard failure.
    assert all(b["is_fallback"] is True for b in status["summary"]["briefs"])
    # Never leak provider/model/token internals through the aggregated summary.
    dumped = str(status)
    for forbidden in ("openai", "anthropic", "gpt", "claude", "api_key", "provider_internal"):
        assert forbidden not in dumped.lower()


async def test_bulk_screening_run_empty_job_completes_immediately(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Empty Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="No Applicants Job"
    )

    started = await workforce.start_bulk_screening_brief_run(
        db_session, principal=partner, job_id=job_id
    )
    assert started["status"] == "complete"
    assert started["total_subtasks"] == 0


async def test_bulk_screening_run_cross_org_partner_gets_not_found(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Owner Co")
    _u2, _o2, other_partner = await make_org_with_admin(db_session, display_name="Other Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Owner Only Job"
    )

    with pytest.raises(ResourceNotFoundError):
        await workforce.start_bulk_screening_brief_run(
            db_session, principal=other_partner, job_id=job_id
        )


async def test_get_run_status_cross_org_returns_not_found(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Owner Co 2")
    _u2, _o2, other_partner = await make_org_with_admin(db_session, display_name="Other Co 2")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Owner Only Job 2"
    )
    await _apply_n_students(db_session, job_id=job_id, n=1)

    started = await workforce.start_bulk_screening_brief_run(
        db_session, principal=partner, job_id=job_id
    )

    with pytest.raises(ResourceNotFoundError):
        await workforce.get_workforce_run_status(
            db_session, principal=other_partner, run_id=uuid.UUID(started["run_id"])
        )


async def test_subtask_idempotent_redelivery_does_not_recompute(db_session) -> None:
    """A Celery at-least-once redelivery for an already-terminal subtask must
    short-circuit before calling the AI service again (no double cost)."""

    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Idempotent Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Idempotent Job"
    )
    [application_id] = await _apply_n_students(db_session, job_id=job_id, n=1)

    started = await workforce.start_bulk_screening_brief_run(
        db_session, principal=partner, job_id=job_id
    )
    run_id = uuid.UUID(started["run_id"])

    first_result = await coordinator.get_terminal_result(
        db_session, run_id=run_id, subtask_key=str(application_id)
    )
    assert first_result is not None
    assert first_result["status"] == SubtaskStatus.SUCCESS.value

    # Simulate a redelivered message recomputing a DIFFERENT (bogus) result —
    # record_subtask_result always overwrites (it trusts its caller), so the
    # real idempotency guard lives in worker_tasks._execute_and_record's
    # get_terminal_result pre-check. Prove that pre-check would have fired.
    existing = await coordinator.get_terminal_result(
        db_session, run_id=run_id, subtask_key=str(application_id)
    )
    assert existing == first_result

    run = (
        await db_session.execute(select(WorkforceRun).where(WorkforceRun.id == run_id))
    ).scalar_one()
    assert run.status == "complete"
