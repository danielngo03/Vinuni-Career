"""Advertising ORM models (ADR-0009 §2/§5/§6).

Two tables:

- ``ad_packages`` — a small seeded reference table of named, fixed-price tiers (no
  bidding, no budget pacing). The chosen package constrains a placement's
  ``placement_type`` and its ``price_amount`` is frozen onto the placement at
  submit.
- ``sponsored_placements`` — a partner's request to sponsor / feature one target
  the partner already owns (a ``job`` or an ``event``). The polymorphic target is
  ``target_type`` + ``target_id`` with **no DB foreign key** (it points at two
  tables); a CHECK constrains ``target_type`` and the service layer validates
  ownership. ``sponsored_placements`` is the SOURCE OF TRUTH for sponsorship; the
  ``jobs/events.is_sponsored``/``is_featured`` columns are a recomputed projection.

Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs (partial unique index,
partial indexes, CHECK constraints, ``set_updated_at`` trigger) live in migration
``0017`` only; the SQLite test path enforces the invariants in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.shared.models import Base, JsonType


class AdPackage(Base):
    """A named, fixed-price advertising tier (reference data; seeded in ``0017``)."""

    __tablename__ = "ad_packages"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # The placement kind the package primarily represents (display/labeling).
    placement_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # sponsored | featured | both
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="VND")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    grants_sponsored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    grants_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class SponsoredPlacement(Base):
    """A partner's request to sponsor / feature one owned job or event.

    Never hard-deleted (soft delete via ``deleted_at``). ``status`` is the lifecycle
    state machine in :mod:`app.modules.advertising.domain.lifecycle`.
    """

    __tablename__ = "sponsored_placements"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    # Polymorphic target — NO FK (points at jobs OR events); CHECK on target_type,
    # service-layer ownership validation.
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)  # job|event
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    placement_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # sponsored | featured | both
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ad_packages.id"), nullable=False
    )
    # Frozen snapshot of the package price at submit (price freeze). NULL while draft.
    price_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="VND")

    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft|pending_approval|approved|active|completed|rejected|cancelled
    # Public inventory class shown to end users (spec §4). Partner placements
    # default to ``paid_sponsored`` (non-removable disclosure); the university may
    # relabel a NON-paid placement to curated/strategic/featured. Never used to
    # mislabel paid inventory as editorial content.
    disclosure_class: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=disclosure_vocab.DEFAULT_DISCLOSURE_CLASS,
    )
    disclosure_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured rejection/escalation reason code (``app.shared.moderation``);
    # ``moderation_note`` remains the optional supplementary free-text field.
    moderation_reason_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paid_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # SLA deadline computed at submission time
    # (``settings.advertising_moderation_sla_hours``).
    due_by: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # T-24h "ending soon" notification dedupe stamp (set by the completion sweep).
    ending_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    settings: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class CampaignCreative(Base):
    """An uploaded banner image attached to a placement for one delivery slot.

    Campaign creatives are PUBLIC marketing media (like org logos) — no Fernet
    encryption, but a magic-byte image allowlist + a size cap gate the bytes
    before they become servable. The internal ``image_path`` storage key is never
    returned to any client; public surfaces receive only the resolved, stable
    creative URL (see :func:`creative_media.public_creative_url`). Soft-deleted
    via ``deleted_at``; review is the small ``moderation_status`` state machine in
    :mod:`app.modules.advertising.domain.creatives`.
    """

    __tablename__ = "campaign_creatives"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    placement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sponsored_placements.id"), nullable=False, index=True
    )
    slot: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # homepage_hero | right_rail | inline_card | event_banner

    # Stored bytes (internal key + resolved media identity). Never exposed.
    image_path: Mapped[str] = mapped_column(String(400), nullable=False)
    media_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    alt_vi: Mapped[str | None] = mapped_column(String(300), nullable=True)
    alt_en: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Responsive crop focal point, normalized to [0, 1] x [0, 1].
    focal_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    focal_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    click_target: Mapped[str | None] = mapped_column(String(500), nullable=True)

    moderation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=creative_vocab.CREATIVE_PENDING,
    )  # pending | approved | rejected
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional per-creative display window (defaults to the placement window).
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Where impressions/clicks attributed to this creative are surfaced (analytics).
    analytics_source_surface: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
