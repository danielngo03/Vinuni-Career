from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Vinuni Career Platform"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_timezone: str = "Asia/Bangkok"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    secret_key: str = Field(
        default="change-me-in-production-please-use-64-random-chars",
        min_length=32,
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    enforce_rbac: bool = True
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/vinuni_career"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    workflow_backend: Literal["local", "celery", "temporal"] = "local"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "vinuni-career"

    backend_cors_origins: Annotated[list[str | AnyHttpUrl], NoDecode] = [
        "http://localhost:3000",
    ]

    llm_provider: Literal["offline", "openai", "gemini", "groq", "openrouter", "nvidia"] = (
        "nvidia"
    )
    llm_provider_chain: Annotated[list[str], NoDecode] = ["nvidia", "offline"]
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 0.35

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-nano"
    openai_embedding_model: str = "text-embedding-3-small"

    gemini_api_key: str | None = None
    gemini_api_keys: Annotated[list[str], NoDecode] = []
    gemini_api_style: Literal["native", "openai_compatible"] = "native"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2-preview"

    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_embedding_model: str | None = None

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str | None = "http://localhost:3000"
    openrouter_app_title: str = "VinUni Career Platform"
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_model_fallbacks: Annotated[list[str], NoDecode] = [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "google/gemma-4-31b-it:free",
        "google/gemma-4-26b-a4b-it:free",
        "nex-agi/nex-n2-pro:free",
    ]
    openrouter_safety_model: str = "nvidia/nemotron-3.5-content-safety:free"
    openrouter_embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    openrouter_rerank_model: str = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"

    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nvidia_embedding_model: str = "nv-embedqa-e5-v5"
    nvidia_rerank_model: str = "nv-rerankqa-mistral-4b-v3"

    scalar_docs_enabled: bool = True
    scalar_docs_path: str = "/scalar"

    ai_gateway_mode: Literal["direct", "litellm_proxy"] = "direct"
    litellm_proxy_url: str | None = None
    litellm_api_key: str | None = None
    vision_extraction_provider: Literal["gemini", "openai", "openrouter", "offline"] = "gemini"
    vision_extraction_model: str = "gemini-3.5-flash"
    structured_extraction_enabled: bool = True
    max_extraction_retries: int = 2
    semantic_cache_enabled: bool = True
    guardrails_enabled: bool = True
    rerank_provider: Literal["offline", "openrouter", "cohere", "flashrank", "nvidia"] = "nvidia"
    cohere_api_key: str | None = None
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    embedding_provider_chain: Annotated[list[str], NoDecode] = ["nvidia", "offline"]
    embedding_dimensions: int = 32
    ai_daily_org_token_limit: int = 200_000

    cache_backend: Literal["memory", "redis"] = "memory"
    cache_default_ttl_seconds: int = 300

    search_backend: Literal["memory", "opensearch", "elasticsearch"] = "memory"
    search_url: str | None = None
    search_api_key: str | None = None
    search_username: str | None = None
    search_password: str | None = None
    search_index_prefix: str = "vinuni"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./.data/uploads"
    storage_public_base_url: str = "http://localhost:8000/files"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    webhook_shared_secret: str | None = None
    internal_service_token: str | None = None

    oidc_backend_callback_base: str = "http://localhost:8000/api/v1/auth/oidc"
    oidc_frontend_callback_url: str = "http://localhost:3000/api/auth/oidc/callback"
    google_oidc_client_id: str | None = None
    google_oidc_client_secret: str | None = None
    google_oidc_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )
    microsoft_oidc_client_id: str | None = None
    microsoft_oidc_client_secret: str | None = None
    microsoft_oidc_tenant: str = "common"

    max_upload_mb: int = 20
    signed_url_ttl_seconds: int = 900

    @field_validator("api_v1_prefix")
    @classmethod
    def normalize_prefix(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes"}:
                return True
        return value

    @field_validator(
        "backend_cors_origins",
        "llm_provider_chain",
        "embedding_provider_chain",
        "gemini_api_keys",
        "openrouter_model_fallbacks",
        mode="before",
    )
    @classmethod
    def parse_list_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


def get_gemini_api_keys() -> list[str]:
    values = _collect_dotenv_values()
    values.update(os.environ)
    return _dedupe_keys(
        [
            *_parse_key_list(values.get("GEMINI_API_KEYS")),
            *_parse_key_list(values.get("GEMINI_API_KEY")),
        ]
    )


def _collect_dotenv_values() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    paths = [Path.cwd() / ".env", root / ".env", root / "backend" / ".env"]
    values: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            values[key.strip()] = _clean_dotenv_value(raw_value)
    return values


def _clean_dotenv_value(value: str) -> str:
    stripped = value.strip()
    if " #" in stripped:
        stripped = stripped.split(" #", 1)[0].strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _parse_key_list(value: str | None) -> list[str]:
    if not value:
        return []
    stripped = value.strip()
    if stripped.startswith("["):
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON list of API keys")
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_keys(values: list[str | None]) -> list[str]:
    keys = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        if normalized and normalized not in seen:
            keys.append(normalized)
            seen.add(normalized)
    return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
