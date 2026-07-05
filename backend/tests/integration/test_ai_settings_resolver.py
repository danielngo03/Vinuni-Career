"""ai_settings resolution facade: env-ceiling precedence + consumer wiring (ADR-0011 §2).

The headline proof: the env+key gate is the HARD CEILING. With NO key, setting
``real_calls_enabled=true`` (and even env real-calls on) keeps
``real_calls_active=false`` — an admin can disable AI but can never enable real
calls beyond what env+key permit. Also proves the four rewired consumers read the
published snapshot, and the budget-guard no-op seam never trips offline.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.ai.extraction.adapters import policy as extraction_policy
from app.ai.extraction.adapters.structuring import (
    run_llm_structuring,
    set_llm_structuring_adapter,
)
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import real_provider_active
from app.core.config import get_settings
from app.modules.ai_settings.application import budget_guard, resolver, settings_service
from app.modules.ai_settings.domain import aliases
from app.modules.ai_settings.domain.models import (
    ROLLOUT_ENABLED,
    ROLLOUT_OFFLINE,
    ROLLOUT_PAUSED,
    AiSettings,
)

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


@pytest.fixture(autouse=True)
def _reset_runtime_snapshot():
    runtime_config.reset_to_bootstrap()
    yield
    runtime_config.reset_to_bootstrap()
    get_settings.cache_clear()


def _row(**over) -> AiSettings:
    """In-memory settings row with all fields the resolver reads."""

    base = dict(
        scope="platform",
        real_calls_enabled=False,
        rollout_state=ROLLOUT_ENABLED,
        chat_model_alias="chat_cheap",
        reasoning_model_alias="reasoning_cheap",
        embedding_model_alias="embedding_cheap",
        eval_model_alias="eval_cheap",
        cv_llm_structuring_enabled=False,
        job_fit_ai_explanation_enabled=True,
        daily_budget_usd=Decimal("1.00"),
    )
    base.update(over)
    return AiSettings(**base)


def _set_env(monkeypatch, *, real_calls: bool, key: str) -> None:
    monkeypatch.setenv("AI_REAL_CALLS_ENABLED", "true" if real_calls else "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    get_settings.cache_clear()


_REAL_KEY = "sk-or-v1-resolver-test-key"
_PLACEHOLDER = "replace-with-local-key"


# --------------------------------------------------------------------------- #
# Precedence — env+key is the HARD CEILING                                     #
# --------------------------------------------------------------------------- #


def test_no_key_forces_real_calls_off_even_with_env_and_db_true(monkeypatch) -> None:
    # Env real-calls ON, DB toggle ON, rollout enabled — but NO usable key.
    _set_env(monkeypatch, real_calls=True, key=_PLACEHOLDER)
    cfg = resolver.build_effective_config(_row(real_calls_enabled=True))
    assert cfg.real_calls_active is False  # <- the env-ceiling proof


def test_env_gate_off_forces_real_calls_off_even_with_key_and_db(monkeypatch) -> None:
    _set_env(monkeypatch, real_calls=False, key=_REAL_KEY)
    cfg = resolver.build_effective_config(_row(real_calls_enabled=True))
    assert cfg.real_calls_active is False


def test_db_toggle_off_keeps_real_calls_off_within_envelope(monkeypatch) -> None:
    _set_env(monkeypatch, real_calls=True, key=_REAL_KEY)
    cfg = resolver.build_effective_config(_row(real_calls_enabled=False))
    assert cfg.real_calls_active is False


@pytest.mark.parametrize("state", [ROLLOUT_PAUSED, ROLLOUT_OFFLINE])
def test_rollout_not_enabled_forces_real_calls_off(monkeypatch, state) -> None:
    _set_env(monkeypatch, real_calls=True, key=_REAL_KEY)
    cfg = resolver.build_effective_config(
        _row(real_calls_enabled=True, rollout_state=state)
    )
    assert cfg.real_calls_active is False


def test_all_true_enables_real_calls(monkeypatch) -> None:
    _set_env(monkeypatch, real_calls=True, key=_REAL_KEY)
    cfg = resolver.build_effective_config(
        _row(real_calls_enabled=True, rollout_state=ROLLOUT_ENABLED)
    )
    assert cfg.real_calls_active is True


# --------------------------------------------------------------------------- #
# Consumers read the published snapshot                                       #
# --------------------------------------------------------------------------- #


def test_factory_reflects_published_snapshot(monkeypatch) -> None:
    _set_env(monkeypatch, real_calls=True, key=_REAL_KEY)
    assert real_provider_active() is True  # bootstrap mode mirrors env

    # Publish a snapshot that turns real calls OFF (e.g. admin paused) -> the
    # gateway consumer reflects it immediately.
    runtime_config.publish(
        resolver.build_effective_config(
            _row(real_calls_enabled=True, rollout_state=ROLLOUT_PAUSED)
        )
    )
    assert real_provider_active() is False


def test_structuring_flag_follows_published_snapshot() -> None:
    class _FakeLlm:
        @property
        def available(self) -> bool:
            return True

        def refine(self, text, base_result):
            return {"extracted_data": {"ok": True}, "review_fields": []}

    set_llm_structuring_adapter(_FakeLlm())
    try:
        # Flag OFF in the snapshot -> structuring is gated off.
        runtime_config.publish(
            resolver.build_effective_config(_row(cv_llm_structuring_enabled=False))
        )
        assert run_llm_structuring("extracted text", {"extracted_data": {}}) is None
        assert extraction_policy.resolve_policy().llm_enabled is False

        # Flip the flag ON via the resolver -> structuring now sees it.
        runtime_config.publish(
            resolver.build_effective_config(_row(cv_llm_structuring_enabled=True))
        )
        refined = run_llm_structuring("extracted text", {"extracted_data": {}})
        assert refined == {"extracted_data": {"ok": True}, "review_fields": []}
        assert extraction_policy.resolve_policy().llm_enabled is True
    finally:
        set_llm_structuring_adapter(None)


def test_cv_llm_uses_snapshot_chat_alias(monkeypatch) -> None:
    import asyncio

    from app.ai.cv import llm as cv_llm

    captured: dict[str, str] = {}

    class _CapturingProvider:
        async def complete(self, messages, *, alias, temperature=0.2, max_tokens=1024):
            captured["alias"] = alias
            from app.ai.gateway.base import AICompletion

            return AICompletion(text="ok", model_alias=alias)

    monkeypatch.setattr(cv_llm, "get_provider", lambda: _CapturingProvider())
    runtime_config.publish(
        resolver.build_effective_config(_row(chat_model_alias="reasoning_cheap"))
    )
    asyncio.run(
        cv_llm.generate_note(task_type="t", system_prompt="s", user_content="u")
    )
    assert captured["alias"] == "reasoning_cheap"


# --------------------------------------------------------------------------- #
# DB-backed resolve_and_publish + budget seam + allowlist invariant           #
# --------------------------------------------------------------------------- #


async def test_resolve_and_publish_seeds_and_publishes(db_session) -> None:
    cfg = await resolver.resolve_and_publish(db_session)
    await db_session.commit()
    assert cfg.chat_model_alias == "chat_default"
    assert cfg.real_calls_active is False  # no key in test env
    assert runtime_config.current().chat_model_alias == "chat_default"


async def test_budget_guard_reads_snapshot_and_never_trips_offline(db_session) -> None:
    principal_admin = (
        await make_org_with_admin(db_session, org_type="university")
    )[2]
    await settings_service.get_effective_settings(db_session, principal=principal_admin)
    await settings_service.update_settings(
        db_session, principal=principal_admin,
        payload={"daily_budget_usd": "3.00"}, ctx=CTX,
    )
    assert runtime_config.current().daily_budget_usd == 3.00
    # No-op accumulator (offline calls cost nothing) -> never raises.
    budget_guard.check(0.0)
    budget_guard.check(2.99)


def test_allowlist_is_gateway_resolvable() -> None:
    # Invariant: an admin can never select an alias the gateway cannot resolve.
    aliases.assert_allowlist_resolvable()
