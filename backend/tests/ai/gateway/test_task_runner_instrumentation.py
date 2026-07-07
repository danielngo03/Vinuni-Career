"""Task 4 — AiTaskRunner instrumentation tests.

TDD: tests written first.  After ``complete()`` on an offline/fake provider:
- One ``AiOpsEvent`` row is written with resolved provider/model, real token
  counts, latency_ms >= 0, and status="ok".
- The existing ``AiUsageLog`` row is STILL written (never regressions the
  existing observability path).

Also covers:
- Error path → status="error", event row still written, AIUnavailableError
  re-raised.
- Budget-blocked path → status="blocked", event row written,
  PaymentRequiredError re-raised.
- ``org_id`` is stored on the event row.

Run:
    cd backend && uv run pytest tests/ai/gateway/ -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage, AIProvider
from app.ai.observability.models import AiOpsEvent, AiUsageLog
from sqlalchemy import func, select

# ---------------------------------------------------------------------------
# Fake provider returning known usage
# ---------------------------------------------------------------------------

class FakeProvider(AIProvider):
    """Deterministic test provider with known prompt/completion token counts."""

    name = "fake_provider"

    def __init__(
        self,
        *,
        prompt_tokens: int = 42,
        completion_tokens: int = 17,
        fail: bool = False,
    ) -> None:
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._fail = fail

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        if self._fail:
            raise RuntimeError("fake provider error")
        return AICompletion(
            text="hello from fake",
            model_alias=alias,
            usage={
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
            },
            finish_reason="stop",
        )

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        if self._fail:
            raise RuntimeError("fake stream error")
        yield "hello "
        yield "from fake"

    async def embed(
        self,
        texts: list[str],
        *,
        alias: str,
    ) -> list[AIEmbedding]:
        return [
            AIEmbedding(
                vector=[0.1, 0.2, 0.3],
                model_alias=alias,
                usage={"prompt_tokens": len(t), "completion_tokens": 0},
            )
            for t in texts
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_provider(monkeypatch: Any, provider: AIProvider) -> None:
    """Patch gateway factory so AiTaskRunner uses our fake provider.

    ``complete()`` imports ``get_provider_for_alias`` and ``real_provider_active``
    directly from ``app.ai.gateway.factory`` inside the method body, so we must
    patch the names on that module — not on ``task_runner``.  We also patch
    ``check_async`` on ``budget_guard`` (the module the task_runner imports from).
    """
    # Patch factory so the local imports inside complete()/stream() see the
    # right values when they do:
    #   from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
    monkeypatch.setattr(
        "app.ai.gateway.factory.get_provider_for_alias",
        lambda alias: provider,
        raising=True,
    )
    monkeypatch.setattr(
        "app.ai.gateway.factory.real_provider_active",
        lambda: True,
        raising=True,
    )
    # Patch the budget guard to be a no-op for these tests.
    async def _noop_check(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.ai_settings.application.budget_guard.check_async",
        _noop_check,
        raising=False,
    )


# ---------------------------------------------------------------------------
# Core test: ops event + usage log both written
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_writes_ops_event_and_keeps_usage_log(
    db_session: Any, monkeypatch: Any
) -> None:
    """After complete(), exactly one AiOpsEvent AND one AiUsageLog row exist."""
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider(prompt_tokens=42, completion_tokens=17))

    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )
    await runner.complete([AIMessage(role="user", content="hi")])

    assert (
        await db_session.scalar(select(func.count()).select_from(AiOpsEvent))
    ) == 1
    assert (
        await db_session.scalar(select(func.count()).select_from(AiUsageLog))
    ) == 1


@pytest.mark.asyncio
async def test_complete_ops_event_has_correct_fields(
    db_session: Any, monkeypatch: Any
) -> None:
    """The AiOpsEvent row has resolved provider/model, real tokens, latency >= 0, status=ok."""
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider(prompt_tokens=42, completion_tokens=17))

    # Deterministically inject a known (provider, model) so the assertion is
    # not coupled to runtime_config bootstrap state in the test environment.
    monkeypatch.setattr(
        "app.ai.gateway.task_runner._resolve_provider_model",
        lambda alias: ("test_provider", "test-model-v1"),
        raising=True,
    )

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        user_id=user_id,
        org_id=org_id,
    )
    await runner.complete([AIMessage(role="user", content="hi")])

    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 1
    ev = events[0]

    assert ev.task_type == "unit_test"
    assert ev.alias == "chat_default"
    # Exact values injected by monkeypatch above — deterministic regardless of
    # runtime_config bootstrap state.
    assert ev.provider == "test_provider"
    assert ev.model == "test-model-v1"
    assert ev.prompt_tokens == 42
    assert ev.completion_tokens == 17
    assert ev.latency_ms is not None
    assert ev.latency_ms >= 0
    assert ev.status == "ok"
    assert ev.org_id == org_id
    assert ev.user_id == user_id
    assert ev.fallback_used is False


@pytest.mark.asyncio
async def test_complete_error_path_writes_ops_event_with_error_status(
    db_session: Any, monkeypatch: Any
) -> None:
    """Provider error → status='error' event written AND AIUnavailableError re-raised."""
    from app.ai.gateway.task_runner import AiTaskRunner
    from app.shared.exceptions import AIUnavailableError

    _patch_provider(monkeypatch, FakeProvider(fail=True))

    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test_error",
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )

    with pytest.raises(AIUnavailableError):
        await runner.complete([AIMessage(role="user", content="hi")])

    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 1
    assert events[0].status == "error"


@pytest.mark.asyncio
async def test_complete_budget_blocked_writes_ops_event_with_blocked_status(
    db_session: Any, monkeypatch: Any
) -> None:
    """Budget rejection → status='blocked' event written AND PaymentRequiredError re-raised."""
    from app.ai.gateway.task_runner import AiTaskRunner
    from app.shared.exceptions import PaymentRequiredError

    # complete() imports these directly from factory/budget_guard at call time,
    # so patch the source modules — not the task_runner namespace.
    monkeypatch.setattr(
        "app.ai.gateway.factory.real_provider_active",
        lambda: True,
        raising=True,
    )
    monkeypatch.setattr(
        "app.ai.gateway.factory.get_provider_for_alias",
        lambda alias: FakeProvider(),
        raising=True,
    )

    async def _budget_exceeded(*_a: Any, **_kw: Any) -> None:
        raise PaymentRequiredError(
            "budget exceeded",
            details={"reason": "BUDGET_EXCEEDED"},
        )

    # task_runner imports check_async from budget_guard at call time; patch there.
    monkeypatch.setattr(
        "app.modules.ai_settings.application.budget_guard.check_async",
        _budget_exceeded,
        raising=False,
    )

    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test_blocked",
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
    )

    with pytest.raises(PaymentRequiredError):
        await runner.complete([AIMessage(role="user", content="hi")])

    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 1
    assert events[0].status == "blocked"


@pytest.mark.asyncio
async def test_complete_org_id_none_is_accepted(
    db_session: Any, monkeypatch: Any
) -> None:
    """org_id=None (default) is backward-compatible — no exception."""
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider())

    # Old-style call without org_id
    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="legacy_call",
        user_id=uuid.uuid4(),
    )
    await runner.complete([AIMessage(role="user", content="hi")])

    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 1
    assert events[0].org_id is None


@pytest.mark.asyncio
async def test_complete_no_db_does_not_crash(monkeypatch: Any) -> None:
    """When db=None (fire-and-forget path), complete() still returns without error."""
    from app.ai.gateway.task_runner import AiTaskRunner

    # No DB — just check no crash.
    # complete() imports real_provider_active directly from factory at call
    # time, so the patch must target the factory module, not task_runner.
    monkeypatch.setattr(
        "app.ai.gateway.factory.real_provider_active",
        lambda: False,
        raising=True,
    )

    runner = AiTaskRunner(
        None,
        alias="chat_default",
        task_type="no_db_call",
    )
    result = await runner.complete([AIMessage(role="user", content="ping")])
    assert result.text  # offline provider returns something
