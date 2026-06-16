from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AcademicRecordEvent(BaseModel):
    student_code: str = Field(min_length=1, max_length=80)
    org_id: str
    records: list[dict[str, Any]]


class WebhookAck(BaseModel):
    accepted: bool
    event_type: str
