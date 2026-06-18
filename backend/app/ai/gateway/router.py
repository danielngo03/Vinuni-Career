"""
Model routing: select the right model tier based on task type and risk level.

Routing rules:
  - CLASSIFICATION, EXTRACTION → small model (fast, cheap)
  - SYNTHESIS, REASONING, COACHING → strong model
  - MODERATION → dedicated safety model
  - EMBEDDING → embedding model
  - RERANK → rerank model

The router never calls the provider directly — it returns routing metadata
consumed by the LLMGateway.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.shared.config import settings


class TaskType(StrEnum):
    # Fast, cheap tasks
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    # Medium complexity
    SUMMARIZATION = "summarization"
    COMPARISON = "comparison"
    # High complexity
    SYNTHESIS = "synthesis"
    REASONING = "reasoning"
    COACHING = "coaching"
    REVIEW_COPILOT = "review_copilot"
    # Specialized
    MODERATION = "moderation"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str
    max_tokens: int
    temperature: float
    task_type: TaskType


# Tier definitions — resolved from settings at runtime
_SMALL_TASKS = {
    TaskType.CLASSIFICATION,
    TaskType.EXTRACTION,
    TaskType.VALIDATION,
    TaskType.SUMMARIZATION,
}
_STRONG_TASKS = {
    TaskType.SYNTHESIS,
    TaskType.REASONING,
    TaskType.COACHING,
    TaskType.REVIEW_COPILOT,
    TaskType.COMPARISON,
}


def route_model(task_type: TaskType) -> ModelRoute:
    """Return the appropriate provider + model for a given task type."""
    provider = settings.llm_provider

    if task_type == TaskType.MODERATION:
        return ModelRoute(
            provider="openrouter",
            model=settings.openrouter_safety_model,
            max_tokens=256,
            temperature=0.0,
            task_type=task_type,
        )
    if task_type == TaskType.EMBEDDING:
        return ModelRoute(
            provider=settings.embedding_provider_chain[0] if settings.embedding_provider_chain else provider,
            model=settings.openrouter_embedding_model,
            max_tokens=0,
            temperature=0.0,
            task_type=task_type,
        )
    if task_type == TaskType.RERANK:
        return ModelRoute(
            provider=settings.rerank_provider,
            model=settings.openrouter_rerank_model,
            max_tokens=0,
            temperature=0.0,
            task_type=task_type,
        )
    if task_type in _SMALL_TASKS:
        # Use a smaller/faster model — openai_model is configured for this
        return ModelRoute(
            provider=provider,
            model=settings.llm_model,
            max_tokens=2048,
            temperature=0.0,
            task_type=task_type,
        )
    # Strong model for synthesis/reasoning
    return ModelRoute(
        provider=provider,
        model=settings.llm_model,
        max_tokens=4096,
        temperature=0.3,
        task_type=task_type,
    )
