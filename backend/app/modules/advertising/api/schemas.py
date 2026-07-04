"""Pydantic request schemas for the advertising API.

HTTP validation only; vocabulary checks against ``domain.lifecycle``, ownership
validation, and business rules live in the services.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PlacementCreateRequest(BaseModel):
    target_type: str = Field(max_length=10)  # job | event
    target_id: uuid.UUID
    placement_type: str = Field(max_length=10)  # sponsored | featured | both
    package_id: uuid.UUID
    start_at: datetime
    disclosure_confirmed: bool = False


class PlacementUpdateRequest(BaseModel):
    placement_type: str | None = Field(default=None, max_length=10)
    package_id: uuid.UUID | None = None
    start_at: datetime | None = None
    disclosure_confirmed: bool | None = None
    version: int | None = None


class PlacementSubmitRequest(BaseModel):
    """Submit may also confirm the non-removable disclosure label."""

    disclosure_confirmed: bool | None = None
    version: int | None = None


class PlacementVersionRequest(BaseModel):
    version: int | None = None


class PlacementApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class PlacementRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)
    version: int | None = None


class PlacementEscalateRequest(BaseModel):
    """University moderator escalates a placement to the human review queue."""

    reason_code: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class PlacementBulkApproveRequest(BaseModel):
    placement_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class PlacementBulkRejectItem(BaseModel):
    id: uuid.UUID
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)


class PlacementBulkRejectRequest(BaseModel):
    items: list[PlacementBulkRejectItem] = Field(min_length=1, max_length=100)


class PlacementMarkPaidRequest(BaseModel):
    payment_reference: str = Field(min_length=1, max_length=120)
    version: int | None = None


class PlacementAdminCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class DisclosureClassRequest(BaseModel):
    """University relabel of a placement's public inventory class (spec §4)."""

    disclosure_class: str = Field(max_length=20)
    version: int | None = None


class CreativeReviewRequest(BaseModel):
    """University approve/reject of an uploaded campaign creative (spec §6)."""

    decision: str = Field(max_length=10)  # approve | reject
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None
