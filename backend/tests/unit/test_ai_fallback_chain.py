"""AI gateway fallback-chain unit tests (AI_PRODUCT_SPEC §5.2).

Covers:
- Single-provider alias behaves identically to pre-chain behaviour (no regression).
- Chain success on the first provider.
- Chain falls back to the second provider when the first's circuit is open.
- Chain falls back to the second provider when the first raises AIUnavailableError.
- Chain exhausts and raises AIUnavailableError when every provider fails.
- Non-retryable exceptions (not AIUnavailableError) do NOT trigger fallback.
- Provider identity is never present in any exception/message surfaced to callers.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from app.ai.gateway import factory, runtime_config
from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage, AIProvider
from app.ai.gateway.fallback_chain import FallbackChainProvider
from app.shared.exceptions import AIUnavailableError

_MSGS = [AIMessage(role="user", content="hello")]


class _StubProvider(AIProvider):
    """Deterministic stub provider for chain tests."""

    def __init__(self, name: str, *, fail_with: Exception | None = None) -> None:
        self.name = name
        self._fail_with = fail_with
        self.calls = 0

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
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
        return AICompletion(text=f"ok-from-{self.name}", model_alias=alias)

    async def embed(self, texts, *, alias):
        self.calls += 1
        if self._fail_with is not None:
            raise self._fail_with
        return [AIEmbedding(vector=[1.0], model_alias=alias) for _ in texts]


@pytest.fixture(autouse=True)
def _reset_state():
    factory._circuit_states.clear()
    runtime_config.reset_to_bootstrap()
    yield
    factory._circuit_states.clear()
    runtime_config.reset_to_bootstrap()


def _publish_chain(
    alias: str,
    chain: list[tuple[str, str, str]],
    *,
    key_env: dict[str, str] | None = None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publish a runtime snapshot with a real-calls-active chain for ``alias``."""

    for env_name, env_value in (key_env or {}).items():
        monkeypatch.setenv(env_name, env_value)

    cfg = runtime_config.current()
    routes = dict(cfg.provider_routes)
    routes[alias] = chain[0]
    chains = dict(cfg.provider_route_chains)
    chains[alias] = chain
    runtime_config.publish(
        replace(
            cfg,
            real_calls_active=True,
            provider_routes=routes,
            provider_route_chains=chains,
        )
    )


# --------------------------------------------------------------------------- #
# FallbackChainProvider unit behaviour (no factory/DB involved)
# --------------------------------------------------------------------------- #


class TestFallbackChainProviderUnit:
    async def test_first_provider_success_short_circuits(self):
        good = _StubProvider("provider_a")
        bad = _StubProvider("provider_b")
        chain = FallbackChainProvider([("provider_a", good), ("provider_b", bad)])

        result = await chain.complete(_MSGS, alias="chat_cheap")

        assert result.text == "ok-from-provider_a"
        assert good.calls == 1
        assert bad.calls == 0  # never tried — first hop succeeded

    async def test_falls_back_to_second_provider_on_unavailable(self):
        first = _StubProvider("provider_a", fail_with=AIUnavailableError())
        second = _StubProvider("provider_b")
        chain = FallbackChainProvider([("provider_a", first), ("provider_b", second)])

        result = await chain.complete(_MSGS, alias="chat_cheap")

        assert result.text == "ok-from-provider_b"
        assert first.calls == 1
        assert second.calls == 1

    async def test_exhausts_chain_and_raises_ai_unavailable(self):
        first = _StubProvider("provider_a", fail_with=AIUnavailableError())
        second = _StubProvider("provider_b", fail_with=AIUnavailableError())
        chain = FallbackChainProvider([("provider_a", first), ("provider_b", second)])

        with pytest.raises(AIUnavailableError):
            await chain.complete(_MSGS, alias="chat_cheap")
        assert first.calls == 1
        assert second.calls == 1

    async def test_non_retryable_exception_does_not_trigger_fallback(self):
        first = _StubProvider("provider_a", fail_with=ValueError("bad input, not availability"))
        second = _StubProvider("provider_b")
        chain = FallbackChainProvider([("provider_a", first), ("provider_b", second)])

        with pytest.raises(ValueError):
            await chain.complete(_MSGS, alias="chat_cheap")
        assert first.calls == 1
        assert second.calls == 0  # non-retryable error must not advance the chain

    async def test_embed_falls_back_across_chain(self):
        first = _StubProvider("provider_a", fail_with=AIUnavailableError())
        second = _StubProvider("provider_b")
        chain = FallbackChainProvider([("provider_a", first), ("provider_b", second)])

        result = await chain.embed(["hello"], alias="embedding_cheap")

        assert len(result) == 1
        assert first.calls == 1
        assert second.calls == 1

    def test_empty_chain_raises_immediately(self):
        with pytest.raises(AIUnavailableError):
            FallbackChainProvider([])

    async def test_error_message_never_contains_provider_name(self):
        first = _StubProvider("super-secret-provider", fail_with=AIUnavailableError())
        second = _StubProvider("also-secret-provider", fail_with=AIUnavailableError())
        chain = FallbackChainProvider(
            [("super-secret-provider", first), ("also-secret-provider", second)]
        )

        with pytest.raises(AIUnavailableError) as excinfo:
            await chain.complete(_MSGS, alias="chat_cheap")
        assert "secret-provider" not in str(excinfo.value)


# --------------------------------------------------------------------------- #
# factory.get_provider_for_alias — chain resolution end-to-end
# --------------------------------------------------------------------------- #


class TestFactoryChainResolution:
    def test_single_provider_alias_unchanged(self, monkeypatch):
        """A one-hop chain must return the same CircuitAwareProvider shape as
        before this feature (no regression)."""

        _publish_chain(
            "chat_cheap",
            [("openrouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat")],
            key_env={"AI_PROVIDER_OPENROUTER_API_KEY": "sk-test-key"},
            monkeypatch=monkeypatch,
        )

        provider = factory.get_provider_for_alias("chat_cheap")

        assert not isinstance(provider, FallbackChainProvider)
        assert provider.__class__.__name__ == "CircuitAwareProvider"

    def test_chain_skips_provider_with_open_circuit(self, monkeypatch):
        _publish_chain(
            "chat_cheap",
            [
                ("provider_open", "https://open.example/v1", "model-a"),
                ("provider_closed", "https://closed.example/v1", "model-a"),
            ],
            key_env={
                "AI_PROVIDER_PROVIDER_OPEN_API_KEY": "sk-a",
                "AI_PROVIDER_PROVIDER_CLOSED_API_KEY": "sk-b",
            },
            monkeypatch=monkeypatch,
        )

        # Force provider_open's circuit open.
        circuit = factory._get_circuit("provider_open")
        for _ in range(factory._CB_THRESHOLD):
            circuit.record_failure()
        assert circuit.is_open() is True

        provider = factory.get_provider_for_alias("chat_cheap")

        # Only one surviving hop (provider_closed) -> returns the bare
        # CircuitAwareProvider, not a FallbackChainProvider wrapper.
        assert not isinstance(provider, FallbackChainProvider)
        assert provider._provider_name == "provider_closed"

    def test_chain_raises_when_all_providers_unavailable(self, monkeypatch):
        _publish_chain(
            "chat_cheap",
            [
                ("provider_x", "https://x.example/v1", "model-a"),
                ("provider_y", "https://y.example/v1", "model-a"),
            ],
            key_env={
                "AI_PROVIDER_PROVIDER_X_API_KEY": "sk-a",
                "AI_PROVIDER_PROVIDER_Y_API_KEY": "sk-b",
            },
            monkeypatch=monkeypatch,
        )
        for name in ("provider_x", "provider_y"):
            circuit = factory._get_circuit(name)
            for _ in range(factory._CB_THRESHOLD):
                circuit.record_failure()

        with pytest.raises(AIUnavailableError):
            factory.get_provider_for_alias("chat_cheap")

    def test_multi_hop_chain_returns_fallback_chain_provider(self, monkeypatch):
        _publish_chain(
            "chat_cheap",
            [
                ("provider_p", "https://p.example/v1", "model-a"),
                ("provider_q", "https://q.example/v1", "model-a"),
            ],
            key_env={
                "AI_PROVIDER_PROVIDER_P_API_KEY": "sk-a",
                "AI_PROVIDER_PROVIDER_Q_API_KEY": "sk-b",
            },
            monkeypatch=monkeypatch,
        )

        provider = factory.get_provider_for_alias("chat_cheap")

        assert isinstance(provider, FallbackChainProvider)
        assert len(provider._entries) == 2
        assert [name for name, _ in provider._entries] == ["provider_p", "provider_q"]

    def test_offline_when_real_calls_disabled(self, monkeypatch):
        from app.ai.gateway.offline import OfflineProvider

        with monkeypatch.context() as m:
            m.setattr(factory, "real_provider_active", lambda: False)
            m.setattr(
                runtime_config,
                "current",
                lambda: replace(runtime_config._bootstrap_from_env(), real_calls_active=False),
            )
            provider = factory.get_provider_for_alias("chat_cheap")
        assert isinstance(provider, OfflineProvider)
