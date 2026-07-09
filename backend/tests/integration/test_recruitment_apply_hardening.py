"""Recruitment apply-flow hardening tests.

- **B-593** — a concurrent apply race (two requests with DIFFERENT idempotency keys
  hitting the ``(job, applicant)`` unique-active index) returns a clean ``409``
  (``DuplicateApplicationError``), never a raw ``500``.

(The former B-603 anonymous-apply CV redaction tests were removed with the
anonymous-apply flow — owner decision 2026-07-10.)
"""

from __future__ import annotations

import pytest
from app.modules.recruitment.application import apply_service
from app.modules.recruitment.application.errors import DuplicateApplicationError
from sqlalchemy.exc import IntegrityError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id


# --------------------------------------------------------------------------- #
# B-593 — concurrent apply race returns a clean 409 (not a 500)               #
# --------------------------------------------------------------------------- #


async def test_concurrent_apply_race_returns_409_not_500(db_session, monkeypatch) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    # A true race: both requests clear the in-transaction ``_active_duplicate``
    # pre-check, then the Postgres partial unique index ``uq_applications_active``
    # rejects the loser's INSERT with an IntegrityError. SQLite unit tests don't
    # carry that partial index, so we force the exact IntegrityError the DB would
    # raise on the application-insert flush (the FIRST flush in ``apply_to_job``).
    real_flush = db_session.flush
    state = {"calls": 0}

    async def flaky_flush(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise IntegrityError(
                "INSERT INTO applications ...",
                {},
                Exception("UNIQUE constraint failed: uq_applications_active"),
            )
        return await real_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", flaky_flush)

    with pytest.raises(DuplicateApplicationError) as exc:
        await apply_service.apply_to_job(
            db_session,
            principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel),
            ctx=CTX,
        )
    # Same clean 409 the sequential-duplicate path returns — never a raw 500.
    assert exc.value.details["reason"] == "duplicate_application"
    assert exc.value.http_status == 409
