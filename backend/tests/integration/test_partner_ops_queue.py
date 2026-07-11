"""Partner ops/todo queue completeness.

Proves the partner command-center ops queue surfaces the ACTIONABLE work an
enterprise recruiting team must not drop: an application awaiting triage, an offer
awaiting internal approval, and an approved offer awaiting send.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.analytics.application import partner_ops_dashboard_service as ops
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    offer_service,
)

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _applied(db):
    """Partner org + published job + a student who APPLIED (not yet reviewed)."""

    _pu, porg, admin = await make_org_with_admin(db, display_name="Ops Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)
    _su, student = await make_student(db, prefix="opsapplicant")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    return admin, uuid.UUID(app["id"])


def _todo(result: dict, key: str) -> dict | None:
    return next((t for t in result["todos"] if t["key"] == key), None)


async def test_applications_to_review_todo_surfaces_and_clears(db_session) -> None:
    admin, app_id = await _applied(db_session)

    result = await ops.get_partner_dashboard_ops(db_session, principal=admin)
    todo = _todo(result, "applications_to_review")
    assert todo is not None and todo["count"] >= 1 and todo["kind"] == "action"

    await decision_service.review_application(
        db_session, principal=admin, application_id=app_id, ctx=CTX
    )
    result2 = await ops.get_partner_dashboard_ops(db_session, principal=admin)
    assert _todo(result2, "applications_to_review") is None


async def test_offer_approve_then_send_todos(db_session) -> None:
    admin, app_id = await _applied(db_session)
    await decision_service.review_application(
        db_session, principal=admin, application_id=app_id, ctx=CTX
    )
    out = await offer_service.create_offer(
        db_session,
        principal=admin,
        application_id=app_id,
        ctx=CTX,
        position_title="Backend Engineer",
        expiry_date=_now() + timedelta(days=7),
        salary_amount=20_000_000,
        start_date=(_now() + timedelta(days=30)).date(),
    )
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db_session, principal=admin, offer_id=oid, ctx=CTX)

    # pending_approval -> offers_to_approve
    result = await ops.get_partner_dashboard_ops(db_session, principal=admin)
    approve_todo = _todo(result, "offers_to_approve")
    assert approve_todo is not None and approve_todo["count"] >= 1

    await offer_service.approve_offer(
        db_session, principal=admin, offer_id=oid, decision="approve", ctx=CTX
    )
    # approved -> offers_to_send (and no longer offers_to_approve)
    result2 = await ops.get_partner_dashboard_ops(db_session, principal=admin)
    assert _todo(result2, "offers_to_approve") is None
    send_todo = _todo(result2, "offers_to_send")
    assert send_todo is not None and send_todo["count"] >= 1
