"""reviews: company_reviews + review_ratings + review_reports + proj_company_rating

Module 13 / E19 (ADR-0013). Student-authored company reviews with a per-category
rating, university moderation, and a projection read-model for the public company
profile aggregate (Bayesian score; no live JOIN on the guest surface).

Slice-1 ships PRE-MODERATION: a review is `pending` until a university moderator
publishes it. The auto-publish + AI-scan model (`docs/BUSINESS_LOGIC.md` §7.3) is
deferred until AI moderation (B-343) lands — that gate is currently resource-
blocked. `is_anonymous` is reserved now (display-only) but public anonymous
display is a later slice.

Postgres-only constructs (CHECK constraints, partial indexes, `set_updated_at`
trigger) are guarded by `is_postgres`; the SQLite unit-test path builds the schema
from ORM metadata and enforces the vocabularies in the service layer.

Revision ID: 0025_company_reviews_and_ratings
Revises: 0024_campaign_creatives
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_company_reviews_and_ratings"
down_revision: str | None = "0024_campaign_creatives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    now = sa.text("NOW()") if is_postgres else sa.func.now()

    # ------------------------------------------------------- company_reviews
    op.create_table(
        "company_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("eligibility_type", sa.String(30), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pros", sa.Text(), nullable=True),
        sa.Column("cons", sa.Text(), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("moderated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("org_id", "reviewer_id",
                            name="uq_review_per_reviewer_org"),
    )

    # ------------------------------------------------------- review_ratings (1:1)
    op.create_table(
        "review_ratings",
        sa.Column("review_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("company_reviews.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("overall", sa.SmallInteger(), nullable=False),
        sa.Column("work_life_balance", sa.SmallInteger(), nullable=False),
        sa.Column("culture_values", sa.SmallInteger(), nullable=False),
        sa.Column("compensation", sa.SmallInteger(), nullable=False),
        sa.Column("career_growth", sa.SmallInteger(), nullable=False),
        sa.Column("interview_experience", sa.SmallInteger(), nullable=True),
    )

    # ------------------------------------------------------- review_reports
    op.create_table(
        "review_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("review_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("company_reviews.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason_code", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now),
        sa.UniqueConstraint("review_id", "reporter_id", name="uq_report_once"),
    )

    # ------------------------------------------------------- proj_company_rating
    op.create_table(
        "proj_company_rating",
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("overall_raw_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("work_life_balance_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("culture_values_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("compensation_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("career_growth_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("interview_experience_avg", sa.Numeric(3, 2), nullable=True),
        sa.Column("distribution", postgresql.JSONB().with_variant(
            sa.JSON(), "sqlite"), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now),
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_review_status", "company_reviews",
            "status IN ('pending','published','flagged','removed')",
        )
        op.create_check_constraint(
            "ck_review_eligibility", "company_reviews",
            "eligibility_type IN ('system_verified_interview',"
            "'system_verified_offer','self_declared','partner_verified')",
        )
        for col in (
            "overall", "work_life_balance", "culture_values",
            "compensation", "career_growth",
        ):
            op.create_check_constraint(
                f"ck_rating_{col}", "review_ratings",
                f"{col} BETWEEN 1 AND 5",
            )
        op.create_check_constraint(
            "ck_rating_interview", "review_ratings",
            "interview_experience IS NULL OR interview_experience BETWEEN 1 AND 5",
        )
        op.create_index(
            "idx_reviews_org_pub", "company_reviews",
            ["org_id", "status", sa.text("published_at DESC")],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_reviews_reviewer", "company_reviews", ["reviewer_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_company_reviews_updated_at "
            "ON company_reviews;"
        )
        op.execute(
            "CREATE TRIGGER trg_company_reviews_updated_at BEFORE UPDATE ON "
            "company_reviews FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index(
            "idx_reviews_org_pub", "company_reviews", ["org_id", "status"]
        )
        op.create_index(
            "idx_reviews_reviewer", "company_reviews", ["reviewer_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_company_reviews_updated_at "
            "ON company_reviews;"
        )
    op.drop_index("idx_reviews_reviewer", table_name="company_reviews")
    op.drop_index("idx_reviews_org_pub", table_name="company_reviews")
    op.drop_table("proj_company_rating")
    op.drop_table("review_reports")
    op.drop_table("review_ratings")
    op.drop_table("company_reviews")
