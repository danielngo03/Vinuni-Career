from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infra.llm_gateway.gateway import LLMGateway
from app.infra.llm_gateway.providers.gemini_native import GeminiNativeProvider
from app.infra.llm_gateway.providers.offline import OfflineProvider
from app.infra.llm_gateway.providers.openai_compatible import OpenAICompatibleProvider


@lru_cache
def get_llm_gateway() -> LLMGateway:
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
        "openai": OpenAICompatibleProvider(
            name="openai",
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            chat_model=settings.openai_model,
            embedding_model=settings.openai_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "gemini": gemini_provider,
        "local": OpenAICompatibleProvider(
            name="local",
            base_url=settings.local_base_url,
            api_key=None,
            chat_model=settings.local_model,
            embedding_model=settings.local_embedding_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        "offline": OfflineProvider(dimensions=settings.embedding_dimensions),
    }
    return LLMGateway(
        providers=providers,
        chat_chain=settings.llm_provider_chain or [settings.llm_provider],
        embedding_chain=settings.embedding_provider_chain,
        max_retries=settings.llm_max_retries,
    )
