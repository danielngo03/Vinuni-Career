"""Realtime speech-to-speech gateway (Tier V2).

TRUE full-duplex voice runs the audio path DIRECTLY between the browser and a
native provider (Gemini Live / OpenAI Realtime) using a short-lived EPHEMERAL
token minted here — audio never transits our servers (low latency + cost
control), and the system instruction + TTL are bound server-side at mint time so
the client cannot alter the grounding or exceed the budget.

This is separate from the TEXT gateway (``AiTaskRunner``): realtime is not a
``complete``/``stream`` text call. It is DISABLED by default and provider-
agnostic; a platform superadmin activates it by configuring a provider. Until a
native mint is wired, ``mint_session`` raises ``RealtimeUnavailableError`` and the
feature falls back to the browser-native voice tier (V1) — it NEVER returns a raw
provider key to the client.
"""

from app.ai.gateway.realtime.config import RealtimeConfig, current
from app.ai.gateway.realtime.mint import mint_session
from app.ai.gateway.realtime.providers import (
    ConnectionDescriptor,
    RealtimeProvider,
    RealtimeUnavailableError,
)

__all__ = [
    "RealtimeConfig",
    "current",
    "ConnectionDescriptor",
    "RealtimeProvider",
    "RealtimeUnavailableError",
    "mint_session",
]
