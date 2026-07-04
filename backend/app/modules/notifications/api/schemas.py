"""Request schemas for the notification-template admin API.

See ``docs/API_CONTRACTS.md`` Notifications section and
``docs.NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §4 (Template Builder).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NotificationTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=2, max_length=150)
    channel: str = Field(min_length=2, max_length=20)
    locale: str = Field(min_length=2, max_length=5)
    subject: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1)
    variables_schema: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class NotificationTemplateUpdateRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    variables_schema: dict | None = None

    model_config = ConfigDict(extra="forbid")


class NotificationTemplatePreviewRequest(BaseModel):
    sample_variables: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
