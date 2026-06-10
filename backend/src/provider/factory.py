"""Provider selection from application settings."""

from __future__ import annotations

from backend.src.core.config import settings
from backend.src.provider.base import LLMProvider, LLMProviderConfig
from backend.src.provider.gemini import GeminiProvider
from backend.src.provider.ollama import OllamaProvider
from backend.src.provider.openai_compatible import OpenAICompatibleProvider


def get_llm_provider() -> LLMProvider:
    provider_name = settings.llm_provider.strip().lower()

    if provider_name == "gemini":
        return GeminiProvider(
            LLMProviderConfig(
                name="gemini",
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.google_api_key,
            )
        )

    if provider_name == "openai":
        return OpenAICompatibleProvider(
            LLMProviderConfig(
                name="openai",
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openai_api_key,
                base_url="https://api.openai.com/v1",
            )
        )

    if provider_name == "openrouter":
        extra_headers = {}
        if settings.openrouter_site_url:
            extra_headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            extra_headers["X-Title"] = settings.openrouter_app_name
        return OpenAICompatibleProvider(
            LLMProviderConfig(
                name="openrouter",
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                site_url=settings.openrouter_site_url,
                app_name=settings.openrouter_app_name,
            ),
            extra_headers=extra_headers,
        )

    if provider_name == "ollama":
        return OllamaProvider(
            LLMProviderConfig(
                name="ollama",
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                base_url=settings.ollama_base_url,
            )
        )

    if provider_name == "custom":
        return OpenAICompatibleProvider(
            LLMProviderConfig(
                name="custom",
                model=settings.custom_llm_model or settings.llm_model,
                temperature=settings.llm_temperature,
                api_key=settings.custom_llm_api_key,
                base_url=settings.custom_llm_base_url,
            )
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
