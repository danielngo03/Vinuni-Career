"""Energy settlement — the single charge choke point for every AI call.

``AiTaskRunner._record_billable`` calls :func:`charge` for every terminal
outcome (``success`` / ``blocked`` / ``provider_failed`` / ``validation_failed``
/ ``cached``). This module is deliberately thin: it owns the *product* decision
of "how much masked energy does this feature cost", then delegates the durable,
idempotent write to :func:`app.ai.observability.billable_usage.record_billable_usage`
— the ledger that is the source of truth for plan/package credit limits
(``docs/PRODUCT_OPERATING_MODEL.md`` §3).

Design contract (must not regress):
- **One settlement point.** All energy accounting flows through :func:`charge`;
  no call site writes ``ai_billable_usage`` directly.
- **Charge only on success.** ``base_units`` are derived here from the per-feature
  weight table; the ledger's ``units_for`` rule then bills them only on a
  chargeable (success) result and records 0 for blocked/failed/cached (still
  useful for attribution + provider-cost accounting).
- **Idempotent.** When ``ctx.idempotency_key`` is set, a retry / Celery
  redelivery / cache reuse never double-charges (enforced by the ledger's unique
  constraint + savepoint).
- **No leakage.** Energy is a masked product unit — never a provider/model name,
  token count, prompt, or raw cost. The student meter reads back through
  :func:`app.ai.observability.billable_usage.billable_summary` (a derived %),
  never the USD cost.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    FEATURE_COVER_LETTER,
    FEATURE_CV_EDIT_COMMAND,
    FEATURE_CV_EXTRACTION,
    FEATURE_CV_FIT_EXPLANATION,
    FEATURE_CV_SUGGESTION,
    FEATURE_EMBEDDINGS,
    FEATURE_INTERVIEW_SIM,
    FEATURE_JD_EXTRACTION,
    FEATURE_JD_WRITER,
    FEATURE_LEARNING_PLAN,
    FEATURE_RERANK,
    FEATURE_SCORECARD_SUGGESTION,
    FEATURE_SCREENING_BRIEF,
    UsageContext,
    record_billable_usage,
)
from app.ai.observability.models import AiBillableUsage

# --------------------------------------------------------------------------- #
# Per-feature energy weight (masked product units charged on a SUCCESSFUL call) #
# --------------------------------------------------------------------------- #
# Kept as a single table so call sites never hardcode a cost and the whole
# taxonomy is auditable in one place. Heavier / multi-turn tasks cost more;
# background helpers (embeddings, rerank) cost the user nothing but are still
# recorded (0 units) for provider-cost attribution.
_DEFAULT_UNIT_WEIGHT = 1

_FEATURE_UNIT_WEIGHTS: dict[str, int] = {
    FEATURE_CHATBOT: 1,
    FEATURE_CV_EXTRACTION: 2,
    FEATURE_CV_SUGGESTION: 1,
    FEATURE_CV_EDIT_COMMAND: 1,
    FEATURE_CV_FIT_EXPLANATION: 1,
    FEATURE_COVER_LETTER: 2,
    FEATURE_INTERVIEW_SIM: 3,
    FEATURE_LEARNING_PLAN: 2,
    FEATURE_JD_EXTRACTION: 2,
    FEATURE_JD_WRITER: 2,
    FEATURE_SCREENING_BRIEF: 2,
    FEATURE_SCORECARD_SUGGESTION: 1,
    FEATURE_EMBEDDINGS: 0,
    FEATURE_RERANK: 0,
}


def feature_unit_weight(feature_key: str) -> int:
    """Masked energy units a successful call to ``feature_key`` costs the user."""

    return _FEATURE_UNIT_WEIGHTS.get(feature_key, _DEFAULT_UNIT_WEIGHT)


async def charge(
    db: AsyncSession,
    *,
    ctx: UsageContext,
    result_status: str,
    provider_cost_usd: float | None = None,
) -> AiBillableUsage:
    """Settle one AI call: write the idempotent ``ai_billable_usage`` row.

    ``base_units`` come from the per-feature weight table keyed by
    ``ctx.feature_key``; the ledger applies the charging rule (bill only on a
    successful result). Returns the persisted (or pre-existing, on an idempotent
    retry) ledger row. The caller owns the surrounding transaction/commit and
    already savepoint-isolates + swallows any error, so this stays a plain
    delegation with no extra error handling of its own.
    """

    return await record_billable_usage(
        db,
        ctx=ctx,
        result_status=result_status,
        base_units=feature_unit_weight(ctx.feature_key),
        provider_cost_usd=provider_cost_usd,
    )
