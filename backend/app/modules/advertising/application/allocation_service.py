"""The ad allocation / distribution engine (spec §7.0, owner decision 2026-07-10).

Given a public SURFACE + a viewer's COARSE, privacy-safe segment, the engine:

1. loads the surface's FINITE sponsored slots (``ad_slots``);
2. filters active, approved, in-budget, not-paced-out campaigns for that surface;
3. matches them against the viewer's coarse targeting attributes (location / major /
   career / work-mode / cohort / device) — NEVER GPS or a sensitive category;
4. ranks by targeting precision + fair pacing pressure + remaining budget, applies
   org-diversity anti-starvation, and fills each open PAID slot position;
5. records the auditable allocation decision (``ad_allocations``) with the coarse
   match reason + pacing state;
6. falls back to a VinUni-CURATED asset (labelled ``university_curated``) or leaves
   the slot empty — NEVER a fake/placeholder ad.

Hard invariants:
- The engine fills PAID slots ONLY. It never reorders or outranks organic /
  recommended inventory — those are selected by the ``discovery`` ranker on a
  separate path. Organic, recommended, sponsored, and university-curated inventory
  are returned as DISTINCT, distinctly-labelled sets.
- Every sponsored item carries the mandatory, NON-REMOVABLE paid disclosure. It is
  never stripped.
- No budget / spend / targeting / org internals reach the public projection — only
  the banner creative, the campaign name, the inventory class, and the disclosure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import campaign_presenters
from app.modules.advertising.application import campaign_reporting, inventory_facade
from app.modules.advertising.domain import ad_slots as slots_vocab
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain import pacing as pacing_math
from app.modules.advertising.domain import targeting as targeting_vocab
from app.modules.advertising.domain.models import AdAllocation, AdCampaign, AdSlot
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError

# Inventory-class labels the composing read-model uses to keep sources DISTINCT.
INVENTORY_ORGANIC = disclosure_vocab.ORGANIC
INVENTORY_RECOMMENDED = disclosure_vocab.RECOMMENDED
INVENTORY_SPONSORED = disclosure_vocab.PAID_SPONSORED
INVENTORY_UNIVERSITY_CURATED = disclosure_vocab.UNIVERSITY_CURATED


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _has_servable_creative(campaign: AdCampaign) -> bool:
    c = campaign.creative or {}
    return bool(c.get("headline") or c.get("image_ref"))


@dataclass(slots=True)
class _Eligible:
    campaign: AdCampaign
    match: targeting_vocab.TargetMatch
    pacing_state: pacing_math.PacingState


# --------------------------------------------------------------------------- #
# Slot inventory                                                              #
# --------------------------------------------------------------------------- #


async def list_surface_slots(session: AsyncSession, *, surface: str) -> list[AdSlot]:
    rows = (
        await session.execute(
            select(AdSlot)
            .where(AdSlot.surface == surface, AdSlot.is_active.is_(True))
            .order_by(AdSlot.code.asc())
        )
    ).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# Ranking + fair fill                                                         #
# --------------------------------------------------------------------------- #


def _rank_key(e: _Eligible) -> tuple:
    remaining = e.campaign.budget_amount - e.campaign.spent_amount
    return (
        -e.match.score,
        -pacing_math.pacing_pressure(e.pacing_state),
        -float(remaining),
        str(e.campaign.id),
    )


def _fair_fill(ranked: list[_Eligible], total_positions: int) -> list[_Eligible]:
    """Greedy fill with org-diversity anti-starvation (one org per pass first).

    First pass takes the best campaign of each distinct org (so a single advertiser
    cannot monopolize a surface while others are eligible); subsequent passes fill
    any remaining positions from the ranked remainder. Deterministic.
    """

    chosen: list[_Eligible] = []
    used_orgs: set[uuid.UUID] = set()
    remaining = list(ranked)

    while remaining and len(chosen) < total_positions:
        picked_index: int | None = None
        # Prefer the highest-ranked campaign whose org is not yet represented.
        for i, e in enumerate(remaining):
            if e.campaign.org_id not in used_orgs:
                picked_index = i
                break
        if picked_index is None:
            # All remaining orgs already represented — start a fresh diversity pass.
            used_orgs.clear()
            continue
        e = remaining.pop(picked_index)
        chosen.append(e)
        used_orgs.add(e.campaign.org_id)
    return chosen


# --------------------------------------------------------------------------- #
# Allocation                                                                  #
# --------------------------------------------------------------------------- #


async def allocate_surface(
    session: AsyncSession,
    *,
    surface: str,
    viewer_signals: dict | None = None,
    locale: str = "vi",
    now: datetime | None = None,
    persist: bool = True,
) -> dict:
    """Fill ``surface``'s sponsored slots for a coarse viewer segment.

    ``viewer_signals`` is arbitrary coarse input (query params + a discovery
    session's ``coarse_tags``); it is sanitized default-deny into a
    :class:`ViewerSegment` — a forbidden/sensitive signal can never enter the
    engine. Returns DISTINCT, labelled sponsored inventory only; organic /
    recommended selection stays on the discovery ranker's separate path.
    """

    if not slots_vocab.is_valid_surface(surface):
        raise ValidationFailedError(details={"field": "surface"})

    now = now or _now()
    viewer = targeting_vocab.sanitize_viewer_segment(viewer_signals)
    seg_key = targeting_vocab.segment_key(viewer)

    slots = await list_surface_slots(session, surface=surface)
    if not slots:
        return _empty_result(surface, seg_key, viewer, now)

    # Candidate active campaigns for this surface, inside their window.
    candidates = list(
        (
            await session.execute(
                select(AdCampaign).where(
                    AdCampaign.deleted_at.is_(None),
                    AdCampaign.status == lifecycle.ACTIVE,
                    AdCampaign.surface == surface,
                    AdCampaign.start_at <= now,
                    AdCampaign.end_at > now,
                )
            )
        ).scalars().all()
    )
    impressions_today = await campaign_reporting.impressions_today_bulk(
        session, campaign_ids=[c.id for c in candidates], now=now
    )

    eligible: list[_Eligible] = []
    for c in candidates:
        if not _has_servable_creative(c):
            continue
        state = pacing_math.compute_pacing_state(
            pacing=c.pacing,
            budget=c.budget_amount,
            spent=c.spent_amount,
            cpm=c.cpm_amount,
            start_at=_aware(c.start_at),
            end_at=_aware(c.end_at),
            impressions_today=impressions_today.get(c.id, 0),
        )
        if not state.eligible:
            continue  # budget exhausted OR paced-out for the day
        match = targeting_vocab.match_targeting(c.targeting, viewer)
        if not match.matched:
            continue  # targeting does not cover this coarse segment
        eligible.append(_Eligible(campaign=c, match=match, pacing_state=state))

    eligible.sort(key=_rank_key)

    total_positions = sum(max(0, s.capacity) for s in slots)
    winners = _fair_fill(eligible, total_positions)

    # Assign winners across slot positions (slot order stable), record the plan.
    result_slots: list[dict] = []
    winner_iter = iter(winners)
    allocated_rows: list[tuple[AdSlot, int, _Eligible]] = []
    filled_campaign_ids: set[uuid.UUID] = set()

    for s in slots:
        slot_items: list[dict] = []
        for position in range(max(0, s.capacity)):
            try:
                e = next(winner_iter)
            except StopIteration:
                break
            filled_campaign_ids.add(e.campaign.id)
            allocated_rows.append((s, position, e))
            slot_items.append(
                _public_item(e, slot=s, position=position, locale=locale)
            )
        fallback = None
        if not slot_items:
            fallback = _curated_fallback(surface, locale=locale)
        result_slots.append(
            {
                "slot_code": s.code,
                "slot_name": s.name_en if locale == "en" else s.name_vi,
                "capacity": s.capacity,
                "max_sponsored_share": s.max_sponsored_share,
                "filled": len(slot_items),
                "items": slot_items,
                "fallback": fallback,
            }
        )

    if persist:
        await _persist_allocations(
            session,
            seg_key=seg_key,
            surface=surface,
            slots=slots,
            allocated_rows=allocated_rows,
            now=now,
        )

    return {
        "surface": surface,
        "viewer_segment_key": seg_key,
        "viewer_segment": _segment_public(viewer),
        "generated_at": now.isoformat(),
        # Sponsored inventory is a DISTINCT, labelled source. Organic / recommended
        # come from the discovery ranker, never from here.
        "inventory_class": INVENTORY_SPONSORED,
        "slots": result_slots,
    }


def _empty_result(surface: str, seg_key: str, viewer, now: datetime) -> dict:
    return {
        "surface": surface,
        "viewer_segment_key": seg_key,
        "viewer_segment": _segment_public(viewer),
        "generated_at": now.isoformat(),
        "inventory_class": INVENTORY_SPONSORED,
        "slots": [],
    }


def _segment_public(viewer: targeting_vocab.ViewerSegment) -> dict:
    """Echo back ONLY the coarse dimensions the engine used (privacy-safe)."""

    return {
        "locations": sorted(viewer.locations),
        "majors": sorted(viewer.majors),
        "careers": sorted(viewer.careers),
        "work_modes": sorted(viewer.work_modes),
        "year_cohorts": sorted(viewer.year_cohorts),
        "device_classes": sorted(viewer.device_classes),
    }


def _public_item(e: _Eligible, *, slot: AdSlot, position: int, locale: str) -> dict:
    """Public sponsored-item projection — creative + non-removable disclosure only."""

    c = e.campaign
    return {
        "campaign_id": str(c.id),
        "slot_code": slot.code,
        "surface": c.surface,
        "position": position,
        "inventory_class": INVENTORY_SPONSORED,
        "source": "sponsored",
        "name": c.name,
        "objective": c.objective,
        "creative": campaign_presenters._public_creative(c.creative),
        "target_type": c.target_type,
        "target_id": str(c.target_id) if c.target_id else None,
        # Mandatory, NON-REMOVABLE paid disclosure — never stripped.
        "disclosure": disclosure_vocab.disclosure_payload(c.disclosure_class, locale=locale),
        # Coarse, non-PII reason (why this sponsored item was allocated here).
        "match_reason": e.match.reason,
    }


def _curated_fallback(surface: str, *, locale: str) -> dict | None:
    """VinUni-curated fallback for an unfilled slot (labelled curated; never paid).

    Only the homepage surface has a configured curated hero asset today; other
    surfaces hide the empty slot rather than fabricate an ad (spec §7.0 fallback).
    """

    if surface != slots_vocab.SURFACE_HOMEPAGE:
        return None
    return inventory_facade.curated_fallback(creative_vocab.SLOT_HOMEPAGE_HERO, locale=locale)


async def _persist_allocations(
    session: AsyncSession,
    *,
    seg_key: str,
    surface: str,
    slots: list[AdSlot],
    allocated_rows: list[tuple[AdSlot, int, _Eligible]],
    now: datetime,
) -> None:
    """Replace this (surface, segment) plan with the freshly-computed allocations.

    Delete-then-insert keeps ``ad_allocations`` reflecting the CURRENT plan and
    bounded (slots × observed segments). Best-effort: a persistence failure never
    breaks serving. Caller commits.
    """

    ttl = get_settings().advertising_allocation_ttl_seconds
    slot_ids = [s.id for s in slots]
    try:
        await session.execute(
            delete(AdAllocation).where(
                AdAllocation.slot_id.in_(slot_ids),
                AdAllocation.segment_key == seg_key,
            )
        )
        for slot, position, e in allocated_rows:
            session.add(
                AdAllocation(
                    campaign_id=e.campaign.id,
                    slot_id=slot.id,
                    surface=surface,
                    slot_code=slot.code,
                    segment_key=seg_key,
                    position=position,
                    match_reason=e.match.reason,
                    pacing_state=e.pacing_state.as_dict(),
                    allocated_at=now,
                    expires_at=now + timedelta(seconds=ttl),
                )
            )
        await session.commit()
    except Exception:  # noqa: BLE001 — serving must not fail on an audit-write error
        await session.rollback()


# --------------------------------------------------------------------------- #
# Delivery event recording (public, privacy-safe)                             #
# --------------------------------------------------------------------------- #


async def record_delivery_event(
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    slot_code: str,
    event_type: str,
    now: datetime | None = None,
) -> dict:
    """Record a privacy-safe delivery event (impression/click/apply-start/register).

    Public (guest-allowed) — carries NO PII/GPS/raw IP; it only bumps the
    ``ad_events`` aggregate. An impression also spends against the campaign budget
    and auto-ends the campaign when the budget is exhausted (the real budget cap).
    A campaign/slot mismatch or unknown id is a non-enumerable ``404``.
    """

    if event_type not in campaign_reporting.EVENT_TYPES:
        raise ValidationFailedError(details={"field": "event_type"})

    campaign = (
        await session.execute(
            select(AdCampaign).where(
                AdCampaign.id == campaign_id, AdCampaign.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise ResourceNotFoundError()

    slot = (
        await session.execute(
            select(AdSlot).where(
                AdSlot.code == slot_code,
                AdSlot.surface == campaign.surface,
                AdSlot.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if slot is None:
        raise ResourceNotFoundError()

    await campaign_reporting.record_event(
        session,
        campaign=campaign,
        slot_id=slot.id,
        event_type=event_type,
        now=now,
    )
    await session.commit()
    return {"status": "recorded", "event_type": event_type}
