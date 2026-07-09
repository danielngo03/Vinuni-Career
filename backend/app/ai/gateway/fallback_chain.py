"""Fallback-chain execution for the AI gateway (AI_PRODUCT_SPEC §5.2).

``factory.get_provider_for_alias`` resolves each alias to an ORDERED list of
already-circuit-checked, already-key-checked provider hops. When that list has
more than one entry, it wraps them in :class:`FallbackChainProvider`, which
tries each hop in order and only advances to the next hop on an
``AIUnavailableError`` — the gateway's own signal for a transient/availability
failure (circuit open, network error, upstream 5xx/timeout). Any other
exception is a non-transient failure (e.g. a bug, or a guard/validation error
raised before this layer) and propagates immediately without retrying, per
AI_PRODUCT_SPEC §5.2 ("only availability/transient failures should" trigger
fallback).

Per-provider success/failure is still recorded by the ``CircuitAwareProvider``
wrapper built in ``factory.py`` — this module does not duplicate that
bookkeeping, it only sequences the hops.

Internal-only observability: which provider actually served a request is
logged at DEBUG for operator debugging. Provider identity must never reach an
end-user response (``.claude/rules/ai.md``).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage, AIProvider
from app.shared.exceptions import AIUnavailableError

logger = logging.getLogger("ai.gateway.fallback_chain")


class FallbackChainProvider(AIProvider):
    """Tries an ordered list of provider hops; only availability errors advance
    to the next hop.

    ``entries`` must be non-empty and pre-filtered by the caller (circuit-open
    and missing-key hops already excluded) — this class only sequences calls
    and does not re-check circuit state itself.
    """

    #: Internal-only marker name; never exposed to end users.
    name = "fallback_chain"

    def __init__(self, entries: list[tuple[str, AIProvider]]) -> None:
        if not entries:
            raise AIUnavailableError()
        self._entries = entries

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> AICompletion:
        last_exc: AIUnavailableError | None = None
        for position, (provider_name, provider) in enumerate(self._entries):
            try:
                result = await provider.complete(
                    messages,
                    alias=alias,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice=tool_choice,
                )
            except AIUnavailableError as exc:
                last_exc = exc
                _log_hop_failed(alias, provider_name, position)
                continue
            _log_hop_served(alias, provider_name, position)
            return result
        raise last_exc or AIUnavailableError()

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        last_exc: AIUnavailableError | None = None
        for position, (provider_name, provider) in enumerate(self._entries):
            yielded_any = False
            try:
                async for chunk in provider.stream(
                    messages, alias=alias, temperature=temperature, max_tokens=max_tokens
                ):
                    yielded_any = True
                    yield chunk
            except AIUnavailableError as exc:
                if yielded_any:
                    # Partial output already reached the caller — retrying on
                    # another provider would duplicate/garble the stream, so
                    # surface the failure instead of silently switching hops.
                    raise
                last_exc = exc
                _log_hop_failed(alias, provider_name, position)
                continue
            _log_hop_served(alias, provider_name, position)
            return
        raise last_exc or AIUnavailableError()

    async def embed(
        self,
        texts: list[str],
        *,
        alias: str,
    ) -> list[AIEmbedding]:
        last_exc: AIUnavailableError | None = None
        for position, (provider_name, provider) in enumerate(self._entries):
            try:
                result = await provider.embed(texts, alias=alias)
            except AIUnavailableError as exc:
                last_exc = exc
                _log_hop_failed(alias, provider_name, position)
                continue
            _log_hop_served(alias, provider_name, position)
            return result
        raise last_exc or AIUnavailableError()


def _log_hop_served(alias: str, provider_name: str, position: int) -> None:
    """Internal debugging only — provider identity must never reach end users."""

    logger.debug(
        "ai_fallback_chain_served",
        extra={"alias": alias, "provider": provider_name, "chain_position": position},
    )


def _log_hop_failed(alias: str, provider_name: str, position: int) -> None:
    """Internal debugging only — provider identity must never reach end users."""

    logger.warning(
        "ai_fallback_chain_hop_failed",
        extra={"alias": alias, "provider": provider_name, "chain_position": position},
    )
