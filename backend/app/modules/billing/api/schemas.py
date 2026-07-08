"""Pydantic request schemas for the billing API.

HTTP validation only; vocabulary checks against ``domain.lifecycle``, audience
matching, ownership, and business rules live in the services.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionRequest(BaseModel):
    """Request a paid plan (self-service)."""

    plan_id: uuid.UUID


class SubscriptionCancelRequest(BaseModel):
    version: int | None = None


class MarkPaidRequest(BaseModel):
    payment_reference: str = Field(min_length=1, max_length=120)
    version: int | None = None


class AdminCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class PlanCreateRequest(BaseModel):
    """Create a university-managed subscription plan."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    name_en: str = Field(min_length=2, max_length=120)
    audience: str = Field(min_length=3, max_length=20)
    billing_period: str = Field(default="monthly", min_length=3, max_length=20)
    duration_days: int = Field(default=30, ge=1, le=3660)
    price_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="VND", min_length=3, max_length=5)
    limits: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    is_visible: bool = True
    sort_order: int = Field(default=0, ge=-32768, le=32767)


class PlanUpdateRequest(BaseModel):
    """Patch a plan. Omitted fields remain unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    name_en: str | None = Field(default=None, min_length=2, max_length=120)
    billing_period: str | None = Field(default=None, min_length=3, max_length=20)
    duration_days: int | None = Field(default=None, ge=1, le=3660)
    price_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=5)
    limits: dict[str, Any] | None = None
    is_default: bool | None = None
    is_visible: bool | None = None
    sort_order: int | None = Field(default=None, ge=-32768, le=32767)
