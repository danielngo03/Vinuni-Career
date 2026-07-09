"""AI assistant API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1500)


class CreateSessionRequest(BaseModel):
    pass


class UpdateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
