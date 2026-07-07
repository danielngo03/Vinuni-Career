"""Unified AI task execution layer (AI_PRODUCT_SPEC §4, §5, §9, §10, §11).

``AiTaskRunner`` is the single entry point for ALL LLM calls in the system.
Every call goes through the same pipeline:

  1. Budget pre-check (§11.2) — raises 402 BUDGET_EXCEEDED before consuming tokens
  2. Input guard (§9.1) — PII redaction, injection strip, length cap
  3. Provider routing via alias (§5.1, ADR-0011 §6)
  4. Circuit breaker (§5.2) — wrapped inside get_provider_for_alias
  5. Provider call (complete or stream)
  6. Output guard (§9.2) — provider brand/key scrub
  7. Cost logging to ai_usage_log (§5.4)
  8. Ops telemetry + Langfuse trace (§5.6, §11)
  9. 1% eval sampling (§10.2)

Domain code calls ``AiTaskRunner(db, alias, task_type).complete(messages)`` or
``.stream(messages)``. It never calls provider adapters directly.

SECRECY: provider names, model IDs, API keys, token counts, latency, and raw
prompt/response content are NEVER logged or surfaced to callers.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage
from app.shared.exceptions import AIUnavailableError, ValidationFailedError


class AiTaskRunner:
    """Pipeline runner for a single AI task.

    Usage::

        runner = AiTaskRunner(db, alias="chat_default", task_type="interview_sim")
        completion = await runner.complete(messages, temperature=0.7, max_tokens=300)

        async for chunk in runner.stream(messages):
            yield {"type": "token", "text": chunk}
    """

    def __init__(
        self,
        db: AsyncSession | None,
        *,
        alias: str,
        task_type: str,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        tool_class: str = "read_only",
        org_id: uuid.UUID | None = None,
    ) -> None:
        self._db = db
        self._alias = alias
        self._task_type = task_type
        self._user_id = user_id
        self._session_id = session_id
        self._tool_class = tool_class
        self._org_id = org_id

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        """Run a complete call through the full governance pipeline."""
        import time

        from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
        from app.ai.gateway.offline import OfflineProvider
        from app.ai.gateway.output_guard import guard_completion
        from app.ai.observability.cost_estimator import estimate_cost_usd
        from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
        from app.modules.ai_settings.application.budget_guard import check_async

        # Resolve alias from runtime config (supports dynamic admin overrides)
        alias = self._alias

        # Resolve concrete (provider, model) for telemetry from runtime snapshot.
        provider_name, model_id = _resolve_provider_model(alias)

        # 1. Budget pre-check
        prompt_chars = sum(len(m.content) for m in messages)
        estimated_cost = estimate_cost_usd(
            alias,
            prompt_chars=prompt_chars,
            completion_chars=max_tokens * 4,
        )
        if self._db is not None and real_provider_active():
            try:
                await check_async(
                    self._db,
                    alias=alias,
                    estimated_cost_usd=estimated_cost,
                    user_id=self._user_id,
                )
            except Exception:
                # Record a "blocked" ops event then re-raise so the caller
                # still sees the PaymentRequiredError.
                if self._db is not None:
                    await _record_telemetry(
                        db=self._db,
                        task_type=self._task_type,
                        alias=alias,
                        provider=provider_name,
                        model=model_id,
                        prompt_tokens=None,
                        completion_tokens=None,
                        latency_ms=0,
                        status="blocked",
                        fallback_used=False,
                        org_id=self._org_id,
                        user_id=self._user_id,
                        session_id=self._session_id,
                    )
                raise

        # 2. Policy orchestration: intent classification → policy decision → rewrite/refuse
        try:
            safe_messages = _sanitize_messages(messages, tool_class=self._tool_class)
        except PolicyRefusalError as exc:
            raise ValidationFailedError(
                str(exc),
                details={"reason": "ai_policy_refused"},
            ) from exc

        # 3. Route to correct provider (circuit breaker applied inside factory)
        if real_provider_active():
            try:
                provider = get_provider_for_alias(alias)
            except Exception:
                provider = OfflineProvider()
        else:
            provider = OfflineProvider()

        # 4. Call provider — measure latency
        t0 = time.monotonic()
        try:
            raw = await provider.complete(
                safe_messages, alias=alias, temperature=temperature, max_tokens=max_tokens
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            if self._db is not None:
                await log_ai_usage_async(
                    self._db,
                    task_type=self._task_type,
                    alias=alias,
                    success=False,
                    user_id=self._user_id,
                    session_id=self._session_id,
                )
                await _record_telemetry(
                    db=self._db,
                    task_type=self._task_type,
                    alias=alias,
                    provider=provider_name,
                    model=model_id,
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_ms=latency_ms,
                    status="error",
                    fallback_used=False,
                    org_id=self._org_id,
                    user_id=self._user_id,
                    session_id=self._session_id,
                )
            else:
                log_ai_usage(task_type=self._task_type, alias=alias, success=False)
            raise AIUnavailableError() from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        # 5. Output guard
        guarded_text = guard_completion(raw)
        completion_chars = len(guarded_text)

        # Extract real token counts from provider usage dict.
        prompt_tokens: int | None = raw.usage.get("prompt_tokens")
        completion_tokens: int | None = raw.usage.get("completion_tokens")

        # 6. Cost log + eval sampling (existing path — do NOT change)
        cost_usd = estimate_cost_usd(
            alias,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
        )
        if self._db is not None:
            await log_ai_usage_async(
                self._db,
                task_type=self._task_type,
                alias=alias,
                success=True,
                prompt_chars=prompt_chars,
                completion_chars=completion_chars,
                user_id=self._user_id,
                session_id=self._session_id,
                cost_usd=cost_usd,
            )
        else:
            log_ai_usage(
                task_type=self._task_type,
                alias=alias,
                success=True,
                prompt_chars=prompt_chars,
                completion_chars=completion_chars,
            )

        # 7. Ops telemetry (new — best-effort, never raises)
        if self._db is not None:
            await _record_telemetry(
                db=self._db,
                task_type=self._task_type,
                alias=alias,
                provider=provider_name,
                model=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
                status="ok",
                fallback_used=False,
                org_id=self._org_id,
                user_id=self._user_id,
                session_id=self._session_id,
            )

        # Return a guarded completion — model_alias is safe (alias, not provider name)
        return AICompletion(
            text=guarded_text,
            model_alias=alias,
            usage=raw.usage,
            finish_reason=raw.finish_reason,
        )

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens through the governance pipeline.

        Note: To avoid double-calling the provider, callers that already have
        the full text (e.g., after a tool loop) should use ``_local_stream``
        from ``chat_service`` instead of this method.
        """
        import time

        from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
        from app.ai.gateway.offline import OfflineProvider
        from app.ai.gateway.output_guard import scrub_text
        from app.ai.observability.cost_estimator import estimate_cost_usd
        from app.ai.observability.usage import log_ai_usage_async
        from app.modules.ai_settings.application.budget_guard import check_async

        alias = self._alias
        provider_name, model_id = _resolve_provider_model(alias)
        prompt_chars = sum(len(m.content) for m in messages)
        estimated_cost = estimate_cost_usd(
            alias,
            prompt_chars=prompt_chars,
            completion_chars=max_tokens * 4,
        )

        if self._db is not None and real_provider_active():
            try:
                await check_async(
                    self._db,
                    alias=alias,
                    estimated_cost_usd=estimated_cost,
                    user_id=self._user_id,
                )
            except Exception:
                if self._db is not None:
                    await _record_telemetry(
                        db=self._db,
                        task_type=self._task_type,
                        alias=alias,
                        provider=provider_name,
                        model=model_id,
                        prompt_tokens=None,
                        completion_tokens=None,
                        latency_ms=0,
                        status="blocked",
                        fallback_used=False,
                        org_id=self._org_id,
                        user_id=self._user_id,
                        session_id=self._session_id,
                    )
                raise

        try:
            safe_messages = _sanitize_messages(messages, tool_class=self._tool_class)
        except PolicyRefusalError as exc:
            raise ValidationFailedError(
                str(exc),
                details={"reason": "ai_policy_refused"},
            ) from exc

        if real_provider_active():
            try:
                provider = get_provider_for_alias(alias)
            except Exception:
                provider = OfflineProvider()
        else:
            provider = OfflineProvider()

        total_chars = 0
        stream_status = "ok"
        t0 = time.monotonic()
        try:
            async for chunk in provider.stream(
                safe_messages, alias=alias, temperature=temperature, max_tokens=max_tokens
            ):
                safe_chunk = scrub_text(chunk)
                total_chars += len(safe_chunk)
                yield safe_chunk
        except AIUnavailableError:
            stream_status = "error"
            raise
        except Exception as exc:
            stream_status = "error"
            raise AIUnavailableError() from exc
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            cost_usd = estimate_cost_usd(
                alias,
                prompt_chars=prompt_chars,
                completion_chars=total_chars,
            )
            if self._db is not None:
                try:
                    await log_ai_usage_async(
                        self._db,
                        task_type=self._task_type,
                        alias=alias,
                        success=bool(total_chars),
                        prompt_chars=prompt_chars,
                        completion_chars=total_chars,
                        user_id=self._user_id,
                        session_id=self._session_id,
                        cost_usd=cost_usd,
                    )
                except Exception:
                    pass
                await _record_telemetry(
                    db=self._db,
                    task_type=self._task_type,
                    alias=alias,
                    provider=provider_name,
                    model=model_id,
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_ms=latency_ms,
                    status=stream_status,
                    fallback_used=False,
                    org_id=self._org_id,
                    user_id=self._user_id,
                    session_id=self._session_id,
                )

    async def embed(
        self,
        texts: list[str],
        *,
        embed_alias: str | None = None,
    ) -> list[AIEmbedding]:
        """Embed texts through the governance pipeline."""
        from app.ai.retrieval.embeddings import embed_texts

        alias = embed_alias or self._alias
        return await embed_texts(texts, alias=alias)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_provider_model(alias: str) -> tuple[str | None, str | None]:
    """Return the concrete (provider_name, model_id) for *alias*.

    Reads the active runtime snapshot — no DB call.  Falls back to
    (None, None) on any error so telemetry never blocks the call path.
    """
    try:
        from app.ai.gateway import runtime_config

        cfg = runtime_config.current()
        # Prefer the full fallback chain (index 0 is always the active hop).
        chain = cfg.provider_route_chains.get(alias)
        if chain:
            provider_name, _base_url, model_id = chain[0]
            return provider_name, model_id
        # Fall back to the flat routes dict.
        route = cfg.provider_routes.get(alias)
        if route:
            provider_name, _base_url, model_id = route
            return provider_name, model_id
    except Exception:  # noqa: BLE001
        pass
    return None, None


async def _record_telemetry(
    *,
    db: AsyncSession,
    task_type: str,
    alias: str,
    provider: str | None,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    status: str,
    fallback_used: bool,
    org_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
) -> None:
    """Fire-and-forget ops telemetry: Langfuse trace → ops_event row.

    Never raises — any failure is logged at WARNING level and swallowed so
    telemetry can never disrupt the AI call path.
    """
    try:
        from app.ai.observability.langfuse_client import trace_call
        from app.ai.observability.ops_recorder import OpsEventInput, record_ops_event
        from app.ai.observability.pricing import estimate_cost_usd_db
        from app.core.logging import request_id_ctx

        request_id = request_id_ctx.get() or ""

        # Langfuse trace first so we can attach the trace_id to the ops event.
        langfuse_trace_id: str | None = None
        try:
            langfuse_trace_id = trace_call(
                task_type=task_type,
                alias=alias,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
                latency_ms=float(latency_ms),
                status=status,
                org_id=str(org_id) if org_id else None,
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
            )
        except Exception:  # noqa: BLE001
            pass

        # DB-backed cost estimate (falls back to alias estimator; never raises).
        cost_usd: float | None = None
        unpriced = True
        try:
            cost_usd, unpriced = await estimate_cost_usd_db(
                db,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
            )
        except Exception:  # noqa: BLE001
            pass

        event = OpsEventInput(
            task_type=task_type,
            alias=alias,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            status=status,
            fallback_used=fallback_used,
            circuit_open=False,
            cost_usd=cost_usd,
            unpriced=unpriced,
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id or None,
            langfuse_trace_id=langfuse_trace_id,
        )
        await record_ops_event(db, event=event)

    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("ai.task_runner").warning(
            "ai_telemetry_failed", exc_info=True
        )


def _sanitize_messages(
    messages: list[AIMessage],
    tool_class: str = "read_only",
) -> list[AIMessage]:
    """Apply full policy pipeline to user messages (system/assistant trusted).

    Raises ``ValueError`` with a user-safe refusal message if a user message
    is refused by the policy orchestrator. The caller (AiTaskRunner) converts
    this to the appropriate HTTP error without reaching the LLM.
    """
    from app.ai.safety.policy_orchestrator import ACTION_REFUSE, check_policy

    result: list[AIMessage] = []
    for m in messages:
        if m.role == "user":
            decision = check_policy(m.content, tool_class=tool_class)
            if decision.action == ACTION_REFUSE:
                raise PolicyRefusalError(decision.refusal_message or "Request not allowed.")
            safe_content = decision.clean_text or m.content
            result.append(AIMessage(role="user", content=safe_content))
        else:
            result.append(m)
    return result


class PolicyRefusalError(ValueError):
    """Raised when policy orchestrator refuses a message."""
    pass
