from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CVMaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80_000)


class CVMaskResponse(BaseModel):
    masked_text: str
    entities: list[dict[str, str]]


class CVCreate(BaseModel):
    student_id: str
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = Field(default=None, max_length=80_000)
    is_primary: bool = True


class CVView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    parsed_data: dict[str, Any]
    masked_data: dict[str, Any]
    is_primary: bool
