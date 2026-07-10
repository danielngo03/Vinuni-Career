"""Integration tests for the campaign-grade ad allocation engine (spec §7.0).

Covers the real allocation/distribution engine end to end: create → submit →
approve → serve; coarse targeting match; budget + pacing eligibility; the
organic/recommended/sponsored/university-curated separation invariant; the
mandatory NON-REMOVABLE paid disclosure; GPS/sensitive-targeting rejection; guest
privacy-safe segments; RBAC (partner create, university approve, cross-org 404,
partner cannot self-approve); and audit on every write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from app.modules.advertising.application import (
    allocation_service,
    campaign_moderation_service,
    campaign_reporting,
    campaign_service,
)
from app.modules.advertising.application.campaign_errors import (
    ForbiddenTargetingError,
    PaidDisclosureImmutableError,
    UnknownTargetingError,
)
from app.modules.advertising.domain import ad_slots as slots_vocab
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain.models import AdEventDaily, AdSlot
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #


async def _seed_slots(db) -> None:
    """Seed ad_slots (the migration data step runs only on Postgres)."""

    existing = set((await db.execute(select(AdSlot.code))).scalars().all())
    for spec in slots_vocab.SEED_SLOTS:
        if spec.code in existing:
            continue
        db.add(
            AdSlot(
                code=spec.code,
                surface=spec.surface,
                name_vi=spec.name_vi,
                name_en=spec.name_en,
                capacity=spec.capacity,
                max_sponsored_share=spec.max_sponsored_share,
                is_active=True,
            )
        )
    await db.commit()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _campaign_payload(**over) -> dict:
    base: dict = {
        "name": "Summer Internship Push",
        "objective": lifecycle.OBJ_APPLICATIONS,
        "surface": slots_vocab.SURFACE_DISCOVERY_FEED,
        "budget_amount": "1000000.00",
        "pacing": lifecycle.PACING_EVEN,
        "start_at": _now() - timedelta(hours=1),
        "end_at": _now() + timedelta(days=10),
        "targeting": {},
        "creative": {"headline": "Join Acme", "click_target": "/jobs"},
        "disclosure_confirmed": True,
    }
    base.update(over)
    return base


async def _active_campaign(db, partner, uni, **over) -> dict:
    """Create → submit → approve a campaign so it is serving (window open)."""

    created = await campaign_service.create_campaign(
        db, principal=partner, payload=_campaign_payload(**over), ctx=CTX
    )
    cid = uuid.UUID(created["id"])
    await campaign_service.submit_campaign(db, principal=partner, campaign_id=cid, ctx=CTX)
    approved = await campaign_moderation_service.approve_campaign(
        db, principal=uni, campaign_id=cid, ctx=CTX
    )
    return approved


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Create / submit / approve / serve                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_submit_approve_and_allocate(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner", display_name="Acme")
    _, _, uni = await make_org_with_admin(db, org_type="university", display_name="VinUni")

    approved = await _active_campaign(db, partner, uni)
    assert approved["status"] == lifecycle.ACTIVE  # inline activation (window open)

    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    assert result["inventory_class"] == "paid_sponsored"
    slot = result["slots"][0]
    assert slot["slot_code"] == "discovery_feed_sponsored"
    assert slot["filled"] == 1
    item = slot["items"][0]
    assert item["campaign_id"] == approved["id"]
    assert item["source"] == "sponsored"
    # NON-REMOVABLE paid disclosure is always present.
    assert item["disclosure"]["is_paid"] is True
    assert item["disclosure"]["is_removable"] is False
    assert item["disclosure"]["label"]
    # No budget/spend/targeting/org internals leak to the public projection.
    assert "budget_amount" not in item and "spent_amount" not in item
    assert "org_id" not in item and "targeting" not in item


@pytest.mark.asyncio
async def test_draft_or_pending_campaign_is_not_served(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    created = await campaign_service.create_campaign(
        db, principal=partner, payload=_campaign_payload(), ctx=CTX
    )
    # Not approved -> not active -> not eligible.
    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    assert result["slots"][0]["filled"] == 0
    assert created["status"] == lifecycle.DRAFT


# --------------------------------------------------------------------------- #
# Targeting match + privacy                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_allocation_respects_coarse_targeting(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")

    hanoi = await _active_campaign(
        db, partner, uni, name="Hanoi only", targeting={"locations": ["hanoi"]}
    )

    # Viewer in HCMC -> the Hanoi-targeted campaign does not match -> not served.
    hcmc_result = await allocation_service.allocate_surface(
        db,
        surface=slots_vocab.SURFACE_DISCOVERY_FEED,
        viewer_signals={"locations": ["ho_chi_minh"]},
    )
    assert hcmc_result["slots"][0]["filled"] == 0

    # Viewer in Hanoi -> matches.
    hanoi_result = await allocation_service.allocate_surface(
        db,
        surface=slots_vocab.SURFACE_DISCOVERY_FEED,
        viewer_signals={"locations": ["hanoi"]},
    )
    item = hanoi_result["slots"][0]["items"][0]
    assert item["campaign_id"] == hanoi["id"]
    assert item["match_reason"]["matched_dimensions"]["locations"] == ["hanoi"]


@pytest.mark.asyncio
async def test_forbidden_targeting_rejected(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    with pytest.raises(ForbiddenTargetingError):
        await campaign_service.create_campaign(
            db,
            principal=partner,
            payload=_campaign_payload(targeting={"gps": ["21.02,105.83"]}),
            ctx=CTX,
        )
    with pytest.raises(ForbiddenTargetingError):
        await campaign_service.create_campaign(
            db,
            principal=partner,
            payload=_campaign_payload(targeting={"gender": ["female"]}),
            ctx=CTX,
        )
    with pytest.raises(UnknownTargetingError):
        await campaign_service.create_campaign(
            db,
            principal=partner,
            payload=_campaign_payload(targeting={"favorite_food": ["pho"]}),
            ctx=CTX,
        )


@pytest.mark.asyncio
async def test_guest_segment_is_privacy_safe(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    await _active_campaign(db, partner, uni)

    result = await allocation_service.allocate_surface(
        db,
        surface=slots_vocab.SURFACE_DISCOVERY_FEED,
        # Forbidden signals mixed with coarse ones -> forbidden dropped default-deny.
        viewer_signals={
            "locations": ["hanoi"],
            "gps": "21.02,105.83",
            "email": "guest@example.com",
            "device_type": "mobile",
        },
    )
    seg = result["viewer_segment"]
    assert seg["locations"] == ["hanoi"]
    assert seg["device_classes"] == ["mobile"]
    # No forbidden key echoed back anywhere in the segment.
    flat = str(result)
    assert "21.02" not in flat and "guest@example.com" not in flat


# --------------------------------------------------------------------------- #
# Budget + pacing                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_budget_exhaustion_ends_and_unserves_campaign(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    # cpm default = 50000 -> 50/impression. budget 100 -> exhausted after 2.
    approved = await _active_campaign(db, partner, uni, budget_amount="100.00")
    cid = uuid.UUID(approved["id"])

    for _ in range(2):
        await allocation_service.record_delivery_event(
            db,
            campaign_id=cid,
            slot_code="discovery_feed_sponsored",
            event_type=campaign_reporting.EV_IMPRESSION,
        )

    refreshed = await campaign_service.get_campaign(db, principal=partner, campaign_id=cid)
    assert refreshed["status"] == lifecycle.ENDED  # auto-ended on budget cap
    assert await _audit_count(db, "advertising.campaign_budget_exhausted") == 1

    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    assert result["slots"][0]["filled"] == 0


@pytest.mark.asyncio
async def test_paced_out_campaign_is_excluded(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    # even pacing, big budget; force today's impressions to the daily cap.
    approved = await _active_campaign(
        db, partner, uni, budget_amount="500000.00", pacing=lifecycle.PACING_EVEN
    )
    cid = uuid.UUID(approved["id"])
    slot = (await db.execute(select(AdSlot).where(AdSlot.code == "discovery_feed_sponsored"))).scalar_one()
    # daily cap = ceil(goal/run_days); goal = 500000/50000*1000 = 10000 over ~10 days -> 1000/day.
    db.add(
        AdEventDaily(
            campaign_id=cid,
            slot_id=slot.id,
            surface=slots_vocab.SURFACE_DISCOVERY_FEED,
            event_date=date.today(),
            impressions=5000,  # well over the daily cap
            spend_amount=Decimal("0"),
        )
    )
    await db.commit()

    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    assert result["slots"][0]["filled"] == 0


# --------------------------------------------------------------------------- #
# Separation + disclosure                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_allocation_returns_only_sponsored_inventory(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    await _active_campaign(db, partner, uni)

    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    # Every served item is a DISTINCT sponsored source with a disclosure.
    for slot in result["slots"]:
        for item in slot["items"]:
            assert item["inventory_class"] == "paid_sponsored"
            assert item["source"] == "sponsored"
            assert item["disclosure"]["is_paid"] is True
            assert item["disclosure"]["is_removable"] is False


@pytest.mark.asyncio
async def test_paid_disclosure_cannot_be_relabelled_editorial(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    approved = await _active_campaign(db, partner, uni)
    cid = uuid.UUID(approved["id"])
    # Record manual payment -> campaign is now PAID inventory.
    await campaign_moderation_service.mark_paid(
        db, principal=uni, campaign_id=cid, payment_reference="BANK-REF-1", ctx=CTX
    )
    with pytest.raises(PaidDisclosureImmutableError):
        await campaign_moderation_service.set_disclosure_class(
            db, principal=uni, campaign_id=cid, disclosure_class="university_curated", ctx=CTX
        )


# --------------------------------------------------------------------------- #
# RBAC + audit                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cross_org_campaign_is_404(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner_a = await make_org_with_admin(db, org_type="partner", display_name="A")
    _, _, partner_b = await make_org_with_admin(db, org_type="partner", display_name="B")
    created = await campaign_service.create_campaign(
        db, principal=partner_a, payload=_campaign_payload(), ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await campaign_service.get_campaign(
            db, principal=partner_b, campaign_id=uuid.UUID(created["id"])
        )


@pytest.mark.asyncio
async def test_partner_cannot_approve_own_campaign(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    created = await campaign_service.create_campaign(
        db, principal=partner, payload=_campaign_payload(), ctx=CTX
    )
    cid = uuid.UUID(created["id"])
    await campaign_service.submit_campaign(db, principal=partner, campaign_id=cid, ctx=CTX)
    # A partner Admin's *:* still cannot self-approve (university-only gate).
    with pytest.raises(PermissionDeniedError):
        await campaign_moderation_service.approve_campaign(
            db, principal=partner, campaign_id=cid, ctx=CTX
        )


@pytest.mark.asyncio
async def test_writes_are_audited(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    await _active_campaign(db, partner, uni)
    assert await _audit_count(db, "advertising.campaign_created") == 1
    assert await _audit_count(db, "advertising.campaign_submitted") == 1
    assert await _audit_count(db, "advertising.campaign_approved") == 1


@pytest.mark.asyncio
async def test_university_can_disable_active_campaign(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    approved = await _active_campaign(db, partner, uni)
    cid = uuid.UUID(approved["id"])
    disabled = await campaign_moderation_service.admin_disable(
        db, principal=uni, campaign_id=cid, reason="policy", ctx=CTX
    )
    assert disabled["status"] == lifecycle.ENDED
    result = await allocation_service.allocate_surface(
        db, surface=slots_vocab.SURFACE_DISCOVERY_FEED, viewer_signals={}
    )
    assert result["slots"][0]["filled"] == 0


@pytest.mark.asyncio
async def test_delivery_events_roll_up_into_performance(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    approved = await _active_campaign(db, partner, uni, budget_amount="1000000.00")
    cid = uuid.UUID(approved["id"])
    for _ in range(3):
        await allocation_service.record_delivery_event(
            db, campaign_id=cid, slot_code="discovery_feed_sponsored",
            event_type=campaign_reporting.EV_IMPRESSION,
        )
    await allocation_service.record_delivery_event(
        db, campaign_id=cid, slot_code="discovery_feed_sponsored",
        event_type=campaign_reporting.EV_CLICK,
    )
    perf = await campaign_reporting.campaign_performance(db, campaign_id=cid)
    assert perf["impressions"] == 3
    assert perf["clicks"] == 1
    assert perf["ctr"] == round(1 / 3, 4)


@pytest.mark.asyncio
async def test_unknown_slot_event_is_404(db_session):
    db = db_session
    await _seed_slots(db)
    _, _, partner = await make_org_with_admin(db, org_type="partner")
    _, _, uni = await make_org_with_admin(db, org_type="university")
    approved = await _active_campaign(db, partner, uni)
    cid = uuid.UUID(approved["id"])
    # A slot from a different surface is not valid for this campaign -> 404.
    with pytest.raises(ResourceNotFoundError):
        await allocation_service.record_delivery_event(
            db, campaign_id=cid, slot_code="homepage_hero",
            event_type=campaign_reporting.EV_IMPRESSION,
        )
