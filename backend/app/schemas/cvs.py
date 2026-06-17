from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CVMaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80_000)


class CVMaskResponse(BaseModel):
    masked_text: str
    entities: list[dict[str, str]]


class CVRawParseRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=80_000)
    student_id: str | None = Field(default=None, max_length=120)


class CVFormParseRequest(BaseModel):
    student_id: str | None = Field(default=None, max_length=120)
    target_position: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=120)
    education: str | None = Field(default=None, max_length=10_000)
    experience: str | None = Field(default=None, max_length=30_000)
    projects: str | None = Field(default=None, max_length=30_000)
    skills: list[str] = Field(default_factory=list)
    raw_notes: str | None = Field(default=None, max_length=20_000)


class CVParsedSkill(BaseModel):
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]


class CVWorkExperience(BaseModel):
    title: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=160)
    duration: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=500)
    score: float = Field(default=0, ge=0, le=10)
    score_reason: str = Field(default="", max_length=300)


class CVEducation(BaseModel):
    degree: str = Field(default="", max_length=180)
    institution: str = Field(default="", max_length=180)
    year: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=500)
    score: float = Field(default=0, ge=0, le=10)
    score_reason: str = Field(default="", max_length=300)


class CVProfileHighlights(BaseModel):
    work_experience_indexes: list[int] = Field(default_factory=list)
    education_indexes: list[int] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)


class CVParseMetadata(BaseModel):
    source: str
    cv_text_excerpt: str
    parser_mode: str
    llm_used: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    provider_chain: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    error_status_code: int | None = None
    error_code: str | None = None
    error: str | None = None


class CVParseResponse(BaseModel):
    student_id: str
    target_position: str
    work_experience: list[CVWorkExperience] = Field(default_factory=list)
    education: list[CVEducation] = Field(default_factory=list)
    profile_highlights: CVProfileHighlights = Field(default_factory=CVProfileHighlights)
    skills: dict[str, CVParsedSkill]
    metadata: CVParseMetadata


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
