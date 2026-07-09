"""knowledge_bases audience + department scoping (partner internal-doc isolation).

Adds two columns to ``knowledge_bases`` so partner knowledge bases can be split
into an ``applicant_facing`` audience (readable by org members + active
applicants) and an ``internal`` audience (org members only, optionally scoped to
a single department). Closes the hole where internal company documents were
readable by student applicants.

- ``audience``     VARCHAR NOT NULL DEFAULT 'internal' ('applicant_facing'|'internal')
- ``department_id`` UUID NULL FK -> departments.id (NULL = whole org)
- index ``ix_kb_scope_org_audience`` on (scope, org_id, audience)

Backfill: existing rows default to ``internal`` (the safe choice — never exposed
to applicants) via the column DEFAULT.

Revision ID: 0088_kb_audience_department
Revises: 0087_chat_attachments
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0088_kb_audience_department"
down_revision: str | None = "0087_chat_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_kb_scope_org_audience"
_FK = "fk_knowledge_bases_department_id"


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "audience",
            sa.String(length=20),
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        _FK,
        "knowledge_bases",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        _INDEX,
        "knowledge_bases",
        ["scope", "org_id", "audience"],
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="knowledge_bases")
    op.drop_constraint(_FK, "knowledge_bases", type_="foreignkey")
    op.drop_column("knowledge_bases", "department_id")
    op.drop_column("knowledge_bases", "audience")
