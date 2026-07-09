"""B-546 dev seed: real ACTIVE sponsored placements + approved creatives.

Exercises ``scripts.seed_demo_marketplace._seed_sponsored_placements`` (the
seed-pipeline addition) directly against the test DB — not the full ``seed()``
orchestration (orgs/logos/messaging), just the new placement/creative slice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.modules.advertising.domain import lifecycle as ad_lifecycle
from app.modules.advertising.domain.creatives import CREATIVE_APPROVED
from app.modules.advertising.domain.models import (
    AdPackage,
    CampaignCreative,
    SponsoredPlacement,
)
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from scripts import seed_demo_marketplace as seed_mod
from sqlalchemy import select

from tests.org_utils import make_org_with_admin


async def _ensure_ad_package(db) -> None:
    """Tests build the schema via ``create_all`` (no migrations), so the
    ``sponsored_14d`` package migration-0017 normally seeds isn't present.
    """

    existing = (
        await db.execute(select(AdPackage).where(AdPackage.code == seed_mod._AD_PACKAGE_CODE))
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        AdPackage(
            code=seed_mod._AD_PACKAGE_CODE,
            name="Được tài trợ 14 ngày",
            placement_type="sponsored",
            price_amount="3000000.00",
            currency="VND",
            duration_days=14,
            grants_sponsored=True,
            grants_featured=False,
        )
    )
    await db.commit()


async def _make_job(db, *, org_id: uuid.UUID, poster_id: uuid.UUID, title: str) -> Job:
    job = Job(
        org_id=org_id,
        posted_by=poster_id,
        title=title,
        slug=f"seed-test-{uuid.uuid4().hex[:10]}",
        description="Test job.",
        employment_type="full_time",
        location_type="onsite",
        required_skills=["SQL"],
        salary_is_disclosed=False,
        status="active",
        published_at=datetime.now(UTC),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _make_event(db, *, org_id: uuid.UUID, creator_id: uuid.UUID, title: str) -> Event:
    now = datetime.now(UTC)
    event = Event(
        org_id=org_id,
        created_by=creator_id,
        title=title,
        slug=f"seed-test-event-{uuid.uuid4().hex[:10]}",
        description="Test event.",
        event_type="workshop",
        format="in_person",
        starts_at=now,
        ends_at=now,
        timezone="Asia/Ho_Chi_Minh",
        status="published",
        visibility="public",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def test_seed_creates_active_job_and_event_placements(db_session) -> None:
    await _ensure_ad_package(db_session)
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    job_a = await _make_job(db_session, org_id=org.id, poster_id=admin.user_id, title="Job A")
    job_b = await _make_job(db_session, org_id=org.id, poster_id=admin.user_id, title="Job B")
    event = await _make_event(db_session, org_id=org.id, creator_id=admin.user_id, title="Event A")

    result = await seed_mod._seed_sponsored_placements(
        db_session, jobs=[job_a, job_b], event=event, poster=admin.user_id
    )
    assert result == {"sponsored_placements_seeded": 3}

    placements = (
        (
            await db_session.execute(
                select(SponsoredPlacement).where(
                    SponsoredPlacement.moderation_note == seed_mod._AD_DEMO_MARKER
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(placements) == 3
    assert all(p.status == ad_lifecycle.ACTIVE for p in placements)

    creatives = (
        (
            await db_session.execute(
                select(CampaignCreative).where(
                    CampaignCreative.placement_id.in_([p.id for p in placements])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(creatives) == 3
    assert all(c.moderation_status == CREATIVE_APPROVED for c in creatives)
    assert {c.slot for c in creatives} == {"homepage_hero", "right_rail", "event_banner"}


async def test_seed_is_idempotent(db_session) -> None:
    await _ensure_ad_package(db_session)
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    job = await _make_job(db_session, org_id=org.id, poster_id=admin.user_id, title="Job A")

    first = await seed_mod._seed_sponsored_placements(
        db_session, jobs=[job], event=None, poster=admin.user_id
    )
    second = await seed_mod._seed_sponsored_placements(
        db_session, jobs=[job], event=None, poster=admin.user_id
    )
    assert first == {"sponsored_placements_seeded": 1}
    assert second == {"sponsored_placements_seeded": 0}

    count = (
        (
            await db_session.execute(
                select(SponsoredPlacement).where(
                    SponsoredPlacement.moderation_note == seed_mod._AD_DEMO_MARKER
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(count) == 1


async def test_seeded_job_placement_is_discoverable_via_inventory_facade(
    db_session,
) -> None:
    """The seeded row is real inventory, not just a raw DB fixture — confirm
    the actual public delivery facade (hero/rail + job-recommendations) sees it.
    """

    from app.modules.advertising.application import inventory_facade

    await _ensure_ad_package(db_session)
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    job = await _make_job(db_session, org_id=org.id, poster_id=admin.user_id, title="Job A")
    await seed_mod._seed_sponsored_placements(
        db_session, jobs=[job], event=None, poster=admin.user_id
    )

    active = await inventory_facade.list_active_sponsored(db_session, target_type="job")
    assert any(a.target_id == job.id for a in active)
