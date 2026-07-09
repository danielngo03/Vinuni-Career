"""Partner recruiting-funnel analytics read (design spec §6 "Analytics").

Covers the funnel applied -> screened -> interview -> offer -> hired (unifying
``applications.status`` + ``candidate_stages.stage_type``), per-stage conversion +
pass rates (from ``candidate_stages.exit_kind``), time-to-hire / time-in-stage
medians with ``low_signal`` when sparse, plus RBAC (partner persona + the
``analytics:view_job_metrics`` grant) and tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.analytics.application import partner_recruiting_funnel_service as funnel_service
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    offer_service,
    stage_service,
)
from app.modules.recruitment.domain import offer as offer_domain
from app.shared.exceptions import PermissionDeniedError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _apply(db, *, student, job_id) -> uuid.UUID:
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    return uuid.UUID(app["id"])


async def _advance(db, *, admin, app_id, times: int) -> None:
    for _ in range(times):
        await stage_service.advance_application_stage(
            db, principal=admin, application_id=app_id, ctx=CTX
        )


async def _hire(db, *, admin, student, app_id) -> None:
    out = await offer_service.create_offer(
        db,
        principal=admin,
        application_id=app_id,
        ctx=CTX,
        position_title="Backend Engineer",
        expiry_date=_now() + timedelta(days=7),
    )
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db, principal=admin, offer_id=oid, ctx=CTX)
    await offer_service.approve_offer(
        db, principal=admin, offer_id=oid, decision="approve", ctx=CTX
    )
    await offer_service.send_offer(db, principal=admin, offer_id=oid, ctx=CTX)
    await offer_service.respond_offer(
        db, principal=student, offer_id=oid, decision=offer_domain.RESPOND_ACCEPTED, ctx=CTX
    )


async def _seed_funnel(db):
    """4 applied, 4 screened, 3 interview, 2 offer, 1 hired for one partner org."""

    _pu, porg, admin = await make_org_with_admin(db, display_name="Funnel Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)

    students = []
    app_ids = []
    for i in range(4):
        _su, student = await make_student(db, prefix=f"cand{i}")
        students.append(student)
        app_ids.append(await _apply(db, student=student, job_id=job_id))

    # Review all 4 -> screening stage row (screened=4).
    for app_id in app_ids:
        await decision_service.review_application(
            db, principal=admin, application_id=app_id, ctx=CTX
        )

    # A, B, C advance screening -> interview (interview reached=3). D stays.
    await _advance(db, admin=admin, app_id=app_ids[0], times=1)
    await _advance(db, admin=admin, app_id=app_ids[1], times=1)
    await _advance(db, admin=admin, app_id=app_ids[2], times=1)
    # A, B advance interview -> offer (offer reached=2). C stays.
    await _advance(db, admin=admin, app_id=app_ids[0], times=1)
    await _advance(db, admin=admin, app_id=app_ids[1], times=1)
    # A hired (offer accepted). B stays at offer.
    await _hire(db, admin=admin, student=students[0], app_id=app_ids[0])

    return porg, admin


async def test_funnel_counts_and_conversion(db_session) -> None:
    _porg, admin = await _seed_funnel(db_session)

    data = await funnel_service.get_recruiting_funnel(db_session, principal=admin)

    counts = {row["stage"]: row["count"] for row in data["funnel"]}
    assert counts == {"applied": 4, "screened": 4, "interview": 3, "offer": 2, "hired": 1}

    conv = {row["stage"]: row["conversion_from_prev_pct"] for row in data["funnel"]}
    assert conv["applied"] is None
    assert conv["screened"] == 100.0
    assert conv["interview"] == 75.0
    assert conv["offer"] == pytest.approx(66.7, abs=0.1)
    assert conv["hired"] == 50.0

    # Localized labels present, no raw enum codes leaked as the display string.
    assert all(row["label"] and row["label"] != row["stage"] for row in data["funnel"])


async def test_stage_outcomes_pass_rates(db_session) -> None:
    _porg, admin = await _seed_funnel(db_session)
    data = await funnel_service.get_recruiting_funnel(db_session, principal=admin)

    outcomes = {row["stage_type"]: row for row in data["stage_outcomes"]}
    assert outcomes["screening"]["entered"] == 4
    assert outcomes["screening"]["advanced"] == 3
    assert outcomes["screening"]["active"] == 1
    assert outcomes["screening"]["pass_rate_pct"] == 75.0

    assert outcomes["interview"]["entered"] == 3
    assert outcomes["interview"]["advanced"] == 2
    assert outcomes["interview"]["active"] == 1

    assert outcomes["offer"]["entered"] == 2
    assert outcomes["offer"]["advanced"] == 1  # hired counts as advanced
    assert outcomes["offer"]["active"] == 1


async def test_time_metrics_low_signal_when_sparse(db_session) -> None:
    _porg, admin = await _seed_funnel(db_session)
    data = await funnel_service.get_recruiting_funnel(db_session, principal=admin)

    tth = data["time_to_hire"]
    assert tth["sample_size"] == 1
    assert tth["low_signal"] is True
    assert tth["median_days"] is not None
    assert sum(b["count"] for b in tth["buckets"]) == 1

    tis = {row["stage_type"]: row for row in data["time_in_stage"]}
    # screening closed 3 times (A,B,C advanced out) -> sample_size 3, low_signal.
    assert tis["screening"]["sample_size"] == 3
    assert tis["screening"]["low_signal"] is True


async def test_empty_org_returns_zero_funnel(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="Empty Co")
    data = await funnel_service.get_recruiting_funnel(db_session, principal=admin)
    assert all(row["count"] == 0 for row in data["funnel"])
    assert data["stage_outcomes"] == []
    assert data["time_to_hire"]["sample_size"] == 0
    assert data["time_to_hire"]["low_signal"] is True


async def test_funnel_requires_analytics_grant(db_session) -> None:
    _porg, _admin = await _seed_funnel(db_session)
    _pu, porg2, _admin2 = await make_org_with_admin(db_session, display_name="Grantless Co")
    _user, _membership, non_admin = await add_member(
        db_session, org=porg2, permissions=[("jobs", "read"), ("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await funnel_service.get_recruiting_funnel(db_session, principal=non_admin)


async def test_funnel_wrong_persona_forbidden(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await funnel_service.get_recruiting_funnel(db_session, principal=student)


async def test_funnel_tenant_isolation(db_session) -> None:
    _porg_a, _admin_a = await _seed_funnel(db_session)
    # A second org with the analytics grant sees only its own (empty) funnel.
    _pu, porg_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    _user, _membership, granted_b = await add_member(
        db_session,
        org=porg_b,
        permissions=[("analytics", "view_job_metrics")],
    )
    data_b = await funnel_service.get_recruiting_funnel(db_session, principal=granted_b)
    assert all(row["count"] == 0 for row in data_b["funnel"])
