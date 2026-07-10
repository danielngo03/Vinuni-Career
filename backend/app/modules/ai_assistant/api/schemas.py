"""AI assistant API request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1500)


class CreateSessionRequest(BaseModel):
    pass


class UpdateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class EditMessageRequest(BaseModel):
    """PATCH .../messages/{id} — replace a user message's text and replay the turn."""

    text: str = Field(..., min_length=1, max_length=1500)


class ConfirmActionRequest(BaseModel):
    """POST .../messages/{id}/confirm body.

    Backward compatible: an omitted/empty body means ``confirm`` (the historical
    behaviour); ``cancel`` resolves the pending card without executing anything.
    """

    decision: Literal["confirm", "cancel"] = "confirm"
