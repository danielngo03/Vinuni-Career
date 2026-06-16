from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "C2 Career Platform"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    secret_key: str = Field(
        default="change-me-in-production-please-use-64-random-chars",
        min_length=32,
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14
    enforce_rbac: bool = False
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    backend_cors_origins: Annotated[list[str | AnyHttpUrl], NoDecode] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]

    llm_provider: Literal["offline", "openai", "gemini", "local"] = "offline"
    llm_provider_chain: Annotated[list[str], NoDecode] = ["offline"]
    llm_model: str = "gpt-5.4-nano"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-nano"
    openai_embedding_model: str = "text-embedding-3-small"

    gemini_api_key: str | None = None
    gemini_api_style: Literal["native", "openai_compatible"] = "native"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "gemini-embedding-2-preview"

    local_base_url: str = "http://localhost:11434/v1"
    local_model: str = "qwen3:14b"
    local_embedding_model: str = "nomic-embed-text-v2-moe"

    scalar_docs_enabled: bool = True
    scalar_docs_path: str = "/scalar"

    embedding_provider_chain: Annotated[list[str], NoDecode] = ["offline"]
    embedding_dimensions: int = 32
    ai_daily_org_token_limit: int = 200_000

    cache_backend: Literal["memory", "redis"] = "memory"
    cache_default_ttl_seconds: int = 300

    search_backend: Literal["memory", "opensearch", "elasticsearch"] = "memory"
    search_url: str | None = None
    search_api_key: str | None = None
    search_username: str | None = None
    search_password: str | None = None
    search_index_prefix: str = "c2"

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "./.data/uploads"
    storage_public_base_url: str = "http://localhost:8000/files"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    webhook_shared_secret: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
