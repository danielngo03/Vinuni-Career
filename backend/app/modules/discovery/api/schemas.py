"""Request schemas for the discovery analytics endpoints.

The schemas accept ONLY the defined fields — there is no free-form bag that could
carry PII into an event. ``signal_tags`` is an optional coarse-signal bag that is
re-sanitized against the allowlist in the service layer before any storage; the
``scope`` of an event is derived server-side and is never accepted from the client.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryEventRequest(BaseModel):
    """A single privacy-safe discovery analytics event."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(
        ...,
        description=(
            "impression|click|view|apply_start|save_intent|event_register_intent"
        ),
    )
    source_surface: str = Field(
        ..., description="Inventory-classed surface, e.g. homepage_recommended"
    )
    target_type: str = Field(..., description="job|event|company|banner")
    target_id: uuid.UUID
    placement_id: uuid.UUID | None = Field(
        default=None,
        description="Sponsored placement ref; retained ONLY on sponsored surfaces.",
    )
    idempotency_key: str = Field(..., min_length=8, max_length=120)
    locale: str | None = Field(default=None, max_length=10)
    # Optional coarse signals to merge onto the session. Re-sanitized server-side
    # against the allowlist — only allowlisted keys survive.
    signal_tags: dict | None = Field(default=None)


class DiscoverySessionResetRequest(BaseModel):
    """Clear stored coarse signals; optionally opt out of personalization."""

    model_config = ConfigDict(extra="forbid")

    opt_out: bool = Field(default=False)
