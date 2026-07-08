"""Realtime provider adapters + the connection descriptor contract.

A provider mints a short-lived EPHEMERAL credential and returns a transport-
agnostic :class:`ConnectionDescriptor` the browser uses to connect DIRECTLY to
the provider. The descriptor carries ONLY leak-safe aliases for provider/model —
never a vendor name, base URL, or the raw API key.

SECURITY: an adapter must return an EPHEMERAL, scoped token — never the raw
provider key. Until a native ephemeral-token mint is implemented and verified for
a given provider, its ``mint_ephemeral`` raises ``RealtimeUnavailableError`` so
the feature falls back to the browser-native voice tier instead of leaking a key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.shared.exceptions import AIUnavailableError


class RealtimeUnavailableError(AIUnavailableError):
    """Realtime tier not available — caller degrades to browser voice / text."""


@dataclass(frozen=True, slots=True)
class ConnectionDescriptor:
    transport: str  # "websocket" (Gemini Live) | "webrtc" (OpenAI Realtime)
    url: str  # provider connection URL (public endpoint, not a secret)
    ephemeral_token: str  # short-lived, scoped — NEVER the raw provider key
    expires_at: str  # ISO-8601 UTC
    provider_ref: str  # leak-safe alias
    model_ref: str  # leak-safe alias


@runtime_checkable
class RealtimeProvider(Protocol):
    async def mint_ephemeral(
        self,
        *,
        system_instruction: str,
        locale: str,
        ttl_seconds: int,
        max_output_tokens: int,
        provider_ref: str,
        model: str,
        voice: str,
    ) -> ConnectionDescriptor: ...


class _UnwiredProvider:
    """Placeholder adapter for a configured-but-not-yet-wired provider.

    Keeps the feature SAFE: it raises instead of ever returning a raw key. A
    superadmin who registers a real provider replaces this with a concrete
    adapter that calls the provider's ephemeral-token endpoint.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    async def mint_ephemeral(self, **_: object) -> ConnectionDescriptor:
        raise RealtimeUnavailableError(
            details={"fallback": "voice", "reason": "REALTIME_PROVIDER_NOT_WIRED"}
        )


# Registry of realtime provider adapters, keyed by config alias. Concrete
# GeminiLive/OpenAIRealtime adapters are registered here when a native mint is
# implemented + verified with a real key. Unknown/unwired aliases resolve to the
# safe placeholder.
_ADAPTERS: dict[str, RealtimeProvider] = {}


def get_provider(alias: str) -> RealtimeProvider:
    return _ADAPTERS.get(alias) or _UnwiredProvider(alias)


def register_provider(alias: str, provider: RealtimeProvider) -> None:
    """Register a concrete adapter (superadmin provider onboarding)."""

    _ADAPTERS[alias] = provider
