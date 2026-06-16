from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    cv_text: str = Field(min_length=1, max_length=80_000)
    job_description: str = Field(min_length=1, max_length=80_000)


class MatchResponse(BaseModel):
    score: float
    matched_skills: list[str]
    missing_skills: list[str]
    reasoning: dict[str, Any]


class ChatMessagePayload(BaseModel):
    role: str = Field(pattern="^(system|developer|user|assistant)$")
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequestPayload(BaseModel):
    messages: list[ChatMessagePayload] = Field(min_length=1, max_length=50)
    model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


class ChatResponsePayload(BaseModel):
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80_000)
    model: str | None = None


class EmbedResponse(BaseModel):
    embedding: list[float]
    provider: str
    model: str
    input_tokens: int


class ProviderStatus(BaseModel):
    chat_chain: list[str]
    embedding_chain: list[str]


class JobPolicyResponse(BaseModel):
    approved: bool
    reasons: list[str]
    trace: dict[str, Any]


class UsageSummary(BaseModel):
    org_id: str
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
