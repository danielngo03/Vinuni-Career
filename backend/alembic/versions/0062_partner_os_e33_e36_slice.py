"""partner_os_e33_e36_slice

Adds the additive schema for the E33 Partner RBAC/Recruiting Intelligence and
E36 B-552/B-553 slice: organization ownership/CRM fields, workflow builder
ownership/simulation/execution-log/failed-node-task tables, recruitment SLA
reminder tracking, and partner job-metrics/candidate-access read models.

This migration is hand-authored (not raw `alembic revision --autogenerate`
output) because autogenerate on this shared dev database also picked up a
large amount of unrelated pre-existing drift (renamed indexes, dropped
tables such as `provinces`/`wards`/`job_embeddings`/`platform_settings`) from
other concurrently-running work outside this slice. That drift is
intentionally excluded here; it should be reconciled separately by whoever
owns it.

Revision ID: 0062_partner_os_e33_e36_slice
Revises: 0061_market_intelligence_snapshot
Create Date: 2026-07-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062_partner_os_e33_e36_slice"
down_revision: str | None = "0061_market_intelligence_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- organization: ownership + CRM (B-518/519/523, B-553) ---
    op.add_column(
        "organizations",
        sa.Column("owner_membership_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_owner_membership_id",
        "organizations",
        "memberships",
        ["owner_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "organizations",
        sa.Column("campus_relationship_owner_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_campus_relationship_owner_id",
        "organizations",
        "users",
        ["campus_relationship_owner_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "organization_risk_flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("flag_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("raised_by", sa.Uuid(), nullable=False),
        sa.Column(
            "raised_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raised_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_risk_flags_org_id"),
        "organization_risk_flags",
        ["org_id"],
        unique=False,
    )

    op.create_table(
        "organization_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_notes_org_id"),
        "organization_notes",
        ["org_id"],
        unique=False,
    )

    # --- recruitment: SLA reminder idempotency tracking ---
    op.add_column(
        "candidate_stages",
        sa.Column("sla_reminder_level", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "candidate_stages",
        sa.Column("sla_reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- workflow: partner ownership, simulation, node logs, failed-node tasks ---
    op.add_column(
        "workflow_flows",
        sa.Column("owner_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "workflow_flows",
        sa.Column("owner_org_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflow_flows_owner_org_id",
        "workflow_flows",
        "organizations",
        ["owner_org_id"],
        ["id"],
    )
    op.add_column(
        "workflow_flows",
        sa.Column("cloned_from_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflow_flows_cloned_from_id",
        "workflow_flows",
        "workflow_flows",
        ["cloned_from_id"],
        ["id"],
    )

    op.add_column(
        "workflow_executions",
        sa.Column(
            "is_simulated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "workflow_node_execution_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=False),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "input_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "output_summary",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("user_safe_error", sa.Text(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.Column("entered_at", sa.DateTime(), nullable=False),
        sa.Column("exited_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_node_execution_logs_execution_id"),
        "workflow_node_execution_logs",
        ["execution_id"],
        unique=False,
    )

    op.create_table(
        "workflow_failed_node_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("flow_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=False),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=True),
        sa.Column("owner_org_id", sa.Uuid(), nullable=True),
        sa.Column("user_safe_error", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
        sa.ForeignKeyConstraint(["flow_id"], ["workflow_flows.id"]),
        sa.ForeignKeyConstraint(["owner_org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_failed_node_tasks_flow_id"),
        "workflow_failed_node_tasks",
        ["flow_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_failed_node_tasks_owner_org_id"),
        "workflow_failed_node_tasks",
        ["owner_org_id"],
        unique=False,
    )

    # --- analytics: partner job metrics + candidate access read models ---
    op.create_table(
        "partner_job_metrics_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("detail_views", sa.Integer(), nullable=False),
        sa.Column("cta_clicks", sa.Integer(), nullable=False),
        sa.Column("apply_starts", sa.Integer(), nullable=False),
        sa.Column("applications_submitted", sa.Integer(), nullable=False),
        sa.Column("save_clicks", sa.Integer(), nullable=False),
        sa.Column("share_clicks", sa.Integer(), nullable=False),
        sa.Column("src_organic", sa.Integer(), nullable=False),
        sa.Column("src_search", sa.Integer(), nullable=False),
        sa.Column("src_recommendation", sa.Integer(), nullable=False),
        sa.Column("src_sponsored", sa.Integer(), nullable=False),
        sa.Column("src_invitation", sa.Integer(), nullable=False),
        sa.Column("src_direct", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "metric_date", name="uq_job_metrics_daily_job_date"
        ),
    )
    op.create_index(
        op.f("ix_partner_job_metrics_daily_job_id"),
        "partner_job_metrics_daily",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_job_metrics_daily_metric_date"),
        "partner_job_metrics_daily",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_job_metrics_daily_org_id"),
        "partner_job_metrics_daily",
        ["org_id"],
        unique=False,
    )

    op.create_table(
        "partner_job_metric_dimensions_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("dimension_type", sa.String(length=20), nullable=False),
        sa.Column("dimension_value", sa.String(length=40), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "metric_date",
            "dimension_type",
            "dimension_value",
            name="uq_job_metric_dim_daily",
        ),
    )
    op.create_index(
        op.f("ix_partner_job_metric_dimensions_daily_job_id"),
        "partner_job_metric_dimensions_daily",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_job_metric_dimensions_daily_metric_date"),
        "partner_job_metric_dimensions_daily",
        ["metric_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_job_metric_dimensions_daily_org_id"),
        "partner_job_metric_dimensions_daily",
        ["org_id"],
        unique=False,
    )

    op.create_table(
        "partner_candidate_access_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_department_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_department_id"], ["departments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_partner_candidate_access_events_application_id"),
        "partner_candidate_access_events",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_candidate_access_events_job_id"),
        "partner_candidate_access_events",
        ["job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_partner_candidate_access_events_org_id"),
        "partner_candidate_access_events",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_partner_candidate_access_events_org_id"),
        table_name="partner_candidate_access_events",
    )
    op.drop_index(
        op.f("ix_partner_candidate_access_events_job_id"),
        table_name="partner_candidate_access_events",
    )
    op.drop_index(
        op.f("ix_partner_candidate_access_events_application_id"),
        table_name="partner_candidate_access_events",
    )
    op.drop_table("partner_candidate_access_events")

    op.drop_index(
        op.f("ix_partner_job_metric_dimensions_daily_org_id"),
        table_name="partner_job_metric_dimensions_daily",
    )
    op.drop_index(
        op.f("ix_partner_job_metric_dimensions_daily_metric_date"),
        table_name="partner_job_metric_dimensions_daily",
    )
    op.drop_index(
        op.f("ix_partner_job_metric_dimensions_daily_job_id"),
        table_name="partner_job_metric_dimensions_daily",
    )
    op.drop_table("partner_job_metric_dimensions_daily")

    op.drop_index(
        op.f("ix_partner_job_metrics_daily_org_id"),
        table_name="partner_job_metrics_daily",
    )
    op.drop_index(
        op.f("ix_partner_job_metrics_daily_metric_date"),
        table_name="partner_job_metrics_daily",
    )
    op.drop_index(
        op.f("ix_partner_job_metrics_daily_job_id"),
        table_name="partner_job_metrics_daily",
    )
    op.drop_table("partner_job_metrics_daily")

    op.drop_index(
        op.f("ix_workflow_failed_node_tasks_owner_org_id"),
        table_name="workflow_failed_node_tasks",
    )
    op.drop_index(
        op.f("ix_workflow_failed_node_tasks_flow_id"),
        table_name="workflow_failed_node_tasks",
    )
    op.drop_table("workflow_failed_node_tasks")

    op.drop_index(
        op.f("ix_workflow_node_execution_logs_execution_id"),
        table_name="workflow_node_execution_logs",
    )
    op.drop_table("workflow_node_execution_logs")

    op.drop_column("workflow_executions", "is_simulated")

    op.drop_constraint(
        "fk_workflow_flows_cloned_from_id", "workflow_flows", type_="foreignkey"
    )
    op.drop_column("workflow_flows", "cloned_from_id")
    op.drop_constraint(
        "fk_workflow_flows_owner_org_id", "workflow_flows", type_="foreignkey"
    )
    op.drop_column("workflow_flows", "owner_org_id")
    op.drop_column("workflow_flows", "owner_type")

    op.drop_column("candidate_stages", "sla_reminder_sent_at")
    op.drop_column("candidate_stages", "sla_reminder_level")

    op.drop_index(
        op.f("ix_organization_notes_org_id"), table_name="organization_notes"
    )
    op.drop_table("organization_notes")

    op.drop_index(
        op.f("ix_organization_risk_flags_org_id"),
        table_name="organization_risk_flags",
    )
    op.drop_table("organization_risk_flags")

    op.drop_constraint(
        "fk_organizations_campus_relationship_owner_id",
        "organizations",
        type_="foreignkey",
    )
    op.drop_column("organizations", "campus_relationship_owner_id")
    op.drop_constraint(
        "fk_organizations_owner_membership_id", "organizations", type_="foreignkey"
    )
    op.drop_column("organizations", "owner_membership_id")
