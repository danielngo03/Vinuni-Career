"""workflow_tz_aware_timestamps

Fixes a P0 bug found during partner-RBAC/workflow-builder QA verification:
``workflow_node_execution_logs.entered_at/exited_at`` and
``workflow_failed_node_tasks.created_at/resolved_at`` were created in
0062_partner_os_e33_e36_slice as naive ``TIMESTAMP`` columns, but the
application layer (``execution_service.py``) always writes tz-aware
``datetime.now(tz=UTC)`` values into them (matching this codebase's universal
tz-aware-timestamp convention — see ``app/shared/models.py``'s
``TimestampMixin``). asyncpg rejects binding a tz-aware Python datetime to a
naive-typed column ("can't subtract offset-naive and offset-aware
datetimes"), which broke flow execution and failed-node-task creation on
PostgreSQL (masked by the test suite's SQLite backend, which does not
enforce tz-awareness). The paired ORM models
(``app/modules/workflow/domain/models.py``) were fixed alongside this
migration to declare ``mapped_column(DateTime(timezone=True))`` explicitly
for every datetime column in the module.

``workflow_flows.created_at/activated_at`` and
``workflow_executions.started_at/finished_at`` (from 0048_workflow_engine)
were already ``TIMESTAMPTZ`` at the DB level — only their ORM-side type
annotations were wrong, which is a code-only fix and needs no migration.

Revision ID: 0063_workflow_tz_aware_timestamps
Revises: 0062_partner_os_e33_e36_slice
Create Date: 2026-07-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063_workflow_tz_aware_timestamps"
down_revision: str | None = "0062_partner_os_e33_e36_slice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `USING col AT TIME ZONE 'UTC'` reinterprets the existing naive values
    # (which were always written as UTC wall-clock time by the application)
    # as UTC instants rather than shifting them per server timezone.
    op.execute(
        "ALTER TABLE workflow_node_execution_logs "
        "ALTER COLUMN entered_at TYPE TIMESTAMPTZ USING entered_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_node_execution_logs "
        "ALTER COLUMN exited_at TYPE TIMESTAMPTZ USING exited_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_failed_node_tasks "
        "ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_failed_node_tasks "
        "ALTER COLUMN resolved_at TYPE TIMESTAMPTZ USING resolved_at AT TIME ZONE 'UTC'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE workflow_node_execution_logs "
        "ALTER COLUMN entered_at TYPE TIMESTAMP USING entered_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_node_execution_logs "
        "ALTER COLUMN exited_at TYPE TIMESTAMP USING exited_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_failed_node_tasks "
        "ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute(
        "ALTER TABLE workflow_failed_node_tasks "
        "ALTER COLUMN resolved_at TYPE TIMESTAMP USING resolved_at AT TIME ZONE 'UTC'"
    )
