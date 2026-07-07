"""Tests for ops_recorder: AiOpsEvent insert + AiUsageDaily upsert.

TDD: tests written first (Task 2).  Run:
    cd backend && uv run pytest tests/ai/observability/test_ops_recorder.py -v
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.observability import ops_recorder
from app.ai.observability.models import (
    AiOpsEvent,
    AiUsageDaily,
)
from sqlalchemy import select


@pytest.mark.asyncio
async def test_record_writes_event_and_upserts_daily(db_session):
    ev = ops_recorder.OpsEventInput(
        task_type="job_fit",
        alias="reasoning_default",
        provider="openrouter",
        model="deepseek/deepseek-r1",
        prompt_tokens=1000,
        completion_tokens=200,
        latency_ms=850,
        status="ok",
        fallback_used=False,
        circuit_open=False,
        cost_usd=0.01,
        unpriced=False,
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        session_id=None,
        request_id="req_abc",
        langfuse_trace_id="tr_1",
    )
    await ops_recorder.record_ops_event(db_session, event=ev)
    await ops_recorder.record_ops_event(db_session, event=ev)  # same day, same grain

    events = (await db_session.scalars(select(AiOpsEvent))).all()
    assert len(events) == 2

    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily) == 1  # upserted, not duplicated
    assert daily[0].requests == 2
    assert daily[0].prompt_tokens == 2000


@pytest.mark.asyncio
async def test_record_never_raises_on_bad_input(db_session):
    # missing required fields must not bubble up into the AI call path
    await ops_recorder.record_ops_event(db_session, event=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_error_status_increments_errors(db_session):
    ev = ops_recorder.OpsEventInput(
        task_type="cv_bullets",
        alias="chat_default",
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=500,
        completion_tokens=0,
        latency_ms=200,
        status="error",
        fallback_used=False,
        circuit_open=False,
        cost_usd=None,
        unpriced=True,
        org_id=None,
        user_id=None,
        session_id=None,
        request_id=None,
        langfuse_trace_id=None,
    )
    await ops_recorder.record_ops_event(db_session, event=ev)

    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily) == 1
    assert daily[0].errors == 1
    assert daily[0].fallbacks == 0


@pytest.mark.asyncio
async def test_fallback_increments_fallbacks(db_session):
    ev = ops_recorder.OpsEventInput(
        task_type="jd_extraction",
        alias="chat_default",
        provider="openrouter",
        model="deepseek/deepseek-v4-flash",
        prompt_tokens=300,
        completion_tokens=100,
        latency_ms=400,
        status="ok",
        fallback_used=True,
        circuit_open=False,
        cost_usd=0.001,
        unpriced=False,
        org_id=None,
        user_id=None,
        session_id=None,
        request_id=None,
        langfuse_trace_id=None,
    )
    await ops_recorder.record_ops_event(db_session, event=ev)

    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert daily[0].fallbacks == 1


@pytest.mark.asyncio
async def test_none_provider_model_maps_to_empty_string_grain(db_session):
    """Provider/model None must not create NULL-grain rows; must use empty string."""
    ev = ops_recorder.OpsEventInput(
        task_type="embedding",
        alias="embedding_default",
        provider=None,
        model=None,
        prompt_tokens=100,
        completion_tokens=0,
        latency_ms=50,
        status="ok",
        fallback_used=False,
        circuit_open=False,
        cost_usd=None,
        unpriced=True,
        org_id=None,
        user_id=None,
        session_id=None,
        request_id=None,
        langfuse_trace_id=None,
    )
    await ops_recorder.record_ops_event(db_session, event=ev)
    await ops_recorder.record_ops_event(db_session, event=ev)

    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily) == 1
    assert daily[0].provider == ""
    assert daily[0].model == ""
    assert daily[0].requests == 2


@pytest.mark.asyncio
async def test_cost_accumulates_across_calls(db_session):
    base = {
        "task_type": "cover_letter",
        "alias": "chat_default",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "prompt_tokens": 200,
        "completion_tokens": 150,
        "latency_ms": 600,
        "status": "ok",
        "fallback_used": False,
        "circuit_open": False,
        "unpriced": False,
        "org_id": None,
        "user_id": None,
        "session_id": None,
        "request_id": None,
        "langfuse_trace_id": None,
    }
    ev1 = ops_recorder.OpsEventInput(**{**base, "cost_usd": 0.005})
    ev2 = ops_recorder.OpsEventInput(**{**base, "cost_usd": 0.003})
    await ops_recorder.record_ops_event(db_session, event=ev1)
    await ops_recorder.record_ops_event(db_session, event=ev2)

    daily = (await db_session.scalars(select(AiUsageDaily))).all()
    assert len(daily) == 1
    assert float(daily[0].cost_usd) == pytest.approx(0.008)
    assert daily[0].completion_tokens == 300
