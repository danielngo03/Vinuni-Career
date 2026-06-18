from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.models.base import TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base


class AutomationWorkflow(Base, TimestampMixin):
    __tablename__ = "automation_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_event: Mapped[str] = mapped_column(String(120), nullable=False)
    graph_data: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowExecutionLog(Base):
    __tablename__ = "workflow_execution_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("automation_workflows.id"),
        index=True,
    )
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="SUCCEEDED")
    execution_trace: Mapped[dict] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
