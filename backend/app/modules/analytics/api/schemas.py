"""Request schemas for the partner-analytics API surface.

Kept in this module's own ``api/schemas.py`` (not the sibling B-548
``analytics_events`` slice, which has no public HTTP surface yet).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_ALLOWED_EVENT_TYPES = {"impression", "cta_click", "share_click"}
_ALLOWED_SOURCES = {"organic", "search", "recommendation", "sponsored", "invitation", "direct"}


class JobEngagementRequest(BaseModel):
    """Body for ``POST /analytics/jobs/{job_id}/engagement``.

    Only client-observable engagement signals that have no other authoritative
    backend write to hang off of (a genuine detail view / save / apply already
    get recorded server-side at their own endpoint). ``extra="forbid"`` — a
    stray field is a ``422``, never silently stored.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(..., description="impression | cta_click | share_click")
    source: str | None = Field(
        default=None, description="organic|search|recommendation|sponsored|invitation|direct"
    )
