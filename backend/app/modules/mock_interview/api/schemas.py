"""Request schemas for the mock-interview API (Pydantic v2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.modules.mock_interview.application import caps
from app.modules.mock_interview.domain.models import (
    MODALITY_TEXT,
    MODALITY_VOICE,
    SPEAKER_CANDIDATE,
    SPEAKER_INTERVIEWER,
)

_MODALITY_PATTERN = r"^(voice|text|realtime)$"


class CreateSessionRequest(BaseModel):
    job_id: uuid.UUID
    cv_id: uuid.UUID | None = None
    modality: str = Field(default=MODALITY_VOICE, pattern=_MODALITY_PATTERN)
    locale: str = Field(default="vi", max_length=8)


class TurnRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=caps.MAX_ANSWER_CHARS)


class TurnItem(BaseModel):
    speaker: str = Field(
        ..., pattern=rf"^({SPEAKER_INTERVIEWER}|{SPEAKER_CANDIDATE})$"
    )
    text: str = Field(..., min_length=1, max_length=caps.MAX_ANSWER_CHARS)


class RecordTurnsRequest(BaseModel):
    turns: list[TurnItem] = Field(default_factory=list, max_length=caps.MAX_TURNS_PERSISTED)


class EndSessionRequest(BaseModel):
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)
    turns: list[TurnItem] | None = Field(default=None, max_length=caps.MAX_TURNS_PERSISTED)


class ShareRequest(BaseModel):
    opt_in: bool


# Re-exported for callers that want the accepted text modality without importing
# domain constants.
TEXT_MODALITY = MODALITY_TEXT
