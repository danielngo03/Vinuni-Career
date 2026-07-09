"""Partner campaign / advertising performance read (design spec §6 "Advertising").

Per-placement + per-campaign delivery metrics for the OWNING partner org:
impressions, clicks, CTR, apply-starts, and committed spend. Delivery counters
come from the platform analytics ledger (``analytics_events`` rows of type
``ad.impression`` / ``ad.click`` / ``ad.apply_start``, ``aggregate_type =
ad_placement``) — the shared cross-module reporting mirror of the discovery
capture ledger, so reporting never special-cases ``discovery_events``. Spend is
the frozen ``price_amount`` on the placement (org-internal, never PII).

RBAC is enforced HERE (service layer): the caller must be a partner-org member
holding ``analytics:view_job_metrics`` for their own org. Placement rows are
fetched through the advertising ``inventory_facade`` (no cross-module ORM import);
delivery counters are aggregated from this module's own ``analytics_events``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import inventory_facade
from app.modules.advertising.domain import lifecycle as ad_lifecycle
from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.auth.domain import personas
from app.modules.opportunities.application import job_read_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

# Which placement lifecycle states represent a real, reportable campaign. A draft
# has neither delivery nor frozen spend yet; a cancelled/rejected one never ran.
_REPORTABLE_STATUSES: tuple[str, ...] = (
    ad_lifecycle.APPROVED,
    ad_lifecycle.ACTIVE,
    ad_lifecycle.COMPLETED,
)

# Committed spend counts only placements that were approved-and-onward (price is
# frozen at submit; a draft carries no committed spend).
_SPEND_STATUSES: frozenset[str] = frozenset(
    {ad_lifecycle.APPROVED, ad_lifecycle.ACTIVE, ad_lifecycle.COMPLETED}
)

_EVENT_COLUMN: dict[str, str] = {
    "ad.impression": "impressions",
    "ad.click": "clicks",
    "ad.apply_start": "apply_starts",
}


def _require_partner_analytics(principal: Principal) -> uuid.UUID:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.PARTNER_MEMBER:
        raise PermissionDeniedError()
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, "analytics", "view_job_metrics", resource_org_id=principal.org_id
    )
    return principal.org_id


async def _delivery_by_placement(
    session: AsyncSession, *, placement_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """``{placement_id: {impressions, clicks, apply_starts}}`` from analytics_events."""

    base = {"impressions": 0, "clicks": 0, "apply_starts": 0}
    if not placement_ids:
        return {}
    rows = (
        await session.execute(
            select(
                AnalyticsEvent.aggregate_id,
                AnalyticsEvent.event_type,
                func.count(),
            )
            .where(
                AnalyticsEvent.aggregate_type == "ad_placement",
                AnalyticsEvent.event_type.in_(tuple(_EVENT_COLUMN.keys())),
                AnalyticsEvent.aggregate_id.in_(placement_ids),
            )
            .group_by(AnalyticsEvent.aggregate_id, AnalyticsEvent.event_type)
        )
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {}
    for placement_id, event_type, count in rows:
        column = _EVENT_COLUMN[event_type]
        out.setdefault(placement_id, dict(base))[column] += int(count or 0)
    return out


def _ctr(impressions: int, clicks: int) -> float | None:
    return round((clicks / impressions) * 100.0, 2) if impressions else None


async def get_campaign_performance(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """Per-campaign delivery + spend for the caller's own org (RBAC-gated)."""

    org_id = _require_partner_analytics(principal)

    placements = await inventory_facade.list_org_placements_for_reporting(
        session, org_id=org_id, statuses=_REPORTABLE_STATUSES
    )
    placement_ids = [p.placement_id for p in placements]
    delivery = await _delivery_by_placement(session, placement_ids=placement_ids)

    job_ids = [p.target_id for p in placements if p.target_type == ad_lifecycle.TARGET_JOB]
    job_titles = await job_read_facade.get_job_titles(session, job_ids) if job_ids else {}

    campaigns: list[dict] = []
    total_impressions = 0
    total_clicks = 0
    total_apply_starts = 0
    total_spend = Decimal(0)
    currency = "VND"

    for p in placements:
        d = delivery.get(p.placement_id, {"impressions": 0, "clicks": 0, "apply_starts": 0})
        impressions = d["impressions"]
        clicks = d["clicks"]
        apply_starts = d["apply_starts"]
        total_impressions += impressions
        total_clicks += clicks
        total_apply_starts += apply_starts

        spend = p.price_amount if (p.status in _SPEND_STATUSES and p.price_amount) else None
        if spend is not None:
            total_spend += spend
            currency = p.currency

        title = (
            job_titles.get(p.target_id)
            if p.target_type == ad_lifecycle.TARGET_JOB
            else None
        )
        campaigns.append(
            {
                "placement_id": str(p.placement_id),
                "target_type": p.target_type,
                "target_type_label": ad_lifecycle.target_type_label(p.target_type, locale=locale),
                "target_id": str(p.target_id),
                "target_title": title,
                "placement_type": p.placement_type,
                "placement_type_label": ad_lifecycle.placement_type_label(
                    p.placement_type, locale=locale
                ),
                "status": p.status,
                "status_label": ad_lifecycle.status_label(p.status, locale=locale),
                "disclosure_class": p.disclosure_class,
                "start_at": p.start_at.isoformat() if p.start_at else None,
                "end_at": p.end_at.isoformat() if p.end_at else None,
                "impressions": impressions,
                "clicks": clicks,
                "apply_starts": apply_starts,
                "ctr_pct": _ctr(impressions, clicks),
                "spend": float(spend) if spend is not None else None,
                "currency": p.currency,
            }
        )

    return {
        "campaigns": campaigns,
        "totals": {
            "campaigns": len(campaigns),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "apply_starts": total_apply_starts,
            "ctr_pct": _ctr(total_impressions, total_clicks),
            "spend": float(total_spend),
            "currency": currency,
        },
    }
