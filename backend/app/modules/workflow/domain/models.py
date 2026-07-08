from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType

# All datetime columns in this module are populated with tz-aware
# ``datetime.now(tz=UTC)`` values by the application layer (execution_service,
# flow_service, activation_service). A bare ``Mapped[datetime]`` annotation
# (no explicit ``mapped_column(DateTime(timezone=True))``) makes SQLAlchemy
# infer a timezone-NAIVE column/bind type, which asyncpg then rejects with
# "can't subtract offset-naive and offset-aware datetimes" as soon as a
# tz-aware value is inserted — breaking flow creation/activation/execution on
# PostgreSQL (this only "worked" against the SQLite test DB, which does not
# enforce tz-awareness). Every timestamp column below is explicit for this
# reason; see the paired Alembic migration that aligns the two columns that
# were originally created as naive TIMESTAMP.


class WorkflowFlow(Base):
    __tablename__ = "workflow_flows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text(), default=None)
    trigger_type: Mapped[str] = mapped_column(String(60))
    graph: Mapped[dict] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # Ownership: a flow is owned by either a partner org or the university org
    # (docs/PARTNER_RBAC_ANALYTICS_SPEC.md "Allowed flow owners"). Nullable for
    # backward compatibility with rows written before this column existed;
    # application code always sets it on create.
    owner_type: Mapped[str | None] = mapped_column(String(20), default=None)  # partner|university
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    # Set when this flow is a draft edit created from an active flow via
    # ``activation_service.create_new_draft_version`` / clone; lets the UI show
    # "based on v{N}" and lets clone distinguish "new" flows from revisions.
    cloned_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_flows.id"), default=None
    )


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_flows.id"))
    trigger_event: Mapped[dict] = mapped_column(JsonType)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    node_logs: Mapped[list] = mapped_column(JsonType, default=list)
    # ``True`` for dry-run/test executions (docs contract's ``/test`` endpoint):
    # no real side effects are performed and the row is excluded from
    # production execution history/read models by default.
    is_simulated: Mapped[bool] = mapped_column(default=False)


class WorkflowNodeExecutionLog(Base):
    """One row per node entered during an execution — the durable, queryable
    counterpart to ``WorkflowExecution.node_logs`` (kept for backward
    compatibility with the inline JSON summary already relied on by
    ``execution_service``/tests). Values here are redacted/summarized: no raw
    CV text, tokens, or full trigger payloads.
    """

    __tablename__ = "workflow_node_execution_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_executions.id"))
    node_id: Mapped[str] = mapped_column(String(120))
    node_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # success|failed|skipped
    actor_type: Mapped[str] = mapped_column(String(20), default="system")  # system|user
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    reason: Mapped[str | None] = mapped_column(Text(), default=None)
    input_summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    output_summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    user_safe_error: Mapped[str | None] = mapped_column(Text(), default=None)
    is_simulated: Mapped[bool] = mapped_column(default=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class WorkflowFailedNodeTask(Base):
    """A recoverable manual-follow-up task created when a node fails during a
    real (non-simulated) execution, so a failed notification/pipeline move/
    approval is never silently dropped — it surfaces on the owning org's
    todos for manual retry or resolution.
    """

    __tablename__ = "workflow_failed_node_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_executions.id"))
    flow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_flows.id"))
    node_id: Mapped[str] = mapped_column(String(120))
    node_type: Mapped[str] = mapped_column(String(40))
    owner_type: Mapped[str | None] = mapped_column(String(20), default=None)
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), default=None
    )
    user_safe_error: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|resolved|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
