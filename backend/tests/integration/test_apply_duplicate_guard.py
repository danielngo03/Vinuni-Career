"""Duplicate-application guard + ``already_applied`` apply-context contract (Task N).

The apply path already rejects a second ACTIVE application to the same job with a
clean ``409`` (``DuplicateApplicationError`` — never a raw ``500``). This slice
locks the full re-apply contract and makes the student-facing ``already_applied``
flag (which disables the apply button) EXACTLY match that server-side guard:

- a second active apply -> ``409 duplicate_application`` carrying the existing
  application id + status (deep-link, not a generic toast);
- a WITHDRAWN application frees the slot -> re-apply is allowed;
- a REJECTED application likewise frees the slot -> re-apply is allowed;
- the apply-context ``already_applied`` flag is ``True`` only while an ACTIVE
  application exists (submitted / under_review) and ``False`` once it is
  withdrawn / rejected, so the button-disable never contradicts the guard.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import student_intelligence_service
from app.modules.recruitment.application import access, apply_service, decision_service
from app.modules.recruitment.application.errors import DuplicateApplicationError
from app.modules.recruitment.domain import lifecycle

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup(db):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Acme")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)
    _su, student = await make_student(db)
    sel = await make_builder_cv(db, student=student)
    return partner, student, job_id, sel


async def _apply(db, *, student, job_id, sel):
    return await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Guard                                                                        #
# --------------------------------------------------------------------------- #


async def test_duplicate_active_apply_blocked_409(db_session) -> None:
    _partner, student, job_id, sel = await _setup(db_session)
    first = await _apply(db_session, student=student, job_id=job_id, sel=sel)

    with pytest.raises(DuplicateApplicationError) as exc:
        await _apply(db_session, student=student, job_id=job_id, sel=sel)

    # User-safe 409 (never a 500), with a deep-linkable existing application.
    assert exc.value.http_status == 409
    assert exc.value.details["reason"] == "duplicate_application"
    assert exc.value.details["application_id"] == first["id"]
    assert exc.value.details["status"] == lifecycle.SUBMITTED


async def test_withdrawn_allows_reapply(db_session) -> None:
    _partner, student, job_id, sel = await _setup(db_session)
    first = await _apply(db_session, student=student, job_id=job_id, sel=sel)

    await apply_service.withdraw_application(
        db_session,
        principal=student,
        application_id=uuid.UUID(first["id"]),
        ctx=CTX,
    )

    second = await _apply(db_session, student=student, job_id=job_id, sel=sel)
    assert second["id"] != first["id"]
    assert second["status"] == lifecycle.SUBMITTED


async def test_rejected_allows_reapply(db_session) -> None:
    partner, student, job_id, sel = await _setup(db_session)
    first = await _apply(db_session, student=student, job_id=job_id, sel=sel)

    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=uuid.UUID(first["id"]),
        reason="not_qualified",
        ctx=CTX,
    )

    second = await _apply(db_session, student=student, job_id=job_id, sel=sel)
    assert second["id"] != first["id"]
    assert second["status"] == lifecycle.SUBMITTED


# --------------------------------------------------------------------------- #
# ``already_applied`` apply-context flag (must match the guard exactly)         #
# --------------------------------------------------------------------------- #


async def _intelligence(db, *, student, job_id):
    return await student_intelligence_service.student_intelligence_for_job(
        db, principal=student, job_id=job_id, cv_id=None,
    )


async def test_already_applied_flag_true_while_active(db_session) -> None:
    _partner, student, job_id, sel = await _setup(db_session)
    await _apply(db_session, student=student, job_id=job_id, sel=sel)

    out = await _intelligence(db_session, student=student, job_id=job_id)
    assert out["apply_readiness"]["already_applied"] is True
    assert out["apply_readiness"]["ready"] is False
    assert out["apply_readiness"]["blocked_reason"] == "already_applied"


async def test_already_applied_flag_false_after_withdraw(db_session) -> None:
    _partner, student, job_id, sel = await _setup(db_session)
    first = await _apply(db_session, student=student, job_id=job_id, sel=sel)
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=uuid.UUID(first["id"]), ctx=CTX,
    )

    out = await _intelligence(db_session, student=student, job_id=job_id)
    # Withdrawn frees the slot -> the button must NOT be disabled as already-applied.
    assert out["apply_readiness"]["already_applied"] is False
    assert out["apply_readiness"]["blocked_reason"] != "already_applied"


async def test_already_applied_flag_false_after_reject(db_session) -> None:
    partner, student, job_id, sel = await _setup(db_session)
    first = await _apply(db_session, student=student, job_id=job_id, sel=sel)
    await decision_service.reject_application(
        db_session, principal=partner, application_id=uuid.UUID(first["id"]),
        reason="not_qualified", ctx=CTX,
    )

    out = await _intelligence(db_session, student=student, job_id=job_id)
    # Rejected also frees the slot (the domain allows re-apply); the flag must
    # agree with the guard so a disabled button never contradicts a re-appliable job.
    assert out["apply_readiness"]["already_applied"] is False
    assert out["apply_readiness"]["blocked_reason"] != "already_applied"
