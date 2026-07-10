"""ORM -> friendly response shapes for the campaign allocation engine (spec §7.0).

Presenters emit vi+en labels (status / objective / pacing / disclosure), the
budget + derived pacing state, and coarse targeting — NEVER raw enum codes alone,
NEVER internal spend rate as a "bid", and NEVER PII. The manual-payment reference
is admin-only spend oversight and is omitted from the partner/public projection.

The PUBLIC allocation projection is the strictest: it exposes only the banner
creative, the campaign name, the source ``inventory_class`` and the mandatory,
non-removable disclosure — never budget, spend, targeting, or org internals.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.advertising.domain import campaign as campaign_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain import pacing as pacing_math
from app.modules.advertising.domain.models import AdCampaign, AdSlot
from app.shared.moderation import queue_age_fields, reason_code_label


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def _public_creative(creative: dict | None) -> dict:
    """Only the public banner fields — never storage keys or internal refs."""

    c = creative or {}
    return {
        "headline": c.get("headline"),
        "body": c.get("body"),
        "image_ref": c.get("image_ref"),
        "click_target": c.get("click_target"),
        "alt": c.get("alt_en") if c.get("alt_en") else c.get("alt_vi"),
        "alt_vi": c.get("alt_vi"),
        "alt_en": c.get("alt_en"),
    }


def slot(s: AdSlot, *, locale: str = "vi") -> dict:
    return {
        "id": str(s.id),
        "code": s.code,
        "surface": s.surface,
        "name": s.name_en if locale == "en" else s.name_vi,
        "capacity": s.capacity,
        "max_sponsored_share": s.max_sponsored_share,
        "is_active": s.is_active,
    }


def campaign(
    c: AdCampaign,
    *,
    locale: str = "vi",
    admin: bool = False,
    impressions_today: int = 0,
) -> dict:
    """Partner/admin campaign projection with derived pacing state.

    ``impressions_today`` (from the ``ad_events`` aggregate) lets the presenter
    surface the honest delivery/pacing state so an under-delivering campaign shows
    truthfully to the partner and university (spec §7.0 fairness).
    """

    state = pacing_math.compute_pacing_state(
        pacing=c.pacing,
        budget=c.budget_amount,
        spent=c.spent_amount,
        cpm=c.cpm_amount,
        start_at=_aware(c.start_at),
        end_at=_aware(c.end_at),
        impressions_today=impressions_today,
    )
    data: dict[str, object] = {
        "id": str(c.id),
        "org_id": str(c.org_id),
        "name": c.name,
        "objective": c.objective,
        "objective_label": campaign_vocab.objective_label(c.objective, locale=locale),
        "surface": c.surface,
        "status": c.status,
        "status_label": campaign_vocab.status_label(c.status, locale=locale),
        "pacing": c.pacing,
        "pacing_label": campaign_vocab.pacing_label(c.pacing, locale=locale),
        "budget_amount": _amount(c.budget_amount),
        "spent_amount": _amount(c.spent_amount),
        "currency": c.currency,
        "start_at": _iso(c.start_at),
        "end_at": _iso(c.end_at),
        "targeting": c.targeting or {},
        "creative": _public_creative(c.creative),
        "target_type": c.target_type,
        "target_id": str(c.target_id) if c.target_id else None,
        "disclosure_class": c.disclosure_class,
        "disclosure": disclosure_vocab.disclosure_payload(c.disclosure_class, locale=locale),
        "disclosure_confirmed": c.disclosure_confirmed,
        "is_paid": c.paid_at is not None,
        "moderation_note": c.moderation_note,
        # Honest delivery / pacing state (never a bid, never a raw model score).
        "delivery": {
            "impression_goal": state.impression_goal,
            "impressions_today": state.impressions_today,
            "daily_cap": state.daily_cap,
            "budget_exhausted": state.budget_exhausted,
            "paced_out": state.paced_out,
            "serving_eligible": state.eligible and c.status == campaign_vocab.ACTIVE,
        },
        "submitted_at": _iso(c.submitted_at),
        "approved_at": _iso(c.approved_at),
        "activated_at": _iso(c.activated_at),
        "paused_at": _iso(c.paused_at),
        "ended_at": _iso(c.ended_at),
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
        "version": c.version,
    }
    if admin:
        # Spend oversight: the bank-transfer reference is admin-only.
        data["payment_reference"] = c.payment_reference
        data["paid_at"] = _iso(c.paid_at)
        data["created_by"] = str(c.created_by)
        data["approved_by"] = str(c.approved_by) if c.approved_by else None
        data["moderation_reason_code"] = c.moderation_reason_code
        data["moderation_reason_label"] = reason_code_label(
            c.moderation_reason_code, locale=locale
        )
        data.update(
            queue_age_fields(submitted_at=c.submitted_at, due_by=c.due_by, now=datetime.now(tz=UTC))
        )
    return data


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
