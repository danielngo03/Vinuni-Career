"""ensure_defaults seeds the six *_default slot bindings from config (P1.3)."""

from __future__ import annotations

import pytest
from app.ai.gateway import provider_registry
from app.ai.gateway.provider_models import AiModelAlias
from sqlalchemy import select

_SLOTS = {
    "chat_default": "deepseek/deepseek-v4-flash",
    "reasoning_default": "deepseek/deepseek-r1",
    "embedding_default": "text-embedding-3-small",
    "rerank_default": "deepseek/deepseek-v4-flash",
    "eval_default": "deepseek/deepseek-v4-flash",
    "vision_default": "google/gemini-2.5-flash",
}


@pytest.mark.asyncio
async def test_seed_creates_default_slots(db_session) -> None:
    await provider_registry.ensure_defaults(db_session)
    await db_session.flush()
    rows = (await db_session.execute(select(AiModelAlias))).scalars().all()
    by_name = {r.alias_name: r for r in rows}
    for slot, model_id in _SLOTS.items():
        assert slot in by_name, f"{slot} not seeded"
        assert by_name[slot].model_id == model_id
        assert by_name[slot].is_builtin is True


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session) -> None:
    await provider_registry.ensure_defaults(db_session)
    await db_session.flush()
    await provider_registry.ensure_defaults(db_session)
    await db_session.flush()
    rows = (
        (
            await db_session.execute(
                select(AiModelAlias).where(AiModelAlias.alias_name == "chat_default")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
