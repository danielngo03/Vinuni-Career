"""Discovery ORM models (spec §8): ``discovery_sessions`` + ``discovery_events``.

Both are PRIVACY-SAFE BY CONSTRUCTION — there is no column for name/email/phone,
exact GPS, raw IP, raw CV text, sensitive categories, or third-party ad ids. The
only signal store is ``discovery_sessions.coarse_tags`` (JSONB), and the service
layer routes every write through :mod:`app.modules.discovery.domain.allowlist`, so
only allowlisted coarse keys can ever land there.

``discovery_sessions``
    A first-party anonymous session keyed by a RANDOM uuid (NOT derived from any
    user identity). ``user_id`` is a nullable link populated only once a session-
    holder logs in (so post-login signal continuity works) — it is the only PII-
    adjacent field and is a plain FK, never exposed by the public event API.

``discovery_events``
    The append-only analytics ledger written by ad-funded surfaces and
    recommendation rails. ``placement_id`` is an FK-less reference to
    ``sponsored_placements`` set ONLY for sponsored surfaces. ``scope`` records
    whether the event was anonymous / session-linked / user-linked.

Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs (partial/extra indexes,
CHECK constraints, ``set_updated_at`` trigger) live in migration ``0020`` only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class DiscoverySession(Base):
    """A first-party anonymous discovery session (random id; coarse signals only)."""

    __tablename__ = "discovery_sessions"

    # Random anonymous id — NOT tied to user PII.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable link populated once a session-holder logs in (post-login continuity).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    locale: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # ONLY allowlisted coarse tags (see domain/allowlist.py). Never PII.
    coarse_tags: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    # Privacy reset / do-not-personalize preference.
    opt_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Short TTL; the cleanup sweep prunes rows past this.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class DiscoveryEvent(Base):
    """An append-only privacy-safe discovery analytics event."""

    __tablename__ = "discovery_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # impression|click|view|apply_start|save_intent|event_register_intent
    source_surface: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # job|event|company|banner
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # FK-less reference to sponsored_placements; set ONLY for sponsored surfaces.
    placement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # anonymous|session|user
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_sessions.id", ondelete="SET NULL"), nullable=True
    )
    # Plain (FK-less) — high-volume append-only ledger, mirrors audit_logs.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
