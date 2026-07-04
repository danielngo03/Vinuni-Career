"""career_services: university counselor workspace (B-554)

Cohorts, cohort memberships, at-risk flags, CV review queue items, appointments
(with a cross-dialect double-booking guard via nullable ``conflict_key``),
employer relationship notes, and intervention history.

Revision ID: 0058_career_services_workspace
Revises: 0057_analytics_events
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058_career_services_workspace"
down_revision = "0057_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_services_cohorts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_counselor_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["owner_counselor_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_cs_cohort_org_name"),
    )
    op.create_index(
        "ix_cs_cohorts_org_id", "career_services_cohorts", ["org_id"]
    )
    op.create_index(
        "ix_cs_cohorts_owner", "career_services_cohorts", ["owner_counselor_id"]
    )

    op.create_table(
        "career_services_cohort_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cohort_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["career_services_cohorts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("cohort_id", "student_id", name="uq_cs_cohort_member"),
    )
    op.create_index(
        "ix_cs_cohort_members_cohort", "career_services_cohort_memberships", ["cohort_id"]
    )
    op.create_index(
        "ix_cs_cohort_members_student",
        "career_services_cohort_memberships",
        ["student_id"],
    )

    op.create_table(
        "career_services_at_risk_flags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("flagged_by", sa.Uuid(), nullable=False),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["cohort_id"], ["career_services_cohorts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["flagged_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_cs_at_risk_org_id", "career_services_at_risk_flags", ["org_id"]
    )
    op.create_index(
        "ix_cs_at_risk_student_id", "career_services_at_risk_flags", ["student_id"]
    )

    op.create_table(
        "career_services_cv_review_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("assigned_counselor_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cv_id"], ["cv_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assigned_counselor_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_cs_cv_review_org_id", "career_services_cv_review_items", ["org_id"]
    )
    op.create_index(
        "ix_cs_cv_review_student_id",
        "career_services_cv_review_items",
        ["student_id"],
    )

    op.create_table(
        "career_services_appointments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("counselor_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conflict_key", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duration_minutes", sa.SmallInteger(), nullable=False, server_default="30"
        ),
        sa.Column("mode", sa.String(20), nullable=False, server_default="in_person"),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "counselor_id", "conflict_key", name="uq_cs_appt_counselor_slot"
        ),
    )
    op.create_index(
        "ix_cs_appt_org_id", "career_services_appointments", ["org_id"]
    )
    op.create_index(
        "ix_cs_appt_student_id", "career_services_appointments", ["student_id"]
    )
    op.create_index(
        "ix_cs_appt_counselor_id", "career_services_appointments", ["counselor_id"]
    )

    op.create_table(
        "career_services_employer_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("employer_org_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="general"),
        sa.Column(
            "visibility", sa.String(30), nullable=False, server_default="all_staff"
        ),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["employer_org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_cs_employer_notes_org_id", "career_services_employer_notes", ["org_id"]
    )
    op.create_index(
        "ix_cs_employer_notes_employer_org_id",
        "career_services_employer_notes",
        ["employer_org_id"],
    )

    op.create_table(
        "career_services_interventions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("counselor_id", sa.Uuid(), nullable=False),
        sa.Column("intervention_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "outcome", sa.String(30), nullable=False, server_default="no_outcome_yet"
        ),
        sa.Column("linked_appointment_id", sa.Uuid(), nullable=True),
        sa.Column("linked_at_risk_flag_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["counselor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["linked_appointment_id"],
            ["career_services_appointments.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_at_risk_flag_id"],
            ["career_services_at_risk_flags.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_cs_interventions_org_id", "career_services_interventions", ["org_id"]
    )
    op.create_index(
        "ix_cs_interventions_student_id",
        "career_services_interventions",
        ["student_id"],
    )
    op.create_index(
        "ix_cs_interventions_counselor_id",
        "career_services_interventions",
        ["counselor_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cs_interventions_counselor_id", table_name="career_services_interventions"
    )
    op.drop_index(
        "ix_cs_interventions_student_id", table_name="career_services_interventions"
    )
    op.drop_index(
        "ix_cs_interventions_org_id", table_name="career_services_interventions"
    )
    op.drop_table("career_services_interventions")

    op.drop_index(
        "ix_cs_employer_notes_employer_org_id",
        table_name="career_services_employer_notes",
    )
    op.drop_index(
        "ix_cs_employer_notes_org_id", table_name="career_services_employer_notes"
    )
    op.drop_table("career_services_employer_notes")

    op.drop_index("ix_cs_appt_counselor_id", table_name="career_services_appointments")
    op.drop_index("ix_cs_appt_student_id", table_name="career_services_appointments")
    op.drop_index("ix_cs_appt_org_id", table_name="career_services_appointments")
    op.drop_table("career_services_appointments")

    op.drop_index(
        "ix_cs_cv_review_student_id", table_name="career_services_cv_review_items"
    )
    op.drop_index(
        "ix_cs_cv_review_org_id", table_name="career_services_cv_review_items"
    )
    op.drop_table("career_services_cv_review_items")

    op.drop_index("ix_cs_at_risk_student_id", table_name="career_services_at_risk_flags")
    op.drop_index("ix_cs_at_risk_org_id", table_name="career_services_at_risk_flags")
    op.drop_table("career_services_at_risk_flags")

    op.drop_index(
        "ix_cs_cohort_members_student", table_name="career_services_cohort_memberships"
    )
    op.drop_index(
        "ix_cs_cohort_members_cohort", table_name="career_services_cohort_memberships"
    )
    op.drop_table("career_services_cohort_memberships")

    op.drop_index("ix_cs_cohorts_owner", table_name="career_services_cohorts")
    op.drop_index("ix_cs_cohorts_org_id", table_name="career_services_cohorts")
    op.drop_table("career_services_cohorts")
