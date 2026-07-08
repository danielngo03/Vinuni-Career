"""AiTaskRunner billable-ledger integration (B-579 wiring).

When a call site passes a ``UsageContext``, every terminal outcome records
exactly one durable ``ai_billable_usage`` row with the correct charge decision:
success charges ``charge_units``; blocked / provider_failed record the event
with 0 units (§3.2). Without a ``UsageContext`` the runner is unchanged (no
billable rows). Charges are idempotent on the context's ``idempotency_key``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.ai.gateway.base import AIMessage
from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    PERSONA_STUDENT,
    SCOPE_USER,
    UsageContext,
    make_idempotency_key,
)
from app.ai.observability.models import AiBillableUsage
from sqlalchemy import func, select

from tests.ai.gateway.test_task_runner_instrumentation import (
    FakeProvider,
    _patch_provider,
)


def _ctx(**over) -> UsageContext:
    base = {
        "actor_persona": PERSONA_STUDENT,
        "feature_key": FEATURE_CHATBOT,
        "task_type": "unit_test",
        "billing_scope": SCOPE_USER,
        "actor_user_id": uuid.uuid4(),
    }
    base.update(over)
    return UsageContext(**base)


async def _count_billable(db) -> int:
    return await db.scalar(select(func.count()).select_from(AiBillableUsage))


@pytest.mark.asyncio
async def test_success_records_one_charge(db_session: Any, monkeypatch: Any) -> None:
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider())
    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        usage_context=_ctx(),
        charge_units=1,
    )
    await runner.complete([AIMessage(role="user", content="hi")])

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].result_status == "success"
    assert rows[0].units_charged == 1
    assert rows[0].feature_key == FEATURE_CHATBOT


@pytest.mark.asyncio
async def test_no_usage_context_records_nothing(db_session: Any, monkeypatch: Any) -> None:
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider())
    runner = AiTaskRunner(db_session, alias="chat_default", task_type="unit_test")
    await runner.complete([AIMessage(role="user", content="hi")])

    assert await _count_billable(db_session) == 0


@pytest.mark.asyncio
async def test_provider_error_records_failed_no_charge(db_session: Any, monkeypatch: Any) -> None:
    from app.ai.gateway.task_runner import AiTaskRunner
    from app.shared.exceptions import AIUnavailableError

    _patch_provider(monkeypatch, FakeProvider(fail=True))
    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        usage_context=_ctx(),
        charge_units=3,
    )
    with pytest.raises(AIUnavailableError):
        await runner.complete([AIMessage(role="user", content="hi")])

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].result_status == "provider_failed"
    assert rows[0].units_charged == 0


@pytest.mark.asyncio
async def test_budget_blocked_records_blocked_no_charge(db_session: Any, monkeypatch: Any) -> None:
    from app.ai.gateway.task_runner import AiTaskRunner
    from app.shared.exceptions import PaymentRequiredError

    monkeypatch.setattr(
        "app.ai.gateway.factory.real_provider_active", lambda: True, raising=True
    )
    monkeypatch.setattr(
        "app.ai.gateway.factory.get_provider_for_alias",
        lambda alias: FakeProvider(),
        raising=True,
    )

    async def _budget_exceeded(*_a: Any, **_kw: Any) -> None:
        raise PaymentRequiredError("budget exceeded", details={"reason": "BUDGET_EXCEEDED"})

    monkeypatch.setattr(
        "app.modules.ai_settings.application.budget_guard.check_async",
        _budget_exceeded,
        raising=False,
    )

    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        usage_context=_ctx(),
        charge_units=2,
    )
    with pytest.raises(PaymentRequiredError):
        await runner.complete([AIMessage(role="user", content="hi")])

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].result_status == "blocked"
    assert rows[0].units_charged == 0


@pytest.mark.asyncio
async def test_stream_success_records_one_charge(db_session: Any, monkeypatch: Any) -> None:
    """A streamed turn that produces text records a single success charge."""
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider())
    runner = AiTaskRunner(
        db_session,
        alias="chat_default",
        task_type="unit_test",
        usage_context=_ctx(),
        charge_units=1,
    )
    chunks = [c async for c in runner.stream([AIMessage(role="user", content="hi")])]
    assert "".join(chunks)  # produced text

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].result_status == "success"
    assert rows[0].units_charged == 1


@pytest.mark.asyncio
async def test_idempotent_no_double_charge_on_retry(db_session: Any, monkeypatch: Any) -> None:
    from app.ai.gateway.task_runner import AiTaskRunner

    _patch_provider(monkeypatch, FakeProvider())
    user_id = uuid.uuid4()
    ctx = _ctx(
        actor_user_id=user_id,
        idempotency_key=make_idempotency_key(FEATURE_CHATBOT, "session-x", "turn-7"),
    )
    for _ in range(2):  # a client retry of the same turn
        runner = AiTaskRunner(
            db_session,
            alias="chat_default",
            task_type="unit_test",
            usage_context=ctx,
            charge_units=1,
        )
        await runner.complete([AIMessage(role="user", content="hi")])

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1  # charged once despite two runs
    assert rows[0].units_charged == 1
