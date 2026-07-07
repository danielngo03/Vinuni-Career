"""Usage-aware governance for the cv/llm hub + ledger idempotency.

Covers the gap where ~15 AI features funnelled through ``app.ai.cv.llm`` and
bypassed the budget/ledger/telemetry path. After wiring an ``AiUsageContext`` in:

- with a context, ``generate_note`` writes exactly one ``ai_usage_log`` row +
  one ``ai_ops_event`` row, attributed to the user;
- without a context, no DB ledger row is written (legacy metadata-only log line);
- an ``idempotency_key`` makes a retried call a no-op — no double-charge and no
  double-counted telemetry;
- a budget refusal (402) propagates as ``PaymentRequiredError`` (never wrapped as
  ``AI_UNAVAILABLE``) and writes a ``blocked`` telemetry span but NO billable
  ledger row.

Run:
    cd backend && uv run pytest tests/ai/gateway/test_usage_governance.py -v
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.ai.gateway.usage_context import (
    BILLING_SCOPE_PARTNER_ORG,
    BILLING_SCOPE_STUDENT,
    BILLING_SCOPE_SYSTEM,
    AiUsageContext,
    billing_scope_for_persona,
)
from app.ai.observability.models import AiOpsEvent, AiUsageLog
from app.shared.exceptions import AIUnavailableError, PaymentRequiredError
from sqlalchemy import func, select


async def _count(db: Any, model: Any) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


# ---------------------------------------------------------------------------
# Context primitive
# ---------------------------------------------------------------------------

def test_billing_scope_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        AiUsageContext(billing_scope="not-a-scope")


def test_billing_scope_for_persona_maps_personas() -> None:
    assert billing_scope_for_persona("student") == BILLING_SCOPE_STUDENT
    assert billing_scope_for_persona("recruiter") == BILLING_SCOPE_PARTNER_ORG
    assert billing_scope_for_persona("partner_member") == BILLING_SCOPE_SYSTEM  # unknown -> system
    assert billing_scope_for_persona(None) == BILLING_SCOPE_SYSTEM


def test_with_idempotency_key_returns_scoped_copy() -> None:
    base = AiUsageContext(user_id=uuid.uuid4())
    keyed = base.with_idempotency_key("op-1")
    assert base.idempotency_key is None
    assert keyed.idempotency_key == "op-1"
    assert keyed.user_id == base.user_id


# ---------------------------------------------------------------------------
# cv/llm governed accounting (offline provider)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_note_without_context_writes_no_ledger_row(db_session: Any) -> None:
    from app.ai.cv.llm import generate_note

    text = await generate_note(
        task_type="cv_rewrite",
        system_prompt="You are a helpful CV assistant.",
        user_content="Improve this bullet.",
    )
    assert isinstance(text, str)
    # Legacy behaviour: metadata log line only, no durable ledger/telemetry row.
    assert await _count(db_session, AiUsageLog) == 0
    assert await _count(db_session, AiOpsEvent) == 0


@pytest.mark.asyncio
async def test_generate_note_with_context_writes_ledger_and_ops_event(db_session: Any) -> None:
    from app.ai.cv.llm import generate_note

    uid = uuid.uuid4()
    usage = AiUsageContext(db=db_session, user_id=uid, billing_scope=BILLING_SCOPE_STUDENT)
    text = await generate_note(
        task_type="cv_rewrite",
        system_prompt="You are a helpful CV assistant.",
        user_content="Improve this bullet.",
        usage=usage,
    )
    assert isinstance(text, str)

    rows = (await db_session.execute(select(AiUsageLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == uid
    assert rows[0].success is True
    assert rows[0].task_type == "cv_rewrite"
    # Ops telemetry span written too (admin-only richer row).
    assert await _count(db_session, AiOpsEvent) == 1


# ---------------------------------------------------------------------------
# Idempotency / no-double-charge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_ai_usage_async_dedups_on_idempotency_key(db_session: Any) -> None:
    from app.ai.observability.usage import log_ai_usage_async

    first = await log_ai_usage_async(
        db_session, task_type="cv_rewrite", alias="chat_default", success=True,
        idempotency_key="op-42",
    )
    second = await log_ai_usage_async(
        db_session, task_type="cv_rewrite", alias="chat_default", success=True,
        idempotency_key="op-42",
    )
    assert first is True
    assert second is False  # dedup no-op — not charged again
    assert await _count(db_session, AiUsageLog) == 1


@pytest.mark.asyncio
async def test_generate_note_idempotency_key_prevents_double_charge(db_session: Any) -> None:
    from app.ai.cv.llm import generate_note

    usage = AiUsageContext(db=db_session, user_id=uuid.uuid4()).with_idempotency_key("cv:1")
    for _ in range(2):
        await generate_note(
            task_type="cv_rewrite",
            system_prompt="You are a helpful CV assistant.",
            user_content="Improve this bullet.",
            usage=usage,
        )
    # Retried logical operation must not double-charge the ledger OR the telemetry.
    assert await _count(db_session, AiUsageLog) == 1
    assert await _count(db_session, AiOpsEvent) == 1


# ---------------------------------------------------------------------------
# Budget refusal propagates + no billable row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_budget_refusal_propagates_and_writes_no_ledger_row(
    db_session: Any, monkeypatch: Any
) -> None:
    from app.ai.cv.llm import generate_note

    monkeypatch.setattr(
        "app.ai.gateway.factory.real_provider_active", lambda: True, raising=True
    )

    async def _refuse(*_a: Any, **_kw: Any) -> None:
        raise PaymentRequiredError(details={"reason": "BUDGET_EXCEEDED"})

    monkeypatch.setattr(
        "app.modules.ai_settings.application.budget_guard.check_async",
        _refuse,
        raising=False,
    )

    usage = AiUsageContext(db=db_session, user_id=uuid.uuid4())
    with pytest.raises(PaymentRequiredError):
        await generate_note(
            task_type="cv_rewrite",
            system_prompt="You are a helpful CV assistant.",
            user_content="Improve this bullet.",
            usage=usage,
        )
    # 402 is NOT wrapped as AI_UNAVAILABLE; no billable ledger row; blocked span only.
    assert await _count(db_session, AiUsageLog) == 0
    events = (await db_session.execute(select(AiOpsEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].status == "blocked"


@pytest.mark.asyncio
async def test_provider_failure_still_maps_to_ai_unavailable(
    db_session: Any, monkeypatch: Any
) -> None:
    from app.ai.cv import llm

    class _Down:
        name = "offline"

        async def complete(self, *_a: Any, **_kw: Any) -> Any:
            raise RuntimeError("provider down")

    monkeypatch.setattr(llm, "get_provider", lambda: _Down(), raising=True)

    usage = AiUsageContext(db=db_session, user_id=uuid.uuid4())
    with pytest.raises(AIUnavailableError):
        await llm.generate_note(
            task_type="cv_rewrite",
            system_prompt="You are a helpful CV assistant.",
            user_content="Improve this bullet.",
            usage=usage,
        )
    # Failure is ledgered as success=False (one row), with an error telemetry span.
    rows = (await db_session.execute(select(AiUsageLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].success is False
