"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is installed in normal app runtime.
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
STUDENTS_DIR = DATA_DIR / "students"

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    llm_temperature: float = _env_float("LLM_TEMPERATURE", 0.0)
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_site_url: str | None = os.getenv("OPENROUTER_SITE_URL")
    openrouter_app_name: str | None = os.getenv("OPENROUTER_APP_NAME")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    custom_llm_model: str | None = os.getenv("CUSTOM_LLM_MODEL")
    custom_llm_base_url: str | None = os.getenv("CUSTOM_LLM_BASE_URL")
    custom_llm_api_key: str | None = os.getenv("CUSTOM_LLM_API_KEY")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    rag_top_k: int = _env_int("RAG_TOP_K", 4)
    gemini_api_key: str | None = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", os.getenv("LLM_MODEL", "gemini-3.1-flash-lite"))
    jobs_dir: Path = JOBS_DIR
    students_dir: Path = STUDENTS_DIR
    strong_match_threshold: float = float(os.getenv("STRONG_MATCH_THRESHOLD", "0.8"))
    partial_match_threshold: float = float(os.getenv("PARTIAL_MATCH_THRESHOLD", "0.6"))
    demo_auth_enabled: bool = _env_bool("DEMO_AUTH_ENABLED", True)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
