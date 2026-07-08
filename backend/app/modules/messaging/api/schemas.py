"""Pydantic request schemas for messaging (HTTP validation only)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CreateThreadBody(BaseModel):
    kind: str = Field(default="direct")
    context_type: str | None = Field(default=None)
    context_id: uuid.UUID | None = Field(default=None)
    # Optional: a partner opening an ``application``-context thread omits this — the
    # service resolves the recipient from the application (the masked applicant) and
    # never requires the partner to pass the student's identity. The service rejects
    # an empty list when the context does NOT resolve a recipient.
    recipient_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    subject: str | None = Field(default=None, max_length=300)
    first_message: str | None = Field(default=None, max_length=8000)


class SendMessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    reply_to_id: uuid.UUID | None = Field(default=None)
    client_dedupe_key: str | None = Field(default=None, max_length=120)


class MuteBody(BaseModel):
    muted: bool = Field(default=True)


class ReportBody(BaseModel):
    reason: str | None = Field(default=None, max_length=50)
