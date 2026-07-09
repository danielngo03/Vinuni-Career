"""Company-reviews ORM models (Module 13 / ADR-0013).

`CompanyReview` (full BaseEntity: UUID PK + timestamps + soft-delete + version) is
student-authored, employer-scoped (`org_id`), one-per-reviewer-per-company. Its
1:1 `ReviewRating` holds the per-category stars. `ReviewReport` records abuse
reports (one per actor per review). `ProjCompanyRating` is the recompute-on-event
read model the public company profile reads through the rating facade (no live
JOIN on the guest surface).

No student PII lives here beyond the `reviewer_id` FK; the public presenter never
emits the reviewer id when `is_anonymous`. Raw status/eligibility codes stay
internal — friendly labels live in `..domain.labels`.

Cross-database types via the shared variants so the models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only CHECK/index/trigger constructs
live in migration `0025`; the SQLite path enforces vocabularies in the service.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, BaseEntity, JsonType


class CompanyReview(BaseEntity):
    """A student's review of one employer org (one per reviewer per company)."""

    __tablename__ = "company_reviews"

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Strongest interaction proof, frozen at submit (never re-derived on read).
    eligibility_type: Mapped[str] = mapped_column(String(30), nullable=False)
    application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pros: Mapped[str | None] = mapped_column(Text, nullable=True)
    cons: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Helpfulness (denormalized count; `review_helpful_votes` is the source).
    helpful_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Partner response (employer reply to a published review).
    partner_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    partner_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReviewHelpfulVote(Base):
    """One authenticated user's 'helpful' mark on a review (one per voter per review)."""

    __tablename__ = "review_helpful_votes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewRating(Base):
    """Per-category 1-5 stars, 1:1 with a review (PK = FK)."""

    __tablename__ = "review_ratings"

    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reviews.id", ondelete="CASCADE"),
        primary_key=True,
    )
    overall: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    work_life_balance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    culture_values: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    compensation: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    career_growth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    interview_experience: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class ReviewReport(Base):
    """An abuse report against a review (one per reporter per review)."""

    __tablename__ = "review_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("company_reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reporter_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProjCompanyRating(Base):
    """Recompute-on-event aggregate read model (one row per employer org)."""

    __tablename__ = "proj_company_rating"

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    overall_raw_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    work_life_balance_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    culture_values_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    compensation_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    career_growth_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    interview_experience_avg: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    distribution: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
