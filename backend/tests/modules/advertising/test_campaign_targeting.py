"""Sponsored-placement audience targeting (WS-13, Task P).

Covers the relevance-filtering win + the trust invariants it must NEVER regress:

- a validated targeting descriptor is persisted in ``sponsored_placements.settings``
  and REJECTS a forbidden PII/sensitive dimension (reusing the discovery
  forbidden-signal allowlist);
- ``inventory_facade.list_active_sponsored`` filters paid slots to a MATCHING
  viewer, EXCLUDES a contradicting viewer, and ranks a matched placement ahead of
  a broad one;
- ``ranking_service`` wires targeting into the paid slots WITHOUT reordering or
  bleeding into the organic stream (organic subsequence preserved);
- paid disclosure stays non-removable and paid->editorial relabel stays blocked on
  a targeted placement;
- a university-restricted descriptor is partner-immutable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.advertising.application import (
    inventory_facade,
    moderation_service,
    placement_service,
)
from app.modules.advertising.application.errors import (
    InvalidTargetingFieldError,
    PaidDisclosureImmutableError,
)
from app.modules.advertising.domain import targeting as ad_targeting
from app.modules.advertising.domain.models import AdPackage, SponsoredPlacement
from app.modules.discovery.application import ranking_service
from app.modules.discovery.domain import ranking
from app.shared.permissions import GUEST
from sqlalchemy import select
from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _seed_package(db) -> AdPackage:
    pkg = AdPackage(
        code="sponsored_14d", name="Tài trợ 14 ngày", placement_type="sponsored",
        price_amount="3000000.00", currency="VND", duration_days=14,
        grants_sponsored=True, grants_featured=False, is_active=True,
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return pkg


async def _seed_active_sponsored(
    db, *, partner, target_id: uuid.UUID, targeting: dict | None = None
) -> uuid.UUID:
    now = _now()
    settings = {"targeting": targeting} if targeting is not None else {}
    placement = SponsoredPlacement(
        org_id=partner.org_id, created_by=partner.user_id, target_type="job",
        target_id=target_id, placement_type="sponsored", package_id=uuid.uuid4(),
        price_amount="3000000.00", currency="VND",
        start_at=now - timedelta(days=1), end_at=now + timedelta(days=13),
        status="active", disclosure_confirmed=True, paid_at=now, activated_at=now,
        settings=settings,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement.id


async def _university(db):
    _u, _org, uni = await make_org_with_admin(db, org_type="university")
    return uni


async def _partner(db, name: str):
    _u, _org, partner = await make_org_with_admin(db, display_name=name)
    return partner


# --------------------------------------------------------------------------- #
# (a) Validation: forbidden dimension rejected                                 #
# --------------------------------------------------------------------------- #


async def test_create_placement_rejects_forbidden_targeting_dimension(db_session) -> None:
    pkg = await _seed_package(db_session)
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Role"
    )

    with pytest.raises(InvalidTargetingFieldError) as exc:
        await placement_service.create_placement(
            db_session, principal=partner, ctx=CTX,
            payload={
                "target_type": "job", "target_id": job_id,
                "placement_type": "sponsored", "package_id": pkg.id,
                "start_at": _now(), "disclosure_confirmed": True,
                # 'gender' is a forbidden sensitive category in the discovery
                # allowlist — targeting must never be allowed to use it.
                "targeting": {"mode": "manual", "dimensions": {"gender": ["male"]}},
            },
        )
    assert exc.value.details["reason"] == "forbidden_targeting_dimension"


async def test_partner_cannot_set_university_restricted_mode(db_session) -> None:
    pkg = await _seed_package(db_session)
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Role"
    )
    with pytest.raises(InvalidTargetingFieldError):
        await placement_service.create_placement(
            db_session, principal=partner, ctx=CTX,
            payload={
                "target_type": "job", "target_id": job_id,
                "placement_type": "sponsored", "package_id": pkg.id,
                "start_at": _now(), "disclosure_confirmed": True,
                "targeting": {"mode": "university_restricted", "dimensions": {}},
            },
        )


async def test_create_placement_persists_valid_targeting(db_session) -> None:
    pkg = await _seed_package(db_session)
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Role"
    )
    created = await placement_service.create_placement(
        db_session, principal=partner, ctx=CTX,
        payload={
            "target_type": "job", "target_id": job_id,
            "placement_type": "sponsored", "package_id": pkg.id,
            "start_at": _now(), "disclosure_confirmed": True,
            "targeting": {
                "mode": "manual",
                "dimensions": {"industry": ["Finance"], "work_mode": ["remote"]},
            },
        },
    )
    assert created["targeting"]["mode"] == "manual"
    # Values are normalized (lowercased) + allowlist-clean.
    assert created["targeting"]["dimensions"]["industry"] == ["finance"]
    assert created["targeting"]["dimensions"]["work_mode"] == ["remote"]


# --------------------------------------------------------------------------- #
# (a) inventory_facade filters paid slots to the viewer                        #
# --------------------------------------------------------------------------- #


async def test_list_active_sponsored_filters_paid_slots_to_matching_viewer(
    db_session,
) -> None:
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    fin_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Finance role"
    )
    health_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Health role"
    )
    await _seed_active_sponsored(
        db_session, partner=partner, target_id=fin_job,
        targeting={"mode": "manual", "dimensions": {"industry": ["finance"]}},
    )
    await _seed_active_sponsored(
        db_session, partner=partner, target_id=health_job,
        targeting={"mode": "manual", "dimensions": {"industry": ["healthcare"]}},
    )

    fin_viewer = ad_targeting.ViewerSignals(
        persona="student", locale="vi", industries=frozenset({"finance"})
    )
    matched = await inventory_facade.list_active_sponsored(
        db_session, target_type="job", limit=10, viewer=fin_viewer
    )
    matched_ids = {a.target_id for a in matched}
    assert fin_job in matched_ids          # matching audience -> shown
    assert health_job not in matched_ids   # contradicting audience -> excluded

    # A viewer with NO industry signal cannot be excluded on that dimension: both
    # remain eligible (indeterminate never over-suppresses).
    blank_viewer = ad_targeting.ViewerSignals(persona="student", locale="vi")
    both = await inventory_facade.list_active_sponsored(
        db_session, target_type="job", limit=10, viewer=blank_viewer
    )
    assert {a.target_id for a in both} == {fin_job, health_job}


async def test_targeted_match_ranks_ahead_of_broad(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    broad_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Broad role"
    )
    targeted_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Targeted role"
    )
    # Broad placement activated LATER (newer) so recency alone would rank it first.
    await _seed_active_sponsored(db_session, partner=partner, target_id=broad_job)
    await _seed_active_sponsored(
        db_session, partner=partner, target_id=targeted_job,
        targeting={"mode": "manual", "dimensions": {"role_family": ["data_ai"]}},
    )
    viewer = ad_targeting.ViewerSignals(
        persona="student", locale="vi", role_families=frozenset({"data_ai"})
    )
    # Only one slot: the positively-matched placement wins it over the newer broad one.
    top = await inventory_facade.list_active_sponsored(
        db_session, target_type="job", limit=1, viewer=viewer
    )
    assert len(top) == 1
    assert top[0].target_id == targeted_job


# --------------------------------------------------------------------------- #
# (d) ranking: paid slots targeted, organic stream NOT reordered               #
# --------------------------------------------------------------------------- #


async def _backdate(db, job_id: uuid.UUID, *, days: int) -> None:
    from app.modules.opportunities.domain.models import Job

    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.published_at = _now() - timedelta(days=days)
    db.add(job)
    await db.commit()


async def test_ranking_targets_paid_slot_without_reordering_organic(db_session) -> None:
    uni = await _university(db_session)
    pa = await _partner(db_session, "Org A")
    pb = await _partner(db_session, "Org B")
    pc = await _partner(db_session, "Org C")
    a = await publish_job(db_session, partner_principal=pa, uni_principal=uni, title="Job A")
    b = await publish_job(db_session, partner_principal=pb, uni_principal=uni, title="Job B")
    c = await publish_job(db_session, partner_principal=pc, uni_principal=uni, title="Job C")
    await _backdate(db_session, a, days=1)
    await _backdate(db_session, b, days=2)
    await _backdate(db_session, c, days=3)

    pf = await _partner(db_session, "Fin Co")
    ph = await _partner(db_session, "Health Co")
    fin_job = await publish_job(
        db_session, partner_principal=pf, uni_principal=uni, title="Sponsored Finance"
    )
    health_job = await publish_job(
        db_session, partner_principal=ph, uni_principal=uni, title="Sponsored Health"
    )
    fin_placement = await _seed_active_sponsored(
        db_session, partner=pf, target_id=fin_job,
        targeting={"mode": "manual", "dimensions": {"industry": ["finance"]}},
    )
    await _seed_active_sponsored(
        db_session, partner=ph, target_id=health_job,
        targeting={"mode": "manual", "dimensions": {"industry": ["healthcare"]}},
    )

    # Guest whose coarse signals say "finance": only the finance paid slot fills.
    out = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags={"industries": ["finance"]}, limit=20
    )
    items = out["items"]
    sponsored = [it for it in items if it["source"] == ranking.SOURCE_SPONSORED]
    sponsored_ids = {it["id"] for it in sponsored}
    assert sponsored_ids == {str(fin_job)}                # matched fills the slot
    assert str(health_job) not in sponsored_ids           # contradicting excluded
    sp = sponsored[0]
    assert sp["placement_id"] == str(fin_placement)
    # Paid disclosure is present + NON-REMOVABLE (trust invariant preserved).
    assert sp["sponsored_disclosure"]["is_paid"] is True
    assert sp["sponsored_disclosure"]["is_removable"] is False

    # Organic stream keeps its EXACT recency subsequence A, B, C (never reordered
    # by the sponsored targeting).
    organic_abc = [
        it["id"] for it in items
        if it["source"] != ranking.SOURCE_SPONSORED
        and it["id"] in {str(a), str(b), str(c)}
    ]
    assert organic_abc == [str(a), str(b), str(c)]
    # A sponsored job never also appears in the organic stream.
    assert str(fin_job) not in [
        it["id"] for it in items if it["source"] != ranking.SOURCE_SPONSORED
    ]


# --------------------------------------------------------------------------- #
# (d) trust invariants: targeting never weakens disclosure                     #
# --------------------------------------------------------------------------- #


async def test_targeting_does_not_weaken_paid_disclosure(db_session) -> None:
    pkg = await _seed_package(db_session)
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Role"
    )
    created = await placement_service.create_placement(
        db_session, principal=partner, ctx=CTX,
        payload={
            "target_type": "job", "target_id": job_id,
            "placement_type": "sponsored", "package_id": pkg.id,
            "start_at": _now(), "disclosure_confirmed": True,
            "targeting": {"mode": "manual", "dimensions": {"industry": ["finance"]}},
        },
    )
    pid = uuid.UUID(created["id"])
    # Submit + freeze price so the placement is PAID inventory.
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="REF-1", ctx=CTX,
    )
    # Paid inventory can NEVER be relabeled to an editorial/curated class.
    with pytest.raises(PaidDisclosureImmutableError):
        await moderation_service.set_disclosure_class(
            db_session, principal=uni, placement_id=pid,
            disclosure_class="university_curated", ctx=CTX,
        )
    # Disclosure stays paid + non-removable.
    detail = await placement_service.get_placement(
        db_session, principal=partner, placement_id=pid,
    )
    assert detail["disclosure"]["is_paid"] is True
    assert detail["disclosure"]["is_removable"] is False
    assert detail["targeting"]["dimensions"]["industry"] == ["finance"]


async def test_university_restricted_targeting_is_partner_immutable(db_session) -> None:
    pkg = await _seed_package(db_session)
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Role"
    )
    created = await placement_service.create_placement(
        db_session, principal=partner, ctx=CTX,
        payload={
            "target_type": "job", "target_id": job_id,
            "placement_type": "sponsored", "package_id": pkg.id,
            "start_at": _now(), "disclosure_confirmed": True,
        },
    )
    pid = uuid.UUID(created["id"])
    # University locks the audience (university_restricted).
    restricted = await moderation_service.set_placement_targeting(
        db_session, principal=uni, placement_id=pid,
        targeting={
            "mode": "university_restricted",
            "dimensions": {"student_segment": ["student"]},
        },
        ctx=CTX,
    )
    assert restricted["targeting"]["mode"] == "university_restricted"

    # The partner may no longer edit the targeting.
    with pytest.raises(InvalidTargetingFieldError) as exc:
        await placement_service.update_placement(
            db_session, principal=partner, placement_id=pid, ctx=CTX,
            payload={"targeting": {"mode": "manual", "dimensions": {}}},
        )
    assert exc.value.details["reason"] == "restricted_by_university"
