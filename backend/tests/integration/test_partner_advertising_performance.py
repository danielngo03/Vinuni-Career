"""Partner campaign / advertising performance read (design spec §6 "Advertising").

Covers per-placement + per-campaign impressions / clicks / CTR / apply-starts /
spend aggregated from ``analytics_events`` (ad.* mirror) + the frozen placement
``price_amount``, the apply-time ``ad.apply_start`` attribution hook, RBAC
(partner + ``analytics:view_job_metrics``), and tenant isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.advertising.domain.models import AdPackage, SponsoredPlacement
from app.modules.analytics.application import advertising_performance_service as ad_perf
from app.modules.analytics.application import ingestion_service as analytics
from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, apply_service
from app.shared.exceptions import PermissionDeniedError
from sqlalchemy import select

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


async def _seed_placement(
    db, *, org_id: uuid.UUID, created_by: uuid.UUID, target_id: uuid.UUID, price="6000000.00"
) -> uuid.UUID:
    pkg = AdPackage(
        code=f"premium_{uuid.uuid4().hex[:6]}",
        name="Premium 30d",
        placement_type="both",
        price_amount=price,
        currency="VND",
        duration_days=30,
        grants_sponsored=True,
        grants_featured=True,
        is_active=True,
    )
    db.add(pkg)
    await db.flush()
    placement = SponsoredPlacement(
        org_id=org_id,
        created_by=created_by,
        target_type="job",
        target_id=target_id,
        placement_type="sponsored",
        package_id=pkg.id,
        price_amount=price,
        currency="VND",
        start_at=_now() - timedelta(days=1),
        end_at=_now() + timedelta(days=29),
        status="active",
        activated_at=_now(),
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement.id


async def _emit(db, *, event_type: str, placement_id: uuid.UUID, n: int) -> None:
    for _ in range(n):
        await analytics.record_event(
            db,
            event_type=event_type,
            aggregate_type="ad_placement",
            aggregate_id=placement_id,
            actor_type="guest",
        )
    await db.commit()


async def _setup(db, *, title="Sponsored Job"):
    _pu, porg, admin = await make_org_with_admin(db, display_name="Ad Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni, title=title)
    return porg, admin, uni, job_id


async def test_campaign_performance_aggregates_delivery_and_spend(db_session) -> None:
    porg, admin, _uni, job_id = await _setup(db_session)
    placement_id = await _seed_placement(
        db_session, org_id=porg.id, created_by=admin.user_id, target_id=job_id
    )
    await _emit(db_session, event_type="ad.impression", placement_id=placement_id, n=100)
    await _emit(db_session, event_type="ad.click", placement_id=placement_id, n=8)
    await _emit(db_session, event_type="ad.apply_start", placement_id=placement_id, n=2)

    data = await ad_perf.get_campaign_performance(db_session, principal=admin)

    assert len(data["campaigns"]) == 1
    c = data["campaigns"][0]
    assert c["placement_id"] == str(placement_id)
    assert c["impressions"] == 100
    assert c["clicks"] == 8
    assert c["apply_starts"] == 2
    assert c["ctr_pct"] == 8.0
    assert c["spend"] == 6000000.0
    assert c["currency"] == "VND"
    assert c["target_title"] == "Sponsored Job"
    assert c["status"] == "active"
    assert c["status_label"] and c["status_label"] != c["status"]

    totals = data["totals"]
    assert totals["campaigns"] == 1
    assert totals["impressions"] == 100
    assert totals["clicks"] == 8
    assert totals["apply_starts"] == 2
    assert totals["ctr_pct"] == 8.0
    assert totals["spend"] == 6000000.0


async def test_campaign_with_no_delivery_shows_zero_ctr_but_spend(db_session) -> None:
    porg, admin, _uni, job_id = await _setup(db_session)
    await _seed_placement(
        db_session, org_id=porg.id, created_by=admin.user_id, target_id=job_id
    )
    data = await ad_perf.get_campaign_performance(db_session, principal=admin)
    c = data["campaigns"][0]
    assert c["impressions"] == 0
    assert c["clicks"] == 0
    assert c["ctr_pct"] is None  # honest: no CTR without impressions
    assert c["spend"] == 6000000.0


async def test_apply_emits_ad_apply_start_attribution(db_session) -> None:
    porg, admin, _uni, job_id = await _setup(db_session)
    placement_id = await _seed_placement(
        db_session, org_id=porg.id, created_by=admin.user_id, target_id=job_id
    )
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )

    rows = (
        (
            await db_session.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.event_type == "ad.apply_start",
                    AnalyticsEvent.aggregate_id == placement_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].aggregate_type == "ad_placement"

    # And it now surfaces in the campaign performance apply_starts counter.
    data = await ad_perf.get_campaign_performance(db_session, principal=admin)
    assert data["campaigns"][0]["apply_starts"] == 1


async def test_apply_to_unsponsored_job_emits_no_attribution(db_session) -> None:
    _porg, _admin, _uni, job_id = await _setup(db_session)  # no placement seeded
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    count = (
        await db_session.execute(
            select(AnalyticsEvent).where(AnalyticsEvent.event_type == "ad.apply_start")
        )
    ).scalars().all()
    assert count == []


async def test_advertising_requires_analytics_grant(db_session) -> None:
    porg, admin, _uni, job_id = await _setup(db_session)
    await _seed_placement(db_session, org_id=porg.id, created_by=admin.user_id, target_id=job_id)
    _user, _membership, non_admin = await add_member(
        db_session, org=porg, permissions=[("jobs", "read"), ("advertising", "view")]
    )
    with pytest.raises(PermissionDeniedError):
        await ad_perf.get_campaign_performance(db_session, principal=non_admin)


async def test_advertising_wrong_persona_forbidden(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await ad_perf.get_campaign_performance(db_session, principal=student)


async def test_advertising_tenant_isolation(db_session) -> None:
    porg_a, admin_a, _uni, job_a = await _setup(db_session, title="Org A Job")
    await _seed_placement(db_session, org_id=porg_a.id, created_by=admin_a.user_id, target_id=job_a)

    _pu, _porg_b, admin_b = await make_org_with_admin(db_session, display_name="Org B")
    data_b = await ad_perf.get_campaign_performance(db_session, principal=admin_b)
    assert data_b["campaigns"] == []
    assert data_b["totals"]["spend"] == 0.0
