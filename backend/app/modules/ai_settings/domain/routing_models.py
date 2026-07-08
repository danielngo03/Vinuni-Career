from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class AiRoutingGraph(Base):
    __tablename__ = "ai_routing_graphs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_family: Mapped[str] = mapped_column(String(20))
    graph: Mapped[dict] = mapped_column(JsonType)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    activated_at: Mapped[datetime | None] = mapped_column(default=None)
    compiled_alias_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_model_aliases.id"), default=None
    )


class AiRoutingGraphActivation(Base):
    __tablename__ = "ai_routing_graph_activations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    graph_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_routing_graphs.id"))
    graph_version: Mapped[int]
    activated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    activated_at: Mapped[datetime]
    previous_active_graph_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
