"""AI provider factory — multi-provider routing support (ADR-0011 §6).

Selects the offline provider by default (deterministic, no network). When real
calls are enabled, ``get_provider_for_alias`` resolves the correct upstream
provider from the runtime snapshot's ``provider_routes`` table, reads the API
key from the encrypted admin snapshot or env fallback, and returns an
``OpenAICompatibleProvider`` instance pointed at the right endpoint.

All LLM access in domain modules must go through this factory / gateway — no
direct provider SDK calls (``.claude/rules/ai.md``).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIProvider
from app.ai.gateway.offline import OfflineProvider
from app.ai.gateway.openai_compatible import OpenAICompatibleProvider
from app.core.config import get_settings
from app.shared.exceptions import AIUnavailableError

# ---------------------------------------------------------------------------
# Circuit Breaker — per-provider failure tracking (AI_PRODUCT_SPEC §5.2)
# Opens after _CB_THRESHOLD consecutive failures; re-tests after _CB_RECOVERY_SECS.
# ---------------------------------------------------------------------------

_CB_THRESHOLD = 3  # failures before circuit opens
_CB_RECOVERY_SECS = 60.0  # seconds before HALF_OPEN retry


@dataclass
class _CircuitState:
    failure_count: int = 0
    last_failure_at: float = 0.0
    opened_at: float = 0.0
    #: HALF_OPEN single-probe guard — True while the one allowed trial call is
    #: in flight, so concurrent callers keep shedding until it resolves.
    probe_in_flight: bool = False

    def state(self) -> str:
        """Tri-state per AI_PRODUCT_SPEC §5.2: ``closed`` | ``open`` | ``half_open``.

        - ``closed``    — under the failure threshold; full concurrency.
        - ``open``      — threshold hit and still inside the recovery window;
          every call fast-fails to the fallback / degraded path.
        - ``half_open`` — recovery window elapsed; ONE probe is allowed through
          to test recovery (see :meth:`acquire`).
        """

        if self.failure_count < _CB_THRESHOLD:
            return "closed"
        if (time.monotonic() - self.opened_at) < _CB_RECOVERY_SECS:
            return "open"
        return "half_open"

    def is_open(self) -> bool:
        """True only in the fully-OPEN (fast-fail) state.

        Kept for the selection gate and existing callers/tests: a ``half_open``
        circuit is admissible (it must be reachable so its single probe can
        run), so only ``open`` short-circuits provider selection.
        """

        return self.state() == "open"

    def acquire(self) -> bool:
        """Call-time admission decision (used by ``CircuitAwareProvider``).

        - ``closed``    → admit (no gating; full concurrency).
        - ``open``      → refuse (shed to the next hop / degraded reply).
        - ``half_open`` → admit EXACTLY ONE probe; concurrent callers are
          refused until the probe resolves. ``record_success`` /
          ``record_failure`` always release the guard, so it can never wedge.
        """

        st = self.state()
        if st == "open":
            return False
        if st == "half_open":
            if self.probe_in_flight:
                return False
            self.probe_in_flight = True
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = 0.0
        self.probe_in_flight = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_at = time.monotonic()
        # Release the probe guard and (re-)open the window on threshold: a failed
        # half-open probe must send the circuit back to OPEN for another cooldown.
        self.probe_in_flight = False
        if self.failure_count >= _CB_THRESHOLD:
            self.opened_at = time.monotonic()


# Mutable per-process state — asyncio is single-threaded so no lock needed.
_circuit_states: dict[str, _CircuitState] = {}


def _get_circuit(provider_name: str) -> _CircuitState:
    if provider_name not in _circuit_states:
        _circuit_states[provider_name] = _CircuitState()
    return _circuit_states[provider_name]


def get_circuit_state(provider_name: str) -> str:
    """Public read-only accessor for the routing canvas: the real tri-state
    (``closed`` | ``open`` | ``half_open``). Read-only — never consumes the
    half-open probe slot (that only happens on an actual call via ``acquire``)."""

    return _get_circuit(provider_name).state()


# ---------------------------------------------------------------------------
# Provider env-key resolution
# Convention: AI_PROVIDER_{UPPERCASE_NAME}_API_KEY
# Built-in provider name fallbacks for backward compat.
# ---------------------------------------------------------------------------

_LEGACY_KEY_FALLBACKS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "azure-openai": "AZURE_OPENAI_API_KEY",
}

_PLACEHOLDER_KEYS = frozenset({"", "replace-with-local-key", "replace-with-local-secret"})


def _get_api_key(provider_name: str) -> str:
    """Resolve the API key for a provider name.

    Admin-managed keys are published as Fernet ciphertexts in the runtime
    snapshot. Env remains a deploy-time fallback and backward-compatible path.
    """
    cipher = runtime_config.current().provider_key_ciphertexts.get(provider_name)
    if cipher:
        from app.ai.gateway.provider_key_crypto import decrypt_provider_api_key

        key = decrypt_provider_api_key(cipher)
        if key not in _PLACEHOLDER_KEYS:
            return key

    env_var = f"AI_PROVIDER_{provider_name.upper().replace('-', '_').replace(' ', '_')}_API_KEY"
    key = os.environ.get(env_var, "")
    if key in _PLACEHOLDER_KEYS:
        if provider_name == "openrouter":
            # pydantic-settings reads .env; os.environ may not export it
            key = getattr(get_settings(), "openrouter_api_key", "") or ""
        elif provider_name == "openai":
            key = getattr(get_settings(), "openai_api_key", "") or os.environ.get(
                "OPENAI_API_KEY",
                "",
            )
        elif provider_name in _LEGACY_KEY_FALLBACKS:
            key = os.environ.get(_LEGACY_KEY_FALLBACKS[provider_name], "")
    return key


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def real_provider_active() -> bool:
    """True when a real (network) provider is configured and enabled.

    Reads the FINAL, post-precedence decision from the published runtime snapshot
    (``runtime_config.current().real_calls_active``) — which already AND-combines
    the env ceiling (``AI_REAL_CALLS_ENABLED``), key presence, and the admin DB
    toggle/rollout (ADR-0011 §2). Used to gate *optional* user-facing AI
    enrichment: under the default offline provider this returns ``False`` so
    callers skip the model call and degrade gracefully.
    """

    return runtime_config.current().real_calls_active


def get_provider() -> AIProvider:
    """Return the active provider for the CURRENT default chat alias.

    Backward-compat entry point. Equivalent to
    ``get_provider_for_alias(current_config.chat_model_alias)``.
    """

    cfg = runtime_config.current()
    if not cfg.real_calls_active:
        return OfflineProvider()
    return get_provider_for_alias(cfg.chat_model_alias)


def get_provider_for_alias(alias: str) -> AIProvider:
    """Return the active provider (chain) for a given model alias.

    Resolution order:
    1. Look up the alias's ORDERED fallback chain in
       ``runtime_config.current().provider_route_chains`` (DB-backed, published
       by the provider registry at startup/update — falls back to the single
       ``provider_routes`` entry, then the env-bootstrapped built-in routes).
    2. Build one provider hop per chain entry, skipping any hop whose circuit
       is open or whose API key is missing.
    3. If exactly one hop survives, return it directly (byte-identical to the
       pre-fallback-chain behaviour — no regression for single-provider
       aliases). If more than one survives, wrap them in
       ``FallbackChainProvider`` (AI_PRODUCT_SPEC §5.2): it tries hop 0 first
       and only advances to the next hop on an ``AIUnavailableError``
       (transient/availability failure) — never on a non-retryable error.
    4. If no hop survives, raise ``AIUnavailableError``.

    The API key is resolved from env at call time — never from the snapshot.
    Callers should handle ``AIUnavailableError`` and degrade gracefully.

    Circuit breaker (spec §5.2): if a hop's provider has failed _CB_THRESHOLD
    consecutive times within _CB_RECOVERY_SECS, it is skipped without
    attempting a network call. A successful call resets its circuit. Failures
    are recorded by the ``CircuitAwareProvider`` wrapper for every hop.
    """

    cfg = runtime_config.current()
    if not cfg.real_calls_active:
        return OfflineProvider()

    chain = cfg.provider_route_chains.get(alias)
    if not chain:
        route = cfg.provider_routes.get(alias)
        chain = [route] if route is not None else []
    if not chain:
        raise AIUnavailableError()

    entries: list[tuple[str, AIProvider]] = []
    for provider_name, base_url, model_id in chain:
        # Circuit breaker check — fast-fail before resolving the API key.
        circuit = _get_circuit(provider_name)
        if circuit.is_open():
            continue

        api_key = _get_api_key(provider_name)

        # Ollama-type providers don't require an API key
        if not api_key and provider_name not in ("ollama-local", "ollama"):
            continue

        hop_base_url = base_url
        # Use the legacy config base_url for the "openrouter" provider if it
        # was set explicitly (e.g. custom OpenRouter mirror).
        if provider_name == "openrouter":
            settings_url = getattr(get_settings(), "openai_compatible_base_url", "")
            if settings_url:
                hop_base_url = settings_url

        inner = OpenAICompatibleProvider(
            base_url=hop_base_url, api_key=api_key, model_override=model_id
        )
        wrapped = CircuitAwareProvider(inner=inner, provider_name=provider_name)
        entries.append((provider_name, wrapped))

    if not entries:
        raise AIUnavailableError()
    if len(entries) == 1:
        return entries[0][1]

    from app.ai.gateway.fallback_chain import FallbackChainProvider

    return FallbackChainProvider(entries)


class CircuitAwareProvider(AIProvider):
    """Thin wrapper that records success/failure in the per-provider circuit breaker."""

    def __init__(self, *, inner: AIProvider, provider_name: str) -> None:
        self._inner = inner
        self._provider_name = provider_name

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._inner.name

    async def complete(
        self,
        messages,
        *,
        alias,
        temperature=0.2,
        max_tokens=1024,
        tools=None,
        tool_choice=None,
    ):
        circuit = _get_circuit(self._provider_name)
        if not circuit.acquire():
            # Circuit OPEN, or a HALF_OPEN probe is already in flight: shed this
            # call WITHOUT recording a provider failure (it never reached the
            # upstream). Raising AIUnavailableError lets the fallback chain move
            # to the next hop / the caller degrade gracefully.
            raise AIUnavailableError()
        try:
            result = await self._inner.complete(
                messages,
                alias=alias,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
            )
            circuit.record_success()
            return result
        except Exception:
            circuit.record_failure()
            raise

    async def stream(self, messages, *, alias, temperature=0.2, max_tokens=1024):
        circuit = _get_circuit(self._provider_name)
        if not circuit.acquire():
            raise AIUnavailableError()
        try:
            async for chunk in self._inner.stream(
                messages, alias=alias, temperature=temperature, max_tokens=max_tokens
            ):
                yield chunk
            circuit.record_success()
        except Exception:
            circuit.record_failure()
            raise

    async def embed(self, texts, *, alias):
        circuit = _get_circuit(self._provider_name)
        if not circuit.acquire():
            raise AIUnavailableError()
        try:
            result = await self._inner.embed(texts, alias=alias)
            circuit.record_success()
            return result
        except Exception:
            circuit.record_failure()
            raise
