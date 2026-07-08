"""Repository for the singleton ``ai_settings`` platform row (ADR-0011).

The migration ``0022`` seeds the row on Postgres. On the SQLite unit-test path (no
migrations) and as a startup safety net, :func:`get_or_create_platform` lazily
creates the singleton from current ``config.py`` defaults — idempotent and
behaviour-preserving (the seeded row mirrors env, so nothing changes vs today).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_settings.domain.models import (
    PLATFORM_SCOPE,
    ROLLOUT_ENABLED,
    AiSettings,
)


async def get_platform(session: AsyncSession) -> AiSettings | None:
    """Return the platform settings row, or ``None`` if not yet seeded."""

    return (
        await session.execute(
            select(AiSettings).where(AiSettings.scope == PLATFORM_SCOPE)
        )
    ).scalar_one_or_none()


def _defaults_from_config() -> AiSettings:
    """Build the seed row mirroring ``config.py`` (behaviour-identical to today)."""

    s = get_settings()
    return AiSettings(
        scope=PLATFORM_SCOPE,
        org_id=None,
        # Seed the DB toggle from env so the resolver's AND keeps today's behaviour.
        real_calls_enabled=bool(s.ai_real_calls_enabled),
        rollout_state=ROLLOUT_ENABLED,
        chat_model_alias=s.ai_default_model_alias,
        reasoning_model_alias=s.ai_reasoning_model_alias,
        embedding_model_alias=s.ai_embedding_model_alias,
        rerank_model_alias=s.ai_rerank_model_alias,
        eval_model_alias=s.ai_eval_model_alias,
        cv_llm_structuring_enabled=bool(s.cv_llm_structuring_enabled),
        job_fit_ai_explanation_enabled=True,
        daily_budget_usd=Decimal(str(s.ai_daily_cost_limit_usd)),
        version=1,
    )


async def get_or_create_platform(session: AsyncSession) -> AiSettings:
    """Return the singleton, lazily seeding it from config defaults if absent.

    Commits the seed in its own flush within the caller's transaction; the unique
    constraint on ``scope`` makes a concurrent double-create fail loudly rather
    than duplicate the singleton.
    """

    row = await get_platform(session)
    if row is not None:
        return row
    row = _defaults_from_config()
    session.add(row)
    await session.flush()
    return row
