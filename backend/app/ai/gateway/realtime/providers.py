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

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import httpx

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


# --------------------------------------------------------------------------- #
# Gemini Live adapter (native speech-to-speech)                                #
# --------------------------------------------------------------------------- #
_PLACEHOLDERS = frozenset({"", "replace-with-local-key", "changeme", "your-key"})
# Ephemeral-token mint (v1alpha) + the constrained Live WebSocket the browser
# connects to. The token carries model + system instruction, so the descriptor
# never exposes them.
_AUTH_TOKEN_URL = "https://generativelanguage.googleapis.com/v1alpha/auth_tokens"
_LIVE_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1alpha.GenerativeService."
    "BidiGenerateContentConstrained"
)


def _gemini_key() -> str:
    from app.core.config import get_settings

    s = get_settings()
    for candidate in (
        getattr(s, "gemini_api_key", "") or "",
        os.environ.get("GEMINI_API_KEY", ""),
        os.environ.get("GOOGLE_API_KEY", ""),
        os.environ.get("AI_PROVIDER_GEMINI_LIVE_API_KEY", ""),
    ):
        if candidate and candidate not in _PLACEHOLDERS:
            return candidate.strip()
    return ""


class GeminiLiveProvider:
    """Mints a Gemini Live ephemeral token bound to the interview grounding.

    The system instruction + model are locked into the token via
    ``liveConnectConstraints`` so the browser cannot alter them, and the raw
    Google key never leaves the server (only the short-lived token is returned).
    """

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
    ) -> ConnectionDescriptor:
        key = _gemini_key()
        if not key:
            raise RealtimeUnavailableError(
                details={"fallback": "voice", "reason": "REALTIME_KEY_MISSING"}
            )
        expire = (datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        model_id = model if model.startswith("models/") else f"models/{model}"
        # Verified against the v1alpha discovery schema: the constraints live in
        # ``bidiGenerateContentSetup`` (a BidiGenerateContentSetup), with response
        # modalities + voice under ``generationConfig``. Locking model + system
        # instruction here keeps grounding server-side and off the client.
        generation_config: dict[str, Any] = {
            "responseModalities": ["AUDIO"],
            "temperature": 0.7,
        }
        if voice:
            generation_config["speechConfig"] = {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            }
        body = {
            "uses": 1,
            "expireTime": expire,
            "bidiGenerateContentSetup": {
                "model": model_id,
                "generationConfig": generation_config,
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _AUTH_TOKEN_URL, params={"key": key}, json=body
                )
        except httpx.HTTPError as exc:
            raise RealtimeUnavailableError(
                details={"fallback": "voice", "reason": "REALTIME_MINT_FAILED"}
            ) from exc
        if resp.status_code >= 400:
            raise RealtimeUnavailableError(
                details={
                    "fallback": "voice",
                    "reason": "REALTIME_MINT_HTTP",
                    "status": resp.status_code,
                }
            )
        data = resp.json()
        token = data.get("name") or data.get("token")
        if not token:
            raise RealtimeUnavailableError(
                details={"fallback": "voice", "reason": "REALTIME_NO_TOKEN"}
            )
        return ConnectionDescriptor(
            transport="websocket",
            url=_LIVE_WS_URL,
            ephemeral_token=str(token),
            expires_at=expire,
            provider_ref=provider_ref,  # leak-safe alias (internal)
            model_ref="interview-live",  # masked; never the real model id
        )


# Register the Gemini Live adapter for its config alias.
register_provider("gemini-live", GeminiLiveProvider())
