"""Reusable AI usage governance for provider call-sites that keep their own
provider/message handling but must still ride the full usage-aware path.

``AiTaskRunner`` (``task_runner.py``) remains the preferred single entry point.
A few call-sites deliberately cannot route through it:

- ``app.ai.cv.llm`` keeps ``get_provider()`` because that symbol is an eval /
  test patch point (the offline fallback harness swaps it for a down provider),
  and it must NOT run input-policy sanitisation so offline outputs stay
  byte-identical for the deterministic eval datasets.
- the extraction vision / structuring adapters post to the provider over raw
  ``httpx`` for the image/scanned path.

Historically those paths bypassed budget/ledger/observability entirely. This
module gives them the same three governance steps ``AiTaskRunner`` applies —
**budget pre-check**, **durable cost ledger** (idempotent, no double-charge),
and **ops telemetry** (Langfuse + ``ai_ops_event``) — without changing their
provider/message handling.

Every helper is a no-op-safe degrade: with ``usage is None`` or ``usage.db is
None`` it emits only the metadata log line, exactly matching the pre-existing
behaviour, so adopting it at a call-site is never a breaking change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.gateway.usage_context import AiUsageContext

# Char->token approximation, matching AiTaskRunner / cost_estimator conventions.
_CHARS_PER_TOKEN = 4.0


async def precheck_budget(
    usage: AiUsageContext | None,
    *,
    alias: str,
    prompt_chars: int,
    max_tokens: int,
) -> None:
    """Budget hard-stop BEFORE consuming tokens (``AI_PRODUCT_SPEC`` §11.2).

    No-op unless a real provider is active AND a durable ``db`` session is
    present (offline / anonymous calls cannot and need not be budget-checked).
    Raises ``PaymentRequiredError`` (402) when the estimated spend would exceed a
    platform / per-user / per-org limit — the caller MUST let this propagate and
    must not wrap it as ``AI_UNAVAILABLE``.
    """

    if usage is None or usage.db is None:
        return

    from app.ai.gateway.factory import real_provider_active

    if not real_provider_active():
        return

    from app.ai.observability.cost_estimator import estimate_cost_usd
    from app.modules.ai_settings.application.budget_guard import check_async

    estimated = estimate_cost_usd(
        alias,
        prompt_chars=prompt_chars,
        completion_chars=int(max_tokens * _CHARS_PER_TOKEN),
    )
    await check_async(
        usage.db,
        alias=alias,
        estimated_cost_usd=estimated,
        user_id=usage.user_id,
        org_id=usage.org_id,
    )


async def record_usage(
    usage: AiUsageContext | None,
    *,
    task_type: str,
    alias: str,
    success: bool,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    latency_ms: int = 0,
    status: str | None = None,
    write_ledger: bool = True,
) -> None:
    """Record one governed provider call to the ledger + ops telemetry.

    - ``usage.db`` present: writes an idempotent ``ai_usage_log`` row (skipped on
      a duplicate ``idempotency_key`` so a retry does not double-charge) plus a
      ``ai_ops_event`` / Langfuse telemetry span. When the ledger row is a dedup
      no-op the telemetry span is skipped too, so retries never double-count.
    - ``usage.db`` absent: emits only the metadata log line (legacy behaviour).

    Set ``write_ledger=False`` for a *blocked* attempt (budget refusal): no
    billable ledger row is written, only a ``blocked`` telemetry span.
    """

    from app.ai.observability.usage import log_ai_usage

    if usage is None or usage.db is None:
        log_ai_usage(
            task_type=task_type,
            alias=alias,
            success=success,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
        )
        return

    resolved_status = status or ("ok" if success else "error")

    inserted = True
    if write_ledger:
        from app.ai.observability.cost_estimator import estimate_cost_usd
        from app.ai.observability.usage import log_ai_usage_async

        cost_usd = (
            estimate_cost_usd(
                alias, prompt_chars=prompt_chars, completion_chars=completion_chars
            )
            if success
            else None
        )
        inserted = await log_ai_usage_async(
            usage.db,
            task_type=task_type,
            alias=alias,
            success=success,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
            user_id=usage.user_id,
            session_id=usage.session_id,
            cost_usd=cost_usd,
            idempotency_key=usage.idempotency_key,
        )
    else:
        # Blocked: still emit the metadata log line for parity, no DB ledger row.
        log_ai_usage(
            task_type=task_type,
            alias=alias,
            success=success,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
        )

    # Skip telemetry when the ledger write was a dedup no-op (retry) — otherwise
    # the ops-event / daily rollup would double-count a de-duplicated call.
    if write_ledger and not inserted:
        return

    from app.ai.gateway.task_runner import _record_telemetry, _resolve_provider_model

    provider_name, model_id = _resolve_provider_model(alias)
    await _record_telemetry(
        db=usage.db,
        task_type=task_type,
        alias=alias,
        provider=provider_name,
        model=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=resolved_status,
        fallback_used=False,
        org_id=usage.org_id,
        user_id=usage.user_id,
        session_id=usage.session_id,
    )
