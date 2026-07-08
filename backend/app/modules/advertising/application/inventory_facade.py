"""Read facade: currently-LIVE sponsored inventory for public delivery surfaces.

The ``discovery`` ranker and the ``marketplace`` overview need to know which
targets are *actively sponsored right now* (to fill the defined sponsored slots
and the homepage hero/banner), but must NOT import the ``SponsoredPlacement`` ORM
across module boundaries. This facade is the single allowed surface: it returns a
PII-free :class:`ActiveSponsoredItem` DTO list plus the mandatory, non-removable
disclosure label.

"Live" here is stricter than the ``status == active`` flag alone: a placement
counts only when it is ``active``, not soft-deleted, grants the *sponsored*
class, and ``now`` is inside ``[start_at, end_at)``. The sponsored selection only
ever *fills paid slots* — it never reorders organic relevance (that rule lives in
the ranker). The disclosure label is always present and never optional.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import presenters
from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import CampaignCreative, SponsoredPlacement


@dataclass(frozen=True, slots=True)
class ActiveSponsoredItem:
    """A live sponsored placement reference (no spend/PII internals exposed)."""

    placement_id: uuid.UUID
    org_id: uuid.UUID
    target_type: str  # job | event
    target_id: uuid.UUID
    placement_type: str  # sponsored | featured | both
    disclosure_class: str = disclosure_vocab.DEFAULT_DISCLOSURE_CLASS


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def disclosure(
    *, disclosure_class: str = disclosure_vocab.PAID_SPONSORED, locale: str = "vi"
) -> dict:
    """Polished public disclosure for an inventory class (spec §4/§7).

    Keyed by ``disclosure_class``: ``paid_sponsored`` is the non-removable PAID
    label; ``university_curated`` / ``strategic_partner`` / ``featured`` are
    truthful editorial/partnership labels (never presented as paid). Backward
    compatible: ``code``/``is_sponsored`` are retained for existing consumers.
    """

    payload = disclosure_vocab.disclosure_payload(disclosure_class, locale=locale)
    payload["code"] = disclosure_class
    return payload


def disclosure_for_placement(placement: SponsoredPlacement, *, locale: str) -> dict:
    return disclosure(disclosure_class=placement.disclosure_class, locale=locale)


async def approved_creative_for_slot(
    session: AsyncSession,
    *,
    placement_id: uuid.UUID,
    slot: str,
    now: datetime | None = None,
    locale: str = "vi",
) -> dict | None:
    """The live, APPROVED creative for ``placement_id`` in ``slot`` (or ``None``).

    Returns the safe creative projection (``image_url`` is the public serve route,
    never a storage key). Window-checked so a not-yet/past creative is skipped.
    """

    now = now or _now()
    rows = (
        await session.execute(
            select(CampaignCreative)
            .where(
                CampaignCreative.placement_id == placement_id,
                CampaignCreative.slot == slot,
                CampaignCreative.deleted_at.is_(None),
                CampaignCreative.moderation_status
                == creative_vocab.CREATIVE_APPROVED,
            )
            .order_by(CampaignCreative.created_at.desc())
        )
    ).scalars().all()
    for c in rows:
        if c.start_at is not None and now < _aware(c.start_at):
            continue
        if c.end_at is not None and now >= _aware(c.end_at):
            continue
        return presenters.creative(c, locale=locale)
    return None


# Static curated fallback alt/click-target per primary slot (the IMAGE comes from
# config so ops can point it at a ``frontend/public`` asset; spec §5).
_CURATED_FALLBACK_META: dict[str, dict] = {
    creative_vocab.SLOT_HOMEPAGE_HERO: {
        "alt": {
            "vi": "Trung tâm Hướng nghiệp VinUni",
            "en": "VinUni Career Center",
        },
        "click_target": "/companies",
    },
    creative_vocab.SLOT_RIGHT_RAIL: {
        "alt": {
            "vi": "Khám phá cơ hội tại VinUni",
            "en": "Explore opportunities at VinUni",
        },
        "click_target": "/jobs",
    },
}


def curated_fallback(slot: str, *, locale: str = "vi") -> dict | None:
    """VinUni-curated fallback banner for a primary slot, or ``None`` if unset.

    Used when NO active partner creative exists for the slot (spec §5/§6). The
    image is a static ``frontend/public`` asset configured per environment; when
    unconfigured no banner is fabricated. Always labelled ``university_curated``
    — NEVER paid.
    """

    settings = get_settings()
    image = {
        creative_vocab.SLOT_HOMEPAGE_HERO: settings.marketplace_hero_fallback_image,
        creative_vocab.SLOT_RIGHT_RAIL: settings.marketplace_rail_fallback_image,
    }.get(slot, "")
    if not image:
        return None
    meta = _CURATED_FALLBACK_META.get(slot, {})
    alt = meta.get("alt", {}).get(locale) or meta.get("alt", {}).get("vi")
    return {
        "placement_id": None,
        "slot": slot,
        "source": "vinuni_curated",
        "job": None,
        "creative": {
            "image_url": image,
            "alt": alt,
            "focal_point": {"x": 0.5, "y": 0.5},
            "click_target": meta.get("click_target"),
        },
        "disclosure": disclosure(
            disclosure_class=disclosure_vocab.UNIVERSITY_CURATED, locale=locale
        ),
    }


async def list_active_sponsored(
    session: AsyncSession,
    *,
    target_type: str = lifecycle.TARGET_JOB,
    now: datetime | None = None,
    limit: int = 10,
    exclude_placement_ids: set[uuid.UUID] | None = None,
) -> list[ActiveSponsoredItem]:
    """Live sponsored placements for ``target_type``, newest activation first.

    Filters to ``status == active``, not soft-deleted, *grants sponsored*, and
    ``start_at <= now < end_at``. One placement per row; the caller dedupes by
    target if the same target carries several placements. Read-only (no commit).

    ``exclude_placement_ids`` drops placements a frequency cap (owned by the
    ``discovery`` module — see ``frequency_cap.over_capped_placements``) has
    already decided this viewer has seen enough times. Excluded slots are left
    unfilled, never backfilled with organic content (hide-if-empty).
    """

    now = now or _now()
    stmt = (
        select(SponsoredPlacement)
        .where(
            SponsoredPlacement.deleted_at.is_(None),
            SponsoredPlacement.status == lifecycle.ACTIVE,
            SponsoredPlacement.target_type == target_type,
            SponsoredPlacement.start_at <= now,
            SponsoredPlacement.end_at > now,
        )
        .order_by(
            SponsoredPlacement.activated_at.desc().nullslast(),
            SponsoredPlacement.id.desc(),
        )
        .limit(max(limit, 0) * 2)  # over-fetch a little; window re-checked below
    )
    rows = list((await session.execute(stmt)).scalars().all())

    out: list[ActiveSponsoredItem] = []
    seen_targets: set[uuid.UUID] = set()
    for p in rows:
        # Defensive re-check against (possibly naive) stored bounds; and only the
        # sponsored class fills sponsored slots (a featured-only placement does not).
        if not (_aware(p.start_at) <= now < _aware(p.end_at)):
            continue
        if not lifecycle.grants_sponsored(p.placement_type):
            continue
        if exclude_placement_ids and p.id in exclude_placement_ids:
            continue
        if p.target_id in seen_targets:
            continue
        seen_targets.add(p.target_id)
        out.append(
            ActiveSponsoredItem(
                placement_id=p.id,
                org_id=p.org_id,
                target_type=p.target_type,
                target_id=p.target_id,
                placement_type=p.placement_type,
                disclosure_class=p.disclosure_class,
            )
        )
        if len(out) >= limit:
            break
    return out


async def is_target_sponsored_now(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    """True iff ``target_id`` carries a currently-LIVE sponsored placement.

    Read-only single-target check used by cross-module attribution (e.g. the
    ``analytics`` read models labeling a job-metrics row's traffic ``source`` as
    ``sponsored``). Reuses the same "live" predicate as :func:`list_active_sponsored`
    instead of re-querying ``SponsoredPlacement`` from another module.
    """

    now = now or _now()
    stmt = select(SponsoredPlacement.id).where(
        SponsoredPlacement.deleted_at.is_(None),
        SponsoredPlacement.status == lifecycle.ACTIVE,
        SponsoredPlacement.target_type == target_type,
        SponsoredPlacement.target_id == target_id,
        SponsoredPlacement.start_at <= now,
        SponsoredPlacement.end_at > now,
    )
    row = (await session.execute(stmt)).first()
    return row is not None


async def count_active_sponsored(
    session: AsyncSession, *, now: datetime | None = None
) -> int:
    """Count of live sponsored placements across job + event targets (health)."""

    jobs = await list_active_sponsored(
        session, target_type=lifecycle.TARGET_JOB, now=now, limit=1000
    )
    events = await list_active_sponsored(
        session, target_type=lifecycle.TARGET_EVENT, now=now, limit=1000
    )
    return len(jobs) + len(events)


async def count_campaigns_by_status_for_org(
    session: AsyncSession, *, org_id: uuid.UUID
) -> dict[str, int]:
    """Sponsored-campaign status counts for an org's CRM rollup."""

    from sqlalchemy import func

    rows = (
        await session.execute(
            select(SponsoredPlacement.status, func.count())
            .where(
                SponsoredPlacement.org_id == org_id,
                SponsoredPlacement.deleted_at.is_(None),
            )
            .group_by(SponsoredPlacement.status)
        )
    ).all()
    return {status: count for status, count in rows}
