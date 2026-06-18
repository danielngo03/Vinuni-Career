"""Add registration verification, policy, evidence and history.

Revision ID: 20260618_0003
Revises: 20260618_0002
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20260618_0003"
down_revision = "20260618_0002"
branch_labels = None
depends_on = None


REGISTRATION_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "VERIFYING",
    "PENDING",
    "UNDER_REVIEW",
    "CHANGES_REQUESTED",
    "NEEDS_CHANGES",
    "RESUBMITTED",
    "APPROVED",
    "REJECTED",
    "WITHDRAWN",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if bind.dialect.name == "postgresql":
        for value in REGISTRATION_STATUSES:
            op.execute(
                sa.text(
                    "ALTER TYPE registrationstatus ADD VALUE IF NOT EXISTS "
                    f"'{value}'"
                )
            )

    if "registration_applications" in tables:
        columns = {
            column["name"]
            for column in inspector.get_columns("registration_applications")
        }
        additions = {
            "version": sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            "checklist": sa.Column(
                "checklist",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            "assessment": sa.Column(
                "assessment",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            "policy_snapshot": sa.Column(
                "policy_snapshot",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        }
        for name, column in additions.items():
            if name not in columns:
                op.add_column("registration_applications", column)

    if "verification_policies" not in tables:
        op.create_table(
            "verification_policies",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "university_org_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id"),
                nullable=False,
            ),
            sa.Column("registration_type", sa.String(length=40), nullable=False),
            sa.Column("mode", sa.String(length=40), nullable=False),
            sa.Column(
                "global_kill_switch",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "confidence_threshold",
                sa.Integer(),
                nullable=False,
                server_default="90",
            ),
            sa.Column(
                "required_providers",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "required_documents",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("sample_rate", sa.Integer(), nullable=False, server_default="100"),
            sa.Column(
                "model_version",
                sa.String(length=120),
                nullable=False,
                server_default="deterministic-v1",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "university_org_id",
                "registration_type",
                name="uq_verification_policy_university_type",
            ),
        )
        op.create_index(
            "ix_verification_policies_university_org_id",
            "verification_policies",
            ["university_org_id"],
        )
        op.create_index(
            "ix_verification_policies_registration_type",
            "verification_policies",
            ["registration_type"],
        )

    if "registration_evidence" not in tables:
        op.create_table(
            "registration_evidence",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "application_id",
                sa.String(length=36),
                sa.ForeignKey("registration_applications.id"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("provider", sa.String(length=120), nullable=False),
            sa.Column("field_name", sa.String(length=120), nullable=False),
            sa.Column(
                "authority",
                sa.String(length=80),
                nullable=False,
                server_default="self_reported",
            ),
            sa.Column("trust_weight", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "extracted_value",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "provenance",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("mismatch", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_registration_evidence_application_id",
            "registration_evidence",
            ["application_id"],
        )
        op.create_index(
            "ix_registration_evidence_provider",
            "registration_evidence",
            ["provider"],
        )
        op.create_index(
            "ix_registration_evidence_field_name",
            "registration_evidence",
            ["field_name"],
        )

    if "registration_history" not in tables:
        op.create_table(
            "registration_history",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "application_id",
                sa.String(length=36),
                sa.ForeignKey("registration_applications.id"),
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("from_status", sa.String(length=40), nullable=True),
            sa.Column("to_status", sa.String(length=40), nullable=False),
            sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id")),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "snapshot",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_registration_history_application_id",
            "registration_history",
            ["application_id"],
        )
        op.create_index(
            "ix_registration_history_to_status",
            "registration_history",
            ["to_status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table_name in (
        "registration_history",
        "registration_evidence",
        "verification_policies",
    ):
        if table_name in tables:
            op.drop_table(table_name)

    if "registration_applications" in tables:
        columns = {
            column["name"]
            for column in inspect(bind).get_columns("registration_applications")
        }
        with op.batch_alter_table("registration_applications") as batch:
            for name in ("policy_snapshot", "assessment", "checklist", "version"):
                if name in columns:
                    batch.drop_column(name)
