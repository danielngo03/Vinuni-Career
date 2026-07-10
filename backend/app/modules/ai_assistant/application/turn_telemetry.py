"""Per-chat-turn observability + energy accounting (AI_PRODUCT_SPEC §5.6/§11/§15).

The gateway ``AiTaskRunner`` records telemetry per *provider call*; the chat
loops (native partner loop, student ReAct loop) call providers directly through
their own cost-tracked helpers, so until now a chat TURN produced no Langfuse
trace, no ``ai_ops_event`` row, and no billable-ledger row. This module closes
that gap with two never-raising helpers:

- :func:`record_chat_turn` — one Langfuse trace + one ``AiOpsEvent`` per
  assistant turn (mirrors ``task_runner._record_telemetry``), plus a
  structured, metadata-only log line carrying the turn-level extras (persona,
  model alias, tool names, iteration count, guard flags). NO prompt text, NO
  chunk content, NO PII — §15.

- :func:`record_turn_billable` — one durable, idempotent
  ``ai_billable_usage`` row per successful REAL-model assistant turn. The
  idempotency key is derived from the assistant message id so a client retry /
  stream replay can never double-charge. Offline turns, refusals, and
  fast-path replies are never charged (callers gate on those).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    PERSONA_PARTNER,
    PERSONA_STUDENT,
    PERSONA_UNIVERSITY,
    RESULT_SUCCESS,
    SCOPE_ORG,
    SCOPE_USER,
    UsageContext,
    make_idempotency_key,
    record_billable_usage,
)
from app.shared.permissions import Principal

_TASK_TYPE = "ai_assistant_chat"
_CHARGE_UNITS_PER_TURN = 1

_log = logging.getLogger("ai.chat")


def _resolve_provider_model(alias: str) -> tuple[str | None, str | None]:
    """Concrete (provider, model) for internal telemetry only (never user-facing)."""
    try:
        from app.ai.gateway import runtime_config

        cfg = runtime_config.current()
        chain = cfg.provider_route_chains.get(alias)
        if chain:
            provider_name, _base_url, model_id = chain[0]
            return provider_name, model_id
        route = cfg.provider_routes.get(alias)
        if route:
            provider_name, _base_url, model_id = route
            return provider_name, model_id
    except Exception:  # noqa: BLE001 — telemetry must never block the turn
        pass
    return None, None


async def record_chat_turn(
    db: AsyncSession | None,
    *,
    principal: Principal,
    session_id: uuid.UUID | None,
    alias: str,
    status: str,
    latency_ms: int,
    iterations: int = 0,
    tool_names: list[str] | None = None,
    guard_flags: list[str] | None = None,
) -> None:
    """Fire-and-forget per-turn telemetry: Langfuse trace → ops event → log line.

    ``status`` vocabulary: ``ok`` | ``error`` | ``blocked`` | ``refused``.
    Metadata only — never prompt/response text, never chunk content, never PII.
    Never raises.
    """
    try:
        # Turn-level extras that the fixed ops-event schema has no columns for.
        _log.info(
            "ai_chat_turn",
            extra={
                "persona": principal.persona,
                "alias": alias,
                "status": status,
                "iterations": iterations,
                "tool_count": len(tool_names or []),
                "tools": ",".join(tool_names or []) or None,
                "guard_flags": ",".join(guard_flags or []) or None,
                "latency_ms": latency_ms,
            },
        )
        if db is None:
            return

        from app.ai.observability.langfuse_client import trace_call
        from app.ai.observability.ops_recorder import OpsEventInput, record_ops_event
        from app.core.logging import request_id_ctx

        provider_name, model_id = _resolve_provider_model(alias)
        request_id = request_id_ctx.get() or ""

        langfuse_trace_id: str | None = None
        try:
            langfuse_trace_id = trace_call(
                task_type=_TASK_TYPE,
                alias=alias,
                provider=provider_name,
                model=model_id,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=float(latency_ms),
                status=status,
                org_id=str(principal.org_id) if principal.org_id else None,
                user_id=str(principal.user_id) if principal.user_id else None,
                request_id=request_id,
            )
        except Exception:  # noqa: BLE001
            pass

        await record_ops_event(
            db,
            event=OpsEventInput(
                task_type=_TASK_TYPE,
                alias=alias,
                provider=provider_name,
                model=model_id,
                prompt_tokens=None,
                completion_tokens=None,
                latency_ms=latency_ms,
                status=status,
                fallback_used=False,
                circuit_open=False,
                cost_usd=None,  # per-call cost already lands in ai_usage_log
                unpriced=True,
                org_id=principal.org_id,
                user_id=principal.user_id,
                session_id=session_id,
                request_id=request_id or None,
                langfuse_trace_id=langfuse_trace_id,
            ),
        )
    except Exception:  # noqa: BLE001 — telemetry must never break the chat path
        _log.warning("ai_chat_turn_telemetry_failed", exc_info=True)


def _usage_context(
    principal: Principal,
    *,
    assistant_message_id: uuid.UUID,
    session_id: uuid.UUID | None,
) -> UsageContext:
    persona = principal.persona or ""
    if persona.startswith("partner"):
        actor_persona = PERSONA_PARTNER
        scope = SCOPE_ORG if principal.org_id else SCOPE_USER
    elif persona.startswith("university"):
        actor_persona = PERSONA_UNIVERSITY
        scope = SCOPE_ORG if principal.org_id else SCOPE_USER
    else:
        actor_persona = PERSONA_STUDENT
        scope = SCOPE_USER
    return UsageContext(
        actor_persona=actor_persona,
        feature_key=FEATURE_CHATBOT,
        task_type=_TASK_TYPE,
        billing_scope=scope,
        actor_user_id=principal.user_id,
        org_id=principal.org_id,
        resource_type="chat_message",
        resource_id=assistant_message_id,
        session_id=session_id,
        idempotency_key=make_idempotency_key(FEATURE_CHATBOT, assistant_message_id),
    )


async def record_turn_billable(
    db: AsyncSession | None,
    *,
    principal: Principal,
    assistant_message_id: uuid.UUID,
    session_id: uuid.UUID | None,
    provider_cost_usd: float | None = None,
) -> None:
    """Record ONE idempotent billable-usage row for a successful real-model turn.

    Callers gate on ``real_provider_active()`` and turn success — this helper
    itself is best-effort and never raises (accounting must not break replies).
    A second call with the same assistant message id is a no-op (one ledger row).
    """
    if db is None:
        return
    try:
        await record_billable_usage(
            db,
            ctx=_usage_context(
                principal,
                assistant_message_id=assistant_message_id,
                session_id=session_id,
            ),
            result_status=RESULT_SUCCESS,
            base_units=_CHARGE_UNITS_PER_TURN,
            provider_cost_usd=provider_cost_usd,
        )
    except Exception:  # noqa: BLE001
        _log.warning("ai_chat_turn_billable_failed", exc_info=True)
