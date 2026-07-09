import pytest
from app.ai.observability import pricing
from app.ai.observability.models import AiModelPrice


@pytest.mark.asyncio
async def test_priced_model_computes_from_db(db_session):
    db_session.add(
        AiModelPrice(
            provider="openrouter",
            model="deepseek/deepseek-v4-flash",
            input_usd_per_1k=0.001,
            output_usd_per_1k=0.002,
            active=True,
        )
    )
    await db_session.flush()
    cost, unpriced = await pricing.estimate_cost_usd_db(
        db_session,
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    assert unpriced is False
    assert cost == pytest.approx(0.001 * 1 + 0.002 * 0.5)  # 0.002


@pytest.mark.asyncio
async def test_unpriced_model_flags_and_falls_back(db_session):
    cost, unpriced = await pricing.estimate_cost_usd_db(
        db_session,
        provider="x",
        model="unknown-model",
        prompt_tokens=1000,
        completion_tokens=0,
    )
    assert unpriced is True
    assert cost is not None  # best-effort fallback, never crashes
