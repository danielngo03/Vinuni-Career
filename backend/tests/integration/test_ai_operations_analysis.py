"""End-to-end test for the workforce pattern's SECOND consumer: university
operations deep-analysis of a partner's hiring quality (§4.2 / WS3.4).

Runs Celery in eager mode (no broker) so the coordinator's fan-out executes
in-process. Proves: fan-out + synthesis, RBAC (granted / ungranted / partner /
superadmin / cross-org), idempotent redelivery, the degraded → partial path, and
privacy-safe output (no PII / provider / model / token leakage).
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.agents import coordinator, operations_analysis as oa, workforce
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, apply_service
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal

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
    from app.modules.automation.workers.celery_app import celery_app

    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


async def _apply_students(db, *, job_id: uuid.UUID, n: int) -> None:
    for i in range(n):
        _su, student = await make_student(db, prefix=f"ops_student_{i}")
        sel = await make_builder_cv(db, student=student)
        await apply_service.apply_to_job(
            db,
            principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel),
            ctx=CTX,
        )


async def _partner_with_job(db, *, applicants: int = 2):
    _pu, porg, partner = await make_org_with_admin(db, display_name="Ops Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title="Ops Partner Role"
    )
    if applicants:
        await _apply_students(db, job_id=job_id, n=applicants)
    return porg, uni, job_id


# --------------------------------------------------------------------------- #
# Happy path: fan-out + synthesis                                             #
# --------------------------------------------------------------------------- #


async def test_operations_analysis_completes_and_synthesizes(db_session) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=2)

    started = await workforce.start_operations_analysis_run(
        db_session, principal=uni, target_org_id=porg.id
    )
    assert started["total_subtasks"] == 4
    assert started["target_type"] == oa.TARGET_PARTNER_HIRING_QUALITY

    status = await workforce.get_operations_analysis_status(
        db_session, principal=uni, run_id=uuid.UUID(started["run_id"])
    )
    # Eager Celery already ran every deterministic pass synchronously.
    assert status["status"] == "complete"
    assert status["total_subtasks"] == 4
    assert status["completed_subtasks"] == 4

    report = status["summary"]
    assert set(report.keys()) == {
        "target",
        "summary",
        "findings",
        "recommendations",
        "caveats",
        "coverage",
    }
    assert report["target"] == {"type": oa.TARGET_PARTNER_HIRING_QUALITY}
    assert report["coverage"]["passes_ok"] == 4
    assert {f["area"] for f in report["findings"]} == set(oa.OPS_PASSES)
    # Offline provider → no chargeable narratives; deterministic signals only.
    assert report["coverage"]["narratives"] == 0
    assert any("advisory only" in c.lower() for c in report["caveats"])


async def test_operations_analysis_output_is_leakage_safe(db_session) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=1)
    started = await workforce.start_operations_analysis_run(
        db_session, principal=uni, target_org_id=porg.id
    )
    status = await workforce.get_operations_analysis_status(
        db_session, principal=uni, run_id=uuid.UUID(started["run_id"])
    )
    dumped = str(status).lower()
    for forbidden in (
        "openai",
        "anthropic",
        "gpt",
        "claude",
        "deepseek",
        "gemini",
        "api_key",
        "model_alias",
        "prompt_tokens",
        "ops_student",  # student login/email prefix must never appear
    ):
        assert forbidden not in dumped


# --------------------------------------------------------------------------- #
# RBAC                                                                         #
# --------------------------------------------------------------------------- #


async def test_ungranted_university_staffer_denied(db_session) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=1)
    # Same real university org, but a staffer with no grants.
    ungranted = Principal(
        user_id=uuid.uuid4(),
        persona="university_staff",
        org_id=uni.org_id,
        permissions=frozenset(),
    )
    with pytest.raises(PermissionDeniedError):
        await workforce.start_operations_analysis_run(
            db_session, principal=ungranted, target_org_id=porg.id
        )


async def test_partner_cannot_run_analysis(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Some Partner")
    _pu2, porg2, _partner2 = await make_org_with_admin(db_session, display_name="Target Co")
    with pytest.raises(PermissionDeniedError):
        await workforce.start_operations_analysis_run(
            db_session, principal=partner, target_org_id=porg2.id
        )


async def test_target_must_be_a_partner_org(db_session) -> None:
    _uu, uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # Targeting a university org (not a partner) 404s — no existence leak.
    with pytest.raises(ResourceNotFoundError):
        await workforce.start_operations_analysis_run(
            db_session, principal=uni, target_org_id=uorg.id
        )


async def test_superadmin_can_run_analysis(db_session) -> None:
    porg, _uni, _job_id = await _partner_with_job(db_session, applicants=1)
    superadmin = Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        is_superadmin=True,
        permissions=frozenset({"*"}),
    )
    started = await workforce.start_operations_analysis_run(
        db_session, principal=superadmin, target_org_id=porg.id
    )
    status = await workforce.get_operations_analysis_status(
        db_session, principal=superadmin, run_id=uuid.UUID(started["run_id"])
    )
    assert status["status"] == "complete"


async def test_cross_org_run_status_not_found(db_session) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=1)
    _uu2, _uorg2, other_uni = await make_org_with_admin(
        db_session, org_type="university", display_name="Other Uni"
    )
    started = await workforce.start_operations_analysis_run(
        db_session, principal=uni, target_org_id=porg.id
    )
    with pytest.raises(ResourceNotFoundError):
        await workforce.get_operations_analysis_status(
            db_session, principal=other_uni, run_id=uuid.UUID(started["run_id"])
        )


# --------------------------------------------------------------------------- #
# Idempotency                                                                  #
# --------------------------------------------------------------------------- #


async def test_subtask_idempotent_redelivery_does_not_recompute(db_session) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=1)
    started = await workforce.start_operations_analysis_run(
        db_session, principal=uni, target_org_id=porg.id
    )
    run_id = uuid.UUID(started["run_id"])

    first = await coordinator.get_terminal_result(
        db_session, run_id=run_id, subtask_key="jobs_quality"
    )
    assert first is not None and first["status"] == "success"

    # A redelivered message would find the same terminal result and short-circuit.
    again = await coordinator.get_terminal_result(
        db_session, run_id=run_id, subtask_key="jobs_quality"
    )
    assert again == first


# --------------------------------------------------------------------------- #
# Degraded → partial (a failed sub-pass must never fabricate a finding)        #
# --------------------------------------------------------------------------- #


async def test_failed_pass_degrades_to_partial_report(db_session, monkeypatch) -> None:
    porg, uni, _job_id = await _partner_with_job(db_session, applicants=1)

    async def _boom(_session, _org_id):
        raise RuntimeError("simulated read-model outage")

    monkeypatch.setitem(oa._READERS, "outcomes", _boom)

    started = await workforce.start_operations_analysis_run(
        db_session, principal=uni, target_org_id=porg.id
    )
    status = await workforce.get_operations_analysis_status(
        db_session, principal=uni, run_id=uuid.UUID(started["run_id"])
    )
    assert status["status"] == "partial"
    report = status["summary"]
    assert report["coverage"]["passes_ok"] == 3
    assert report["coverage"]["passes_failed"] == 1
    assert not any(f["area"] == "outcomes" for f in report["findings"])
    assert any("could not be" in c.lower() for c in report["caveats"])
