"""Human review queue ORM model (AI_PRODUCT_SPEC §9.3).

One row per escalated AI advisory finding awaiting a human moderator's final
decision. AI findings are ADVISORY: the queue exists precisely so a human —
not a model — makes every consequential moderation/fraud call.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")

SOURCE_BIAS = "bias_detection"
SOURCE_CONTENT = "content_moderation"
SOURCE_FRAUD = "fraud_detection"
SOURCE_AGENT_LOOP = "agent_loop"
# A human moderator explicitly escalated a job/event/ad-placement moderation
# item for a second opinion (jobs/events/advertising moderation "escalate"
# action), rather than an AI detector raising an advisory finding.
SOURCE_MODERATOR_ESCALATION = "moderator_escalation"
# ADR-0014 (E36): platform-support and abuse/fraud triage additions to the
# `human_review_queue.source` vocabulary. `source` is a plain String(32) with
# no DB enum/CHECK constraint (migration 0052) — these are code-only
# constants, no migration required.
SOURCE_SUPPORT_CASE = "support_case"
SOURCE_USER_REPORT = "user_report"

STATUS_PENDING = "PENDING"
STATUS_RESOLVED = "RESOLVED"
STATUS_DISMISSED = "DISMISSED"


class HumanReviewItem(Base):
    __tablename__ = "human_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, index=True
    )
    findings_json: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --------------------------------------------------------------------------- #
# Content reports (ADR-0014, docs/DATA_MODEL.md §35)                          #
# --------------------------------------------------------------------------- #

REPORT_ENTITY_TYPES = frozenset({"company", "job", "message"})

REPORT_STATUS_PENDING = "PENDING"
REPORT_STATUS_TRIAGED = "TRIAGED"
REPORT_STATUS_DISMISSED = "DISMISSED"
REPORT_STATUSES = frozenset(
    {REPORT_STATUS_PENDING, REPORT_STATUS_TRIAGED, REPORT_STATUS_DISMISSED}
)


class ContentReport(Base):
    """A user-submitted report on a reportable entity (company/job/message, V1).

    ``UNIQUE(reporter_id, entity_type, entity_id)`` makes a duplicate report
    from the same reporter on the same entity an idempotent no-op — the
    primary anti-spam control. A service-layer rate limit on distinct-entity
    report volume per reporter per window is the secondary control (the
    unique constraint alone cannot be defeated by reporting many different
    entities in a burst).
    """

    __tablename__ = "content_reports"
    __table_args__ = (
        UniqueConstraint(
            "reporter_id", "entity_type", "entity_id", name="uq_content_report_reporter_entity"
        ),
        Index("idx_content_reports_entity", "entity_type", "entity_id"),
        Index("idx_content_reports_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reporter_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REPORT_STATUS_PENDING
    )
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("human_review_queue.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
