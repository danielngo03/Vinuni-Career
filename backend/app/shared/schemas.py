from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIMessage(BaseModel):
    message: str


class PageParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ErrorResponse(BaseModel):
    detail: str
    trace_id: str | None = None


class AuditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str | None
    action: str
    target_resource: str
    target_id: str | None
    new_data: dict[str, Any] | None
    created_at: datetime
