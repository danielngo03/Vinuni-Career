from __future__ import annotations

from functools import lru_cache

from app.ai.gateway.gateway import LLMGateway
from app.ai.gateway.providers.gemini_native import GeminiNativeProvider
from app.ai.gateway.providers.offline import OfflineProvider
from app.ai.gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.gateway.providers.openrouter import OpenRouterProvider
from app.shared.config import settings


@lru_cache
def get_llm_gateway() -> LLMGateway:
    if settings.ai_gateway_mode == "litellm_proxy" and settings.litellm_proxy_url:
        return _litellm_proxy_gateway()

    return _direct_gateway()


def _direct_gateway() -> LLMGateway:
    gemini_provider = (
        GeminiNativeProvider(
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key,
            chat_model=settings.gemini_model,
            embedding_model=settings.gemini_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        if settings.gemini_api_style == "native"
        else OpenAICompatibleProvider(
            name="gemini",
            base_url=settings.gemini_openai_base_url,
            api_key=settings.gemini_api_key,
            chat_model=settings.gemini_model,
            embedding_model=settings.gemini_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )
    providers = {
        "openrouter": OpenRouterProvider(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            chat_model=settings.openrouter_model,
            chat_model_fallbacks=settings.openrouter_model_fallbacks,
            embedding_model=settings.openrouter_embedding_model,
            rerank_model=settings.openrouter_rerank_model,
            http_referer=settings.openrouter_http_referer,
            app_title=settings.openrouter_app_title,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "openai": OpenAICompatibleProvider(
            name="openai",
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            chat_model=settings.openai_model,
            embedding_model=settings.openai_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "nvidia": OpenAICompatibleProvider(
            name="nvidia",
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
            chat_model=settings.nvidia_model,
            embedding_model=settings.nvidia_embedding_model,
            rerank_model=settings.nvidia_rerank_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "gemini": gemini_provider,
        "offline": OfflineProvider(dimensions=settings.embedding_dimensions),
    }
    return LLMGateway(
        providers=providers,
        chat_chain=settings.llm_provider_chain or [settings.llm_provider],
        embedding_chain=settings.embedding_provider_chain,
        rerank_chain=[settings.rerank_provider, "offline"]
        if settings.rerank_provider != "offline"
        else ["offline"],
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )


def _litellm_proxy_gateway() -> LLMGateway:
    providers = {
        "openrouter": OpenAICompatibleProvider(
            name="openrouter",
            base_url=settings.litellm_proxy_url or "",
            api_key=settings.litellm_api_key,
            chat_model=settings.openrouter_model,
            embedding_model=settings.openrouter_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "openai": OpenAICompatibleProvider(
            name="openai",
            base_url=settings.litellm_proxy_url or "",
            api_key=settings.litellm_api_key,
            chat_model=settings.openai_model,
            embedding_model=settings.openai_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "gemini": OpenAICompatibleProvider(
            name="gemini",
            base_url=settings.litellm_proxy_url or "",
            api_key=settings.litellm_api_key,
            chat_model=settings.gemini_model,
            embedding_model=settings.gemini_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "nvidia": OpenAICompatibleProvider(
            name="nvidia",
            base_url=settings.litellm_proxy_url or "",
            api_key=settings.litellm_api_key,
            chat_model=settings.nvidia_model,
            embedding_model=settings.nvidia_embedding_model,
            rerank_model=settings.nvidia_rerank_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "offline": OfflineProvider(dimensions=settings.embedding_dimensions),
    }
    return LLMGateway(
        providers=providers,
        chat_chain=settings.llm_provider_chain or [settings.llm_provider],
        embedding_chain=settings.embedding_provider_chain,
        rerank_chain=[settings.rerank_provider, "offline"]
        if settings.rerank_provider != "offline"
        else ["offline"],
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )
