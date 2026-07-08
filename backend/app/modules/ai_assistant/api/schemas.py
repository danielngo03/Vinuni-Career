"""AI assistant API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1500)
    # Optional UI locale hint ("vi"/"en"/region-tagged). Selects the language of
    # deterministic user-facing assistant text and confirmation-card copy; unknown
    # or omitted values fall back to "vi" (server-side ``normalize_locale``).
    locale: str | None = Field(default=None, max_length=16)


class CreateSessionRequest(BaseModel):
    pass
