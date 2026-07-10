"""``ad_events`` daily-aggregate helpers: pacing reads, event recording, reporting.

The ``ad_events`` table is a PRIVACY-SAFE per-campaign / per-slot / per-day counter
(impressions / clicks / apply-starts / event-register-intents + accumulated spend).
It has NO PII, no raw IP, no GPS — only aggregate counts. It feeds two things:

- PACING: :func:`impressions_today_for` gives the allocation engine today's delivery
  so ``even`` pacing can throttle a campaign that has hit its daily share;
- REPORTING: :func:`campaign_performance` rolls up CTR / apply-start rate for the
  partner's own campaign analytics and the university's oversight view.

:func:`record_event` is the delivery accounting path (called by the public event
endpoint). An ``impression`` also spends against the campaign budget at the frozen
per-impression rate; when the budget is exhausted the campaign is auto-``ended``
(the real budget cap). Exact per-event idempotency lives in the fine-grained
``discovery_events`` ledger; this aggregate is intentionally an approximate counter
(spec §8 "ad_impressions / ad_clicks can initially share discovery_events").
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain import pacing as pacing_math
from app.modules.advertising.domain.models import AdCampaign, AdEventDaily
from app.shared.audit import AuditContext, write_audit

# Delivery event vocabulary (privacy-safe; no PII / GPS / raw IP).
EV_IMPRESSION = "impression"
EV_CLICK = "click"
EV_APPLY_START = "apply_start"
EV_REGISTER_INTENT = "register_intent"

EVENT_TYPES: frozenset[str] = frozenset(
    {EV_IMPRESSION, EV_CLICK, EV_APPLY_START, EV_REGISTER_INTENT}
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _use_lock() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def impressions_today_for(
    session: AsyncSession, *, campaign_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Total impressions delivered for a campaign on ``now``'s date (all slots)."""

    day = (now or _now()).date()
    total = (
        await session.execute(
            select(func.coalesce(func.sum(AdEventDaily.impressions), 0)).where(
                AdEventDaily.campaign_id == campaign_id,
                AdEventDaily.event_date == day,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def impressions_today_bulk(
    session: AsyncSession, *, campaign_ids: list[uuid.UUID], now: datetime | None = None
) -> dict[uuid.UUID, int]:
    """Batched ``impressions_today_for`` for a set of campaigns (allocation loop)."""

    if not campaign_ids:
        return {}
    day = (now or _now()).date()
    rows = (
        await session.execute(
            select(AdEventDaily.campaign_id, func.coalesce(func.sum(AdEventDaily.impressions), 0))
            .where(
                AdEventDaily.campaign_id.in_(campaign_ids),
                AdEventDaily.event_date == day,
            )
            .group_by(AdEventDaily.campaign_id)
        )
    ).all()
    out = dict.fromkeys(campaign_ids, 0)
    for cid, total in rows:
        out[cid] = int(total or 0)
    return out


async def _get_or_create_daily(
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    slot_id: uuid.UUID,
    surface: str,
    day: date,
) -> AdEventDaily:
    stmt = select(AdEventDaily).where(
        AdEventDaily.campaign_id == campaign_id,
        AdEventDaily.slot_id == slot_id,
        AdEventDaily.event_date == day,
    )
    if _use_lock():
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = AdEventDaily(
            campaign_id=campaign_id,
            slot_id=slot_id,
            surface=surface,
            event_date=day,
            impressions=0,
            clicks=0,
            apply_starts=0,
            register_intents=0,
            spend_amount=Decimal("0"),
        )
        session.add(row)
        await session.flush()
    return row


async def record_event(
    session: AsyncSession,
    *,
    campaign: AdCampaign,
    slot_id: uuid.UUID,
    event_type: str,
    now: datetime | None = None,
    audit_ctx: AuditContext | None = None,
) -> AdEventDaily:
    """Increment the daily aggregate for a delivery event; spend on impressions.

    Caller is responsible for committing. The impression path spends against the
    campaign budget at the frozen per-impression rate and auto-``ends`` the
    campaign once the budget is exhausted (the real budget cap; audited).
    """

    now = now or _now()
    day = now.date()
    row = await _get_or_create_daily(
        session,
        campaign_id=campaign.id,
        slot_id=slot_id,
        surface=campaign.surface,
        day=day,
    )

    if event_type == EV_IMPRESSION:
        row.impressions += 1
        cost = pacing_math.cost_per_impression(cpm=campaign.cpm_amount)
        row.spend_amount = (row.spend_amount or Decimal("0")) + cost
        campaign.spent_amount = (campaign.spent_amount or Decimal("0")) + cost
        if (
            pacing_math.budget_exhausted(spent=campaign.spent_amount, budget=campaign.budget_amount)
            and campaign.status == lifecycle.ACTIVE
        ):
            campaign.status = lifecycle.ENDED
            campaign.ended_at = now
            campaign.version += 1
            await write_audit(
                session,
                action="advertising.campaign_budget_exhausted",
                resource_type="ad_campaign",
                resource_id=campaign.id,
                context=audit_ctx or AuditContext(),
                after={"status": campaign.status, "reason": "budget_exhausted"},
            )
    elif event_type == EV_CLICK:
        row.clicks += 1
    elif event_type == EV_APPLY_START:
        row.apply_starts += 1
    elif event_type == EV_REGISTER_INTENT:
        row.register_intents += 1
    await session.flush()
    return row


async def campaign_performance(
    session: AsyncSession, *, campaign_id: uuid.UUID
) -> dict:
    """Lifetime aggregate performance for one campaign (privacy-safe counts)."""

    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(AdEventDaily.impressions), 0),
                func.coalesce(func.sum(AdEventDaily.clicks), 0),
                func.coalesce(func.sum(AdEventDaily.apply_starts), 0),
                func.coalesce(func.sum(AdEventDaily.register_intents), 0),
                func.coalesce(func.sum(AdEventDaily.spend_amount), 0),
            ).where(AdEventDaily.campaign_id == campaign_id)
        )
    ).one()
    impressions, clicks, apply_starts, register_intents, spend = row
    impressions = int(impressions or 0)
    clicks = int(clicks or 0)
    apply_starts = int(apply_starts or 0)
    register_intents = int(register_intents or 0)

    def _rate(numerator: int) -> float:
        return round(numerator / impressions, 4) if impressions else 0.0

    return {
        "impressions": impressions,
        "clicks": clicks,
        "apply_starts": apply_starts,
        "register_intents": register_intents,
        "ctr": _rate(clicks),
        "apply_start_rate": _rate(apply_starts),
        "spend_amount": f"{Decimal(str(spend or 0)):.2f}",
        "currency": "VND",
    }
