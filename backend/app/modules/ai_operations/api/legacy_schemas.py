from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class RerankRequestPayload(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    documents: list[str] = Field(min_length=1, max_length=100)
    top_n: int = Field(default=5, ge=1, le=50)
    model: str | None = None


class RerankResultPayload(BaseModel):
    index: int
    text: str
    relevance_score: float


class RerankResponsePayload(BaseModel):
    results: list[RerankResultPayload]
    provider: str
    model: str
    input_tokens: int


class ProviderStatus(BaseModel):
    chat_chain: list[str]
    embedding_chain: list[str]
    rerank_chain: list[str]


class JobPolicyResponse(BaseModel):
    approved: bool
    reasons: list[str]
    trace: dict[str, Any]


class JobPolicyRequest(BaseModel):
    job_id: str | None = None
    job_description: str | None = Field(default=None, min_length=20, max_length=50_000)


class AIUsageLogView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    user_id: str | None
    feature_name: str
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    raw_usage: dict[str, Any] | None = None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime


class UsageSummary(BaseModel):
    org_id: str
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
