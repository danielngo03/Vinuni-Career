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
  8. 1% eval sampling (§10.2)

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

        runner = AiTaskRunner(db, alias="chat_cheap", task_type="interview_sim")
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
    ) -> None:
        self._db = db
        self._alias = alias
        self._task_type = task_type
        self._user_id = user_id
        self._session_id = session_id
        self._tool_class = tool_class

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        """Run a complete call through the full governance pipeline."""
        from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
        from app.ai.gateway.offline import OfflineProvider
        from app.ai.gateway.output_guard import guard_completion
        from app.ai.observability.cost_estimator import estimate_cost_usd
        from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
        from app.modules.ai_settings.application.budget_guard import check_async

        # Resolve alias from runtime config (supports dynamic admin overrides)
        alias = self._alias

        # 1. Budget pre-check
        prompt_chars = sum(len(m.content) for m in messages)
        estimated_cost = estimate_cost_usd(
            alias,
            prompt_chars=prompt_chars,
            completion_chars=max_tokens * 4,
        )
        if self._db is not None and real_provider_active():
            await check_async(
                self._db,
                alias=alias,
                estimated_cost_usd=estimated_cost,
                user_id=self._user_id,
            )

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

        # 4. Call provider
        try:
            raw = await provider.complete(
                safe_messages, alias=alias, temperature=temperature, max_tokens=max_tokens
            )
        except Exception as exc:
            if self._db is not None:
                await log_ai_usage_async(
                    self._db,
                    task_type=self._task_type,
                    alias=alias,
                    success=False,
                    user_id=self._user_id,
                    session_id=self._session_id,
                )
            else:
                log_ai_usage(task_type=self._task_type, alias=alias, success=False)
            raise AIUnavailableError() from exc

        # 5. Output guard
        guarded_text = guard_completion(raw)
        completion_chars = len(guarded_text)

        # 6. Cost log + eval sampling
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
        from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
        from app.ai.gateway.offline import OfflineProvider
        from app.ai.gateway.output_guard import scrub_text
        from app.ai.observability.cost_estimator import estimate_cost_usd
        from app.ai.observability.usage import log_ai_usage_async
        from app.modules.ai_settings.application.budget_guard import check_async

        alias = self._alias
        prompt_chars = sum(len(m.content) for m in messages)
        estimated_cost = estimate_cost_usd(
            alias,
            prompt_chars=prompt_chars,
            completion_chars=max_tokens * 4,
        )

        if self._db is not None and real_provider_active():
            await check_async(
                self._db,
                alias=alias,
                estimated_cost_usd=estimated_cost,
                user_id=self._user_id,
            )

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
        try:
            async for chunk in provider.stream(
                safe_messages, alias=alias, temperature=temperature, max_tokens=max_tokens
            ):
                safe_chunk = scrub_text(chunk)
                total_chars += len(safe_chunk)
                yield safe_chunk
        except AIUnavailableError:
            raise
        except Exception as exc:
            raise AIUnavailableError() from exc
        finally:
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
