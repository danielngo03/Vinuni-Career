"""recruitment pipeline stage engine: templates + stages + candidate stages

ADR-0004 §3/§6. The stage engine's foundational layer:

- ``pipeline_templates`` — per-org ordered pipeline definitions. One immutable
  ``is_default = is_system = true`` row is SEEDED per existing org (data step).
- ``pipeline_stages`` — the ordered stages of a template (unique ``(template_id,
  sort_order)``). The seeded default is the canonical 3-stage ladder
  Screening -> Interview -> Offer, all ``required_action = manual``.
- ``candidate_stages`` — the APPEND-ONLY stage history of an application
  (``status ∈ {ACTIVE, PASSED, ROLLED_BACK, REJECTED}``). A Postgres partial
  unique index enforces "at most one ACTIVE row per application"; it is
  dialect-guarded so it is inert/skipped on SQLite (unit tests rely on the
  service-layer guard).

``applications`` is intentionally NOT altered — the coarse outcome stays on
``applications.status``; the fine pipeline position lives in ``candidate_stages``.
The named-but-deferred ``interviews`` / ``scorecards`` / ``offers`` tables are NOT
created here (their own later ADRs/migrations own them).

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; the service's lazy ``ensure_org_default_template`` seeds the default
template there (and for orgs created after this migration on Postgres).

Revision ID: 0012_pipeline_stage_engine
Revises: 0011_outbox_retry_backoff
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_pipeline_stage_engine"
down_revision: str | None = "0011_outbox_retry_backoff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Canonical seeded ladder (mirrors ``recruitment.domain.pipeline.DEFAULT_STAGES``).
_DEFAULT_TEMPLATE_NAME = "Quy trình tuyển dụng mặc định"
_DEFAULT_STAGES = (
    ("Sàng lọc hồ sơ", "screening", 1, False),
    ("Phỏng vấn", "interview", 2, False),
    ("Đề nghị", "offer", 3, True),
)

_UQ_ACTIVE = "uq_candidate_stage_active"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ------------------------------------------------- pipeline_templates
    op.create_table(
        "pipeline_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_pipeline_templates_org", "pipeline_templates", ["org_id"])

    # ---------------------------------------------------- pipeline_stages
    op.create_table(
        "pipeline_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("template_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipeline_templates.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("stage_type", sa.String(30), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("required_action", sa.String(30), nullable=False,
                  server_default="manual"),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("candidate_visible", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("automation_rules", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("template_id", "sort_order", name="uq_pipeline_stage_order"),
    )
    op.create_index("idx_pipeline_stages_template", "pipeline_stages", ["template_id"])

    # --------------------------------------------------- candidate_stages
    op.create_table(
        "candidate_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("entered_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_kind", sa.String(20), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("idx_candidate_stages_app", "candidate_stages", ["application_id"])

    if is_postgres:
        # At most one ACTIVE candidate stage per application (the single-slot
        # invariant). Partial unique index — dialect-guarded; SQLite tests rely on
        # the service-layer guard.
        op.create_index(
            _UQ_ACTIVE, "candidate_stages", ["application_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )
        # Idempotency-Key dedupe lookup for a retried advance/rollback.
        op.create_index(
            "idx_candidate_stages_idem", "candidate_stages",
            ["application_id", "idempotency_key"],
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )

        # ---- Data step: seed one immutable system-default template per org. ----
        # INSERT...SELECT so it is atomic and correct regardless of org count; the
        # NOT EXISTS guard keeps a re-run idempotent.
        op.execute(
            f"""
            INSERT INTO pipeline_templates (id, org_id, name, is_default, is_system, created_at)
            SELECT gen_random_uuid(), o.id, '{_DEFAULT_TEMPLATE_NAME}', true, true, NOW()
            FROM organizations o
            WHERE NOT EXISTS (
                SELECT 1 FROM pipeline_templates t
                WHERE t.org_id = o.id AND t.is_system = true AND t.is_default = true
            )
            """
        )
        for name, stage_type, sort_order, is_terminal in _DEFAULT_STAGES:
            op.execute(
                f"""
                INSERT INTO pipeline_stages
                    (id, template_id, name, stage_type, sort_order, required_action,
                     is_terminal, candidate_visible, automation_rules)
                SELECT gen_random_uuid(), t.id, '{name}', '{stage_type}', {sort_order},
                       'manual', {str(is_terminal).lower()}, true, '{{}}'::jsonb
                FROM pipeline_templates t
                WHERE t.is_system = true AND t.is_default = true
                  AND NOT EXISTS (
                      SELECT 1 FROM pipeline_stages s
                      WHERE s.template_id = t.id AND s.sort_order = {sort_order}
                  )
                """
            )
    else:
        op.create_index(
            "idx_candidate_stages_idem", "candidate_stages",
            ["application_id", "idempotency_key"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index("idx_candidate_stages_idem", table_name="candidate_stages")
    if is_postgres:
        op.drop_index(_UQ_ACTIVE, table_name="candidate_stages")
    op.drop_index("idx_candidate_stages_app", table_name="candidate_stages")
    op.drop_table("candidate_stages")

    op.drop_index("idx_pipeline_stages_template", table_name="pipeline_stages")
    op.drop_table("pipeline_stages")

    op.drop_index("idx_pipeline_templates_org", table_name="pipeline_templates")
    op.drop_table("pipeline_templates")
