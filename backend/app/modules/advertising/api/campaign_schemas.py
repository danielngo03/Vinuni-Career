"""Pydantic request schemas for the campaign allocation-engine API (spec §7.0).

HTTP validation only; vocabulary checks (objective/pacing/surface), coarse
targeting allowlisting, ownership validation, and business rules live in the
services.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreativeInput(BaseModel):
    headline: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=600)
    image_ref: str | None = Field(default=None, max_length=500)
    click_target: str | None = Field(default=None, max_length=500)
    alt_vi: str | None = Field(default=None, max_length=300)
    alt_en: str | None = Field(default=None, max_length=300)


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(max_length=30)
    surface: str = Field(max_length=40)
    budget_amount: str | float | int
    pacing: str = Field(default="even", max_length=10)
    start_at: datetime
    end_at: datetime
    # Coarse allowlisted targeting only (validated in the service; GPS/sensitive
    # dimensions are rejected 422). Empty = broad (untargeted).
    targeting: dict[str, Any] | None = None
    creative: CreativeInput | None = None
    target_type: str | None = Field(default=None, max_length=12)
    target_id: uuid.UUID | None = None
    disclosure_confirmed: bool = False


class CampaignUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    objective: str | None = Field(default=None, max_length=30)
    surface: str | None = Field(default=None, max_length=40)
    budget_amount: str | float | int | None = None
    pacing: str | None = Field(default=None, max_length=10)
    start_at: datetime | None = None
    end_at: datetime | None = None
    targeting: dict[str, Any] | None = None
    creative: CreativeInput | None = None
    target_type: str | None = Field(default=None, max_length=12)
    target_id: uuid.UUID | None = None
    disclosure_confirmed: bool | None = None
    version: int | None = None


class CampaignSubmitRequest(BaseModel):
    disclosure_confirmed: bool | None = None
    version: int | None = None


class CampaignVersionRequest(BaseModel):
    version: int | None = None


class CampaignReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class CampaignApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class CampaignRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)
    version: int | None = None


class CampaignMarkPaidRequest(BaseModel):
    payment_reference: str = Field(min_length=1, max_length=120)
    version: int | None = None


class CampaignDisclosureClassRequest(BaseModel):
    disclosure_class: str = Field(max_length=20)
    version: int | None = None


class DeliveryEventRequest(BaseModel):
    """Privacy-safe delivery event — NO PII/GPS/raw IP; only the coarse target."""

    campaign_id: uuid.UUID
    slot_code: str = Field(max_length=60)
    event_type: str = Field(max_length=20)  # impression|click|apply_start|register_intent
