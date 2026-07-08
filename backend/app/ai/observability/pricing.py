"""DB-backed cost estimation for AI gateway calls.

Provides a two-tier cost resolution strategy:

1. Primary: look up the ``(provider, model)`` pair in ``ai_model_price``.
   When a matching active row exists, compute cost from real per-1k token
   prices stored there by an admin.

2. Fallback: delegate to the existing alias-based ``estimate_cost_usd``
   estimator in ``cost_estimator.py``, which uses conservative hardcoded
   per-1M prices keyed by gateway alias. The fallback always returns a
   value (never raises), and the caller is told the result is unpriced so
   it can log accordingly.

Never surfaced to end users — internal cost-accounting and observability only.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.cost_estimator import estimate_cost_usd
from app.ai.observability.models import AiModelPrice

# Conservative chars-per-token approximation (mirrors cost_estimator.py).
_CHARS_PER_TOKEN = 4.0


async def resolve_price(
    session: AsyncSession, provider: str, model: str
) -> AiModelPrice | None:
    """Return the active price row for ``(provider, model)``, or ``None``."""
    row = await session.scalar(
        select(AiModelPrice).where(
            AiModelPrice.provider == provider,
            AiModelPrice.model == model,
            AiModelPrice.active.is_(True),
        )
    )
    return row


async def estimate_cost_usd_db(
    session: AsyncSession,
    *,
    provider: str | None,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float | None, bool]:
    """Return ``(cost_usd, unpriced)`` for one LLM call.

    ``unpriced`` is ``False`` when a DB price row was used (accurate),
    ``True`` when the alias-based fallback estimator was used instead.

    The fallback is always attempted so this function never raises — callers
    can safely log the result without a try/except.
    """
    if provider and model:
        price = await resolve_price(session, provider, model)
        if price is not None:
            cost = (prompt_tokens / 1000.0) * float(price.input_usd_per_1k) + (
                completion_tokens / 1000.0
            ) * float(price.output_usd_per_1k)
            return round(cost, 7), False

    # Fallback: reuse the existing char-based estimator (alias-agnostic).
    approx = estimate_cost_usd(
        model or "unknown",
        prompt_chars=int(prompt_tokens * _CHARS_PER_TOKEN),
        completion_chars=int(completion_tokens * _CHARS_PER_TOKEN),
    )
    return round(approx, 7), True
