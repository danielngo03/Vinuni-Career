"""ORM -> friendly response shapes for advertising (ADR-0009 §7).

Presenters emit vi+en labels (``status_label``, ``placement_type_label``,
``target_type_label``, ``package``), the frozen price, and the target's public
title — **never raw enum codes alone, never internal status of the target beyond
what the partner already owns, and never AI/provider internals**. The
``payment_reference`` (bank-transfer ref) is admin-only spend oversight and is
omitted from the partner projection.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import (
    AdPackage,
    CampaignCreative,
    SponsoredPlacement,
)
from app.modules.advertising.infrastructure import creative_media
from app.shared.moderation import queue_age_fields, reason_code_label


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def package(pkg: AdPackage, *, locale: str = "vi") -> dict:
    return {
        "id": str(pkg.id),
        "code": pkg.code,
        "name": pkg.name,
        "placement_type": pkg.placement_type,
        "placement_type_label": lifecycle.placement_type_label(pkg.placement_type, locale=locale),
        "price_amount": _amount(pkg.price_amount),
        "currency": pkg.currency,
        "duration_days": pkg.duration_days,
        "grants_sponsored": pkg.grants_sponsored,
        "grants_featured": pkg.grants_featured,
        "is_active": pkg.is_active,
    }


def _alt_for(c: CampaignCreative, *, locale: str) -> str | None:
    """Localized alt text with a graceful vi<->en fallback (spec §5)."""

    if locale == "en":
        return c.alt_en or c.alt_vi
    return c.alt_vi or c.alt_en


def creative(c: CampaignCreative, *, locale: str = "vi") -> dict:
    """Friendly creative shape — NEVER the raw ``image_path`` storage key."""

    spec = creative_vocab.slot_spec(c.slot)
    return {
        "id": str(c.id),
        "placement_id": str(c.placement_id),
        "slot": c.slot,
        "slot_label": creative_vocab.slot_label(c.slot, locale=locale),
        "asset_requirements": spec,
        # Stable public serve URL (re-checks approval+active on each request).
        "image_url": creative_media.public_creative_url(c.id, version=c.version),
        "media_type": c.media_type,
        "alt": _alt_for(c, locale=locale),
        "alt_vi": c.alt_vi,
        "alt_en": c.alt_en,
        "focal_point": {"x": c.focal_x, "y": c.focal_y},
        "click_target": c.click_target,
        "moderation_status": c.moderation_status,
        "moderation_status_label": creative_vocab.creative_status_label(
            c.moderation_status, locale=locale
        ),
        "moderation_note": c.moderation_note,
        "start_at": _iso(c.start_at),
        "end_at": _iso(c.end_at),
        "analytics_source_surface": c.analytics_source_surface,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
        "version": c.version,
    }


def placement(
    p: SponsoredPlacement,
    *,
    locale: str = "vi",
    pkg: AdPackage | None = None,
    target_title: str | None = None,
    admin: bool = False,
    creatives: list[CampaignCreative] | None = None,
) -> dict:
    data: dict[str, object] = {
        "id": str(p.id),
        "org_id": str(p.org_id),
        "target_type": p.target_type,
        "target_type_label": lifecycle.target_type_label(p.target_type, locale=locale),
        "target_id": str(p.target_id),
        "target_title": target_title,
        "placement_type": p.placement_type,
        "placement_type_label": lifecycle.placement_type_label(p.placement_type, locale=locale),
        "disclosure_class": p.disclosure_class,
        "disclosure": disclosure_vocab.disclosure_payload(p.disclosure_class, locale=locale),
        "package_id": str(p.package_id),
        "package": package(pkg, locale=locale) if pkg is not None else None,
        "price_amount": _amount(p.price_amount),
        "currency": p.currency,
        "start_at": _iso(p.start_at),
        "end_at": _iso(p.end_at),
        "status": p.status,
        "status_label": lifecycle.status_label(p.status, locale=locale),
        "disclosure_confirmed": p.disclosure_confirmed,
        "moderation_note": p.moderation_note,
        "is_paid": p.paid_at is not None,
        "paid_at": _iso(p.paid_at),
        "submitted_at": _iso(p.submitted_at),
        "approved_at": _iso(p.approved_at),
        "activated_at": _iso(p.activated_at),
        "completed_at": _iso(p.completed_at),
        "cancelled_at": _iso(p.cancelled_at),
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
        "version": p.version,
    }
    if creatives is not None:
        live = [c for c in creatives if c.deleted_at is None]
        data["creatives"] = [creative(c, locale=locale) for c in live]
        # Asset-requirements / missing-asset state for the primary public slots
        # (partner uploader + university "missing/broken creative" inspector).
        present_slots = {
            c.slot for c in live if c.moderation_status == creative_vocab.CREATIVE_APPROVED
        }
        data["missing_primary_slots"] = sorted(
            s for s in creative_vocab.PRIMARY_SLOTS if s not in present_slots
        )
        data["has_approved_creative"] = bool(present_slots)
    if admin:
        # Spend oversight: the bank-transfer reference is admin-only.
        data["payment_reference"] = p.payment_reference
        data["created_by"] = str(p.created_by)
        data["approved_by"] = str(p.approved_by) if p.approved_by else None
        data["moderation_reason_code"] = p.moderation_reason_code
        data["moderation_reason_label"] = reason_code_label(p.moderation_reason_code, locale=locale)
        data["claimed_by"] = str(p.claimed_by) if p.claimed_by else None
        data["claimed_at"] = _iso(p.claimed_at)
        data.update(
            queue_age_fields(submitted_at=p.submitted_at, due_by=p.due_by, now=datetime.now(tz=UTC))
        )
    return data
