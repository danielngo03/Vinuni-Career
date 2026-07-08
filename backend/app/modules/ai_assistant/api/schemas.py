"""AI assistant API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1500)


class CreateSessionRequest(BaseModel):
    pass


class RenameSessionRequest(BaseModel):
    """Rename a chat session. The service strips + re-validates 1..120 chars."""

    title: str = Field(..., min_length=1, max_length=120)


class EditMessageRequest(BaseModel):
    """Edit a sent USER message; the service re-runs the assistant from it."""

    text: str = Field(..., min_length=1, max_length=1500)
