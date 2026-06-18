"""
app/ai/gateway — LLM provider chain with circuit breaker and model routing.

This is the canonical location (moved from app.ai.gateway).
Backward-compat: app.ai.gateway.* still resolves via shim.

Key features:
  - Provider chain with ordered fallback
  - Per-provider circuit breaker (CLOSED → OPEN → HALF_OPEN)
  - Task-type routing: small model for extraction, strong model for synthesis
  - Token and cost budget enforcement
  - Retry with exponential backoff and jitter
"""
from __future__ import annotations

from app.ai.gateway.circuit_breaker import CircuitBreaker, CircuitState
from app.ai.gateway.factory import get_llm_gateway
from app.ai.gateway.gateway import LLMGateway
from app.ai.gateway.router import TaskType, route_model
from app.ai.gateway.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingResponse,
    RerankRequest,
    RerankResponse,
)

__all__ = [
    "LLMGateway",
    "get_llm_gateway",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "EmbeddingResponse",
    "RerankRequest",
    "RerankResponse",
    "CircuitBreaker",
    "CircuitState",
    "route_model",
    "TaskType",
]
