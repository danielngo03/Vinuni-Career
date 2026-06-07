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
MOCK_DIR = DATA_DIR / "mock"

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    jobs_dir: Path = JOBS_DIR
    mock_students_path: Path = MOCK_DIR / "students.json"
    strong_match_threshold: float = float(os.getenv("STRONG_MATCH_THRESHOLD", "0.8"))
    partial_match_threshold: float = float(os.getenv("PARTIAL_MATCH_THRESHOLD", "0.6"))


settings = Settings()
