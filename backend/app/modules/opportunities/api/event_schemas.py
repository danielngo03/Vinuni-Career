"""Pydantic request schemas for the events API (ADR-0008).

HTTP validation only; vocabulary checks against ``domain.event_lifecycle`` and
business rules (time ordering, capacity, lifecycle) live in the services.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EventCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    description: str = Field(min_length=10)
    event_type: str = Field(max_length=30)
    format: str = Field(max_length=20)
    cover_image_path: str | None = Field(default=None, max_length=1000)
    venue_name: str | None = Field(default=None, max_length=300)
    venue_address: str | None = None
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=50)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=1_000_000)
    visibility: str = Field(default="public", max_length=20)
    tags: list[str] = Field(default_factory=list)


class EventUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    description: str | None = Field(default=None, min_length=10)
    event_type: str | None = Field(default=None, max_length=30)
    format: str | None = Field(default=None, max_length=20)
    cover_image_path: str | None = Field(default=None, max_length=1000)
    venue_name: str | None = Field(default=None, max_length=300)
    venue_address: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=50)
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=1_000_000)
    visibility: str | None = Field(default=None, max_length=20)
    tags: list[str] | None = None
    version: int | None = None


class EventVersionRequest(BaseModel):
    """Optional optimistic-version body for submit / cancel."""

    version: int | None = None


class EventApproveRequest(BaseModel):
    """Approve has no required fields — an empty/absent body is valid (no 422)."""

    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class EventModerationRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)
    version: int | None = None


class EventEscalateRequest(BaseModel):
    """University moderator escalates an event to the shared human review queue."""

    reason_code: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class EventBulkApproveRequest(BaseModel):
    event_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class EventBulkRejectItem(BaseModel):
    id: uuid.UUID
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)


class EventBulkRejectRequest(BaseModel):
    items: list[EventBulkRejectItem] = Field(min_length=1, max_length=100)
