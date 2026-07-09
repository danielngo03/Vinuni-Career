"""Declarative ``Base``, shared column mixins, and cross-cutting infra tables.

Conventions follow ``docs/DATA_MODEL.md`` §3:

- UUID primary keys
- ``created_at`` / ``updated_at`` timestamps
- ``deleted_at`` soft delete (``NULL`` = active)
- ``version`` optimistic-locking counter

Types are declared cross-database: ``Uuid`` and ``JSON`` render natively on
PostgreSQL and degrade cleanly on SQLite for unit tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres, plain JSON on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")

# BIGSERIAL/identity on Postgres; INTEGER PRIMARY KEY (autoincrement rowid) on SQLite.
BigIntPk = BigInteger().with_variant(Integer(), "sqlite")


def ensure_aware(value: datetime) -> datetime:
    """Coerce a possibly naive DB datetime to UTC-aware.

    ``DateTime(timezone=True)`` returns aware values on PostgreSQL but naive ones
    on SQLite (unit tests); comparisons against ``datetime.now(tz=UTC)`` must not
    mix naive/aware. Shared across modules (not auth-specific) so any module can
    import it from here instead of reaching into ``auth.domain.models``.
    """

    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in the project."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class VersionedMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BaseEntity(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionedMixin):
    """Full base entity: UUID PK + timestamps + soft delete + version."""

    __abstract__ = True


# --------------------------------------------------------------------------- #
# Cross-cutting infrastructure tables (Phase 0 baseline)                       #
# --------------------------------------------------------------------------- #


class AuditLog(Base):
    """Append-only audit trail for every write action (``docs/DATA_MODEL.md``).

    Stores IP/UA **hashes** only — never raw values. ``actor_id`` /
    ``actor_org_id`` / ``session_id`` are plain UUIDs in Phase 0; FKs to
    ``users``/``organizations``/``sessions`` are added once those tables exist.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    before_snapshot: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    after_snapshot: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OutboxEvent(Base):
    """Transactional outbox for domain events (``docs/ARCHITECTURE.md`` §4.6)."""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
