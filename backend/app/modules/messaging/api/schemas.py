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
    # Messaging V2 targets (mutually exclusive with recipient_ids by precedence):
    # ``target_org_id`` — initiate to an org Page (student→partner/uni, partner→uni);
    # ``target_department_id`` — internal department channel (same org, staff only).
    target_org_id: uuid.UUID | None = Field(default=None)
    target_department_id: uuid.UUID | None = Field(default=None)
    subject: str | None = Field(default=None, max_length=300)
    first_message: str | None = Field(default=None, max_length=8000)


class SendMessageBody(BaseModel):
    # Empty body is allowed ONLY when the message carries attachments (image/file-only
    # messages). The service rejects a blank body with no attachments.
    body: str = Field(default="", max_length=8000)
    reply_to_id: uuid.UUID | None = Field(default=None)
    client_dedupe_key: str | None = Field(default=None, max_length=120)
    # Messaging V2: optionally bind previously-uploaded attachments to this message.
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class MuteBody(BaseModel):
    muted: bool = Field(default=True)


class ReportBody(BaseModel):
    reason: str | None = Field(default=None, max_length=50)


class AssignThreadBody(BaseModel):
    department_id: uuid.UUID | None = Field(default=None)
    assignee_id: uuid.UUID | None = Field(default=None)


class ResolveThreadBody(BaseModel):
    resolved: bool = Field(default=True)
