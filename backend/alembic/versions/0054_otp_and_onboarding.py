"""Add OTP columns to email_verifications; create onboarding_states, student_verifications;
extend partner_registration_requests.

Revision ID: 0054_otp_and_onboarding
Revises: 0053_job_requirements_industry_links
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0054_otp_and_onboarding"
down_revision = "0053_job_requirements_industry_links"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    # ── email_verifications: add OTP columns ────────────────────────────────
    op.add_column(
        "email_verifications",
        sa.Column("otp_code_hash", sa.String(128), nullable=True),
    )
    op.add_column(
        "email_verifications",
        sa.Column("otp_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    # purpose now also accepts 'student_email' — VARCHAR column already wide enough

    # ── onboarding_states ───────────────────────────────────────────────────
    op.create_table(
        "onboarding_states",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("role", sa.String(20), nullable=True),
        sa.Column("seeker_type", sa.String(30), nullable=True),
        sa.Column("current_step", sa.String(50), nullable=False, server_default="role_select"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── student_verifications ───────────────────────────────────────────────
    op.create_table(
        "student_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("university_name", sa.String(255), nullable=False),
        sa.Column("student_id_number", sa.String(50), nullable=False),
        sa.Column("student_email", sa.String(320), nullable=False),
        sa.Column("student_email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id_card_file_path", sa.String(500), nullable=True),
        sa.Column("ai_check_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("ai_check_result", _JSON, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ── partner_registration_requests: extend with doc verification cols ────
    with op.batch_alter_table("partner_registration_requests") as batch_op:
        batch_op.add_column(sa.Column("tax_id", sa.String(20), nullable=True))
        batch_op.add_column(
            sa.Column("tax_id_verified", sa.Boolean(), nullable=False, server_default="false")
        )
        batch_op.add_column(sa.Column("tax_id_api_result", _JSON, nullable=True))
        batch_op.add_column(sa.Column("document_path", sa.String(500), nullable=True))
        batch_op.add_column(
            sa.Column("ai_doc_status", sa.String(30), nullable=False, server_default="pending")
        )
        batch_op.add_column(sa.Column("ai_doc_result", _JSON, nullable=True))
        batch_op.add_column(sa.Column("submitted_by_user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_partner_reg_submitted_by",
            "users",
            ["submitted_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("partner_registration_requests") as batch_op:
        batch_op.drop_constraint("fk_partner_reg_submitted_by", type_="foreignkey")
        batch_op.drop_column("submitted_by_user_id")
        batch_op.drop_column("ai_doc_result")
        batch_op.drop_column("ai_doc_status")
        batch_op.drop_column("document_path")
        batch_op.drop_column("tax_id_api_result")
        batch_op.drop_column("tax_id_verified")
        batch_op.drop_column("tax_id")

    op.drop_table("student_verifications")
    op.drop_table("onboarding_states")

    op.drop_column("email_verifications", "otp_attempts")
    op.drop_column("email_verifications", "otp_code_hash")
