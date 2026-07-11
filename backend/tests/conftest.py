"""Shared test fixtures.

The whole suite runs WITHOUT real provider keys and WITHOUT requiring Redis or
Postgres: a temporary SQLite file backs the ORM so all connections share state.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Point the app at a temporary file-backed SQLite DB BEFORE importing app code.
_TMP_DIR = tempfile.mkdtemp(prefix="vinuni_test_")
_DB_PATH = Path(_TMP_DIR) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
# --- Test environment isolation (docs/ENVIRONMENT.md, testing.md) -----------
# Tests MUST NOT depend on backend/.env real-call settings or alias overrides.
# Pin all AI-relevant env vars here so test behaviour is deterministic regardless
# of what the developer has set in backend/.env.
os.environ["AI_REAL_CALLS_ENABLED"] = "false"
os.environ["AI_DEFAULT_MODEL_ALIAS"] = "chat_default"  # pin the function slots
os.environ["AI_REASONING_MODEL_ALIAS"] = "reasoning_default"
os.environ["AI_EMBEDDING_MODEL_ALIAS"] = "embedding_default"
os.environ["AI_RERANK_MODEL_ALIAS"] = "rerank_default"
os.environ["AI_EVAL_MODEL_ALIAS"] = "eval_default"
os.environ["AI_DAILY_COST_LIMIT_USD"] = "1.00"
os.environ["OPENROUTER_API_KEY"] = "replace-with-local-key"  # placeholder → key_configured False
os.environ["CV_LLM_STRUCTURING_ENABLED"] = "false"
os.environ["AUDIT_LOG_ENABLED"] = "true"

from app.core.config import get_settings  # noqa: E402
from app.core.db import dispose_engine, get_engine, get_sessionmaker  # noqa: E402
from app.core.metadata import import_all_models, target_metadata  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
async def _create_schema() -> AsyncIterator[None]:
    import_all_models()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(target_metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_tables(_create_schema: None) -> AsyncIterator[None]:
    """Truncate all tables after each test for cross-test isolation.

    The schema is created once per session; services commit their own
    transactions, so committed rows would otherwise leak between tests.
    """

    yield
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for table in reversed(target_metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest.fixture
async def db_session() -> AsyncIterator:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
