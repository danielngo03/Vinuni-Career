"""membership_roles.department_id + career_services_cohorts.department_id.

Department-scoped permission enforcement (P2/WS2.1). Strictly additive — every
existing row is NULL, so behavior is byte-for-byte unchanged:

1. ``membership_roles.department_id`` (nullable FK -> departments, SET NULL) —
   NULL = the role assignment's grants apply ORG-WIDE (today's behavior);
   non-NULL = the grants apply ONLY inside that department
   (``Principal.department_grants``). The composite PK ``(membership_id,
   role_id)`` is unchanged, so a role assignment carries at most one department
   scope. An index on ``department_id`` supports the scoped-grant resolution
   query and department-deletion cascades.
2. ``career_services_cohorts.department_id`` (nullable FK -> departments,
   SET NULL) — the representative department-owned university resource: cohort
   writes are gated by a department-scoped ``career_services_cohorts`` grant for
   this department. NULL = org-wide cohort (every existing row → unchanged).

Revision ID: 0087_membership_role_department_scope
Revises: 0086_chat_attachments_university
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087_membership_role_department_scope"
down_revision: str | None = "0086_chat_attachments_university"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Per-assignment department scope on membership_roles.
    op.add_column(
        "membership_roles",
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_membership_roles_department_id",
        "membership_roles",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_membership_roles_department_id",
        "membership_roles",
        ["department_id"],
    )

    # 2. Owning department on career-services cohorts (representative enforcement).
    op.add_column(
        "career_services_cohorts",
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_career_services_cohorts_department_id",
        "career_services_cohorts",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_career_services_cohorts_department_id",
        "career_services_cohorts",
        ["department_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_career_services_cohorts_department_id",
        table_name="career_services_cohorts",
    )
    op.drop_constraint(
        "fk_career_services_cohorts_department_id",
        "career_services_cohorts",
        type_="foreignkey",
    )
    op.drop_column("career_services_cohorts", "department_id")

    op.drop_index(
        "ix_membership_roles_department_id",
        table_name="membership_roles",
    )
    op.drop_constraint(
        "fk_membership_roles_department_id",
        "membership_roles",
        type_="foreignkey",
    )
    op.drop_column("membership_roles", "department_id")
