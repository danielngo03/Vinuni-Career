"""Per-campaign advertising analytics read model (WS-13, Task P).

Covers the ``ad_placement_metrics_daily`` projection built from the privacy-safe
``discovery_events`` ledger:

- aggregation is correct (impressions / clicks / apply-starts per day + totals);
- CTR + cost-per-apply-start are derived correctly (frozen campaign price basis);
- the read is PARTNER-SCOPED (a cross-org partner gets a non-enumerable 404);
- the payload carries NO PII (no viewer/session/candidate id);
- the refresh + nightly sweep are idempotent.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.advertising.application import campaign_metrics_service as metrics
from app.modules.advertising.domain.metrics_models import AdPlacementMetricsDaily
from app.modules.advertising.domain.models import SponsoredPlacement
from app.modules.discovery.domain.models import DiscoveryEvent
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import func, select
from tests.org_utils import make_org_with_admin

_FORBIDDEN = [
    "session_id", "user_id", "candidate_id", "ip_address", "email", "user_agent",
    "openrouter", "confidence", "prompt_tokens",
]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _assert_no_pii(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


async def _partner(db, name: str):
    _u, _org, partner = await make_org_with_admin(db, display_name=name)
    return partner


async def _seed_active_placement(db, *, partner, price: str = "3000000.00") -> uuid.UUID:
    now = _now()
    placement = SponsoredPlacement(
        org_id=partner.org_id, created_by=partner.user_id, target_type="job",
        target_id=uuid.uuid4(), placement_type="sponsored", package_id=uuid.uuid4(),
        price_amount=price, currency="VND",
        start_at=now - timedelta(days=1), end_at=now + timedelta(days=13),
        status="active", disclosure_confirmed=True, paid_at=now, activated_at=now,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement.id


async def _seed_events(
    db, *, placement_id: uuid.UUID, day: datetime, spec: dict[str, int]
) -> None:
    """Insert ``spec`` = {event_type: count} sponsored events on ``day``."""

    for event_type, count in spec.items():
        for _ in range(count):
            db.add(
                DiscoveryEvent(
                    id=uuid.uuid4(),
                    event_type=event_type,
                    source_surface="homepage_sponsored",
                    target_type="job",
                    target_id=uuid.uuid4(),
                    placement_id=placement_id,
                    scope="session",
                    idempotency_key=uuid.uuid4().hex,
                    created_at=day,
                )
            )
    await db.commit()


# --------------------------------------------------------------------------- #
# Aggregation correctness                                                      #
# --------------------------------------------------------------------------- #


async def test_refresh_aggregates_events_per_day(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    pid = await _seed_active_placement(db_session, partner=partner)

    d1 = _now() - timedelta(days=1)
    d2 = _now()
    await _seed_events(
        db_session, placement_id=pid, day=d1,
        spec={"impression": 100, "click": 10, "apply_start": 2},
    )
    await _seed_events(
        db_session, placement_id=pid, day=d2,
        spec={"impression": 50, "click": 5, "apply_start": 3},
    )

    await metrics.refresh_placement(db_session, placement_id=pid, org_id=partner.org_id)
    await db_session.commit()

    rows = (
        await db_session.execute(
            select(AdPlacementMetricsDaily)
            .where(AdPlacementMetricsDaily.placement_id == pid)
            .order_by(AdPlacementMetricsDaily.metric_date.asc())
        )
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].impressions == 100 and rows[0].clicks == 10 and rows[0].apply_starts == 2
    assert rows[1].impressions == 50 and rows[1].clicks == 5 and rows[1].apply_starts == 3


async def test_placement_analytics_totals_ctr_and_cost_per_apply(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    pid = await _seed_active_placement(db_session, partner=partner, price="3000000.00")
    await _seed_events(
        db_session, placement_id=pid, day=_now(),
        spec={"impression": 200, "click": 20, "apply_start": 5},
    )

    out = await metrics.get_placement_analytics(
        db_session, principal=partner, placement_id=pid,
    )
    assert out["totals"]["impressions"] == 200
    assert out["totals"]["clicks"] == 20
    assert out["totals"]["apply_starts"] == 5
    # CTR = clicks / impressions = 10.0%.
    assert out["ctr_pct"] == 10.0
    # apply-start rate = apply_starts / impressions = 2.5%.
    assert out["apply_start_rate_pct"] == 2.5
    # Cost per apply-start = 3,000,000 / 5 = 600,000.
    assert out["cost_per_apply_start"] == "600000.00"
    assert out["currency"] == "VND"
    assert out["day_count"] == 1
    _assert_no_pii(out)


async def test_cost_per_apply_none_when_no_apply_starts(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    pid = await _seed_active_placement(db_session, partner=partner)
    await _seed_events(
        db_session, placement_id=pid, day=_now(), spec={"impression": 30, "click": 3},
    )
    out = await metrics.get_placement_analytics(
        db_session, principal=partner, placement_id=pid,
    )
    assert out["cost_per_apply_start"] is None
    assert out["ctr_pct"] == 10.0


# --------------------------------------------------------------------------- #
# Partner-scoped RBAC (cross-org -> 404)                                       #
# --------------------------------------------------------------------------- #


async def test_placement_analytics_is_partner_scoped(db_session) -> None:
    owner = await _partner(db_session, "Owner Co")
    other = await _partner(db_session, "Other Co")
    pid = await _seed_active_placement(db_session, partner=owner)
    await _seed_events(
        db_session, placement_id=pid, day=_now(), spec={"impression": 10},
    )
    # The owning org can read.
    out = await metrics.get_placement_analytics(
        db_session, principal=owner, placement_id=pid,
    )
    assert out["totals"]["impressions"] == 10
    # A different org's partner cannot even enumerate it -> 404, never 403.
    with pytest.raises(ResourceNotFoundError):
        await metrics.get_placement_analytics(
            db_session, principal=other, placement_id=pid,
        )


async def test_org_analytics_only_returns_own_org_campaigns(db_session) -> None:
    owner = await _partner(db_session, "Owner Co")
    other = await _partner(db_session, "Other Co")
    p_owner = await _seed_active_placement(db_session, partner=owner)
    p_other = await _seed_active_placement(db_session, partner=other)
    await _seed_events(
        db_session, placement_id=p_owner, day=_now(), spec={"impression": 40, "click": 4},
    )
    await _seed_events(
        db_session, placement_id=p_other, day=_now(), spec={"impression": 999},
    )
    await metrics.refresh_placement(db_session, placement_id=p_owner, org_id=owner.org_id)
    await metrics.refresh_placement(db_session, placement_id=p_other, org_id=other.org_id)
    await db_session.commit()

    out = await metrics.get_org_analytics(db_session, principal=owner)
    assert out["campaign_count"] == 1
    assert out["totals"]["impressions"] == 40
    assert {c["placement_id"] for c in out["campaigns"]} == {str(p_owner)}
    _assert_no_pii(out)


# --------------------------------------------------------------------------- #
# Idempotency (refresh + sweep)                                                #
# --------------------------------------------------------------------------- #


async def test_refresh_is_idempotent(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    pid = await _seed_active_placement(db_session, partner=partner)
    await _seed_events(
        db_session, placement_id=pid, day=_now(),
        spec={"impression": 12, "click": 2, "apply_start": 1},
    )
    await metrics.refresh_placement(db_session, placement_id=pid, org_id=partner.org_id)
    await db_session.commit()
    await metrics.refresh_placement(db_session, placement_id=pid, org_id=partner.org_id)
    await db_session.commit()

    total_rows = (
        await db_session.execute(
            select(func.count()).select_from(AdPlacementMetricsDaily).where(
                AdPlacementMetricsDaily.placement_id == pid
            )
        )
    ).scalar_one()
    assert total_rows == 1  # one (placement, date) row, never duplicated
    row = (
        await db_session.execute(
            select(AdPlacementMetricsDaily).where(
                AdPlacementMetricsDaily.placement_id == pid
            )
        )
    ).scalar_one()
    assert row.impressions == 12 and row.clicks == 2 and row.apply_starts == 1


async def test_sweep_refresh_recomputes_all_placements_with_events(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    pid = await _seed_active_placement(db_session, partner=partner)
    await _seed_events(
        db_session, placement_id=pid, day=_now(), spec={"impression": 7, "click": 1},
    )
    res1 = await metrics.sweep_refresh(db_session)
    assert res1["refreshed"] == 1 and res1["errors"] == 0
    # Re-tick converges to the same values (idempotent).
    res2 = await metrics.sweep_refresh(db_session)
    assert res2["refreshed"] == 1
    row = (
        await db_session.execute(
            select(AdPlacementMetricsDaily).where(
                AdPlacementMetricsDaily.placement_id == pid
            )
        )
    ).scalar_one()
    assert row.impressions == 7 and row.clicks == 1
