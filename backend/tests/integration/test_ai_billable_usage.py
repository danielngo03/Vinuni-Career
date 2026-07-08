"""Billable AI usage ledger foundation (B-579).

Covers the charge-decision rules (§3.2), idempotency (no double-charge on
retry/redelivery/cache), provider-cost attribution without billing, and the
per-user credit summary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    FEATURE_CV_FIT_EXPLANATION,
    PERSONA_STUDENT,
    RESULT_BLOCKED,
    RESULT_CACHED,
    RESULT_PROVIDER_FAILED,
    RESULT_SUCCESS,
    SCOPE_USER,
    UsageContext,
    billable_summary,
    make_idempotency_key,
    record_billable_usage,
    units_for,
)


def _ctx(**over) -> UsageContext:
    base = {
        "actor_persona": PERSONA_STUDENT,
        "feature_key": FEATURE_CHATBOT,
        "task_type": "ai_assistant_chat",
        "billing_scope": SCOPE_USER,
        "actor_user_id": uuid.uuid4(),
    }
    base.update(over)
    return UsageContext(**base)


def test_units_for_only_charges_on_success() -> None:
    assert units_for(RESULT_SUCCESS, 2) == 2
    for status in (RESULT_BLOCKED, RESULT_PROVIDER_FAILED, RESULT_CACHED, "validation_failed"):
        assert units_for(status, 2) == 0


async def test_success_charges_units(db_session) -> None:
    row = await record_billable_usage(
        db_session, ctx=_ctx(), result_status=RESULT_SUCCESS, base_units=1
    )
    assert row.id is not None
    assert row.units_charged == 1
    assert row.result_status == RESULT_SUCCESS


async def test_blocked_and_failed_record_but_do_not_charge(db_session) -> None:
    blocked = await record_billable_usage(
        db_session, ctx=_ctx(), result_status=RESULT_BLOCKED, base_units=5
    )
    failed = await record_billable_usage(
        db_session, ctx=_ctx(), result_status=RESULT_PROVIDER_FAILED, base_units=5
    )
    assert blocked.units_charged == 0
    assert blocked.result_status == RESULT_BLOCKED
    assert failed.units_charged == 0


async def test_provider_cost_recorded_even_when_not_charged(db_session) -> None:
    row = await record_billable_usage(
        db_session,
        ctx=_ctx(),
        result_status=RESULT_PROVIDER_FAILED,
        base_units=2,
        provider_cost_usd=0.0004,
    )
    assert row.units_charged == 0
    assert float(row.provider_cost_usd) == 0.0004


async def test_idempotent_no_double_charge(db_session) -> None:
    user_id = uuid.uuid4()
    key = make_idempotency_key(FEATURE_CV_FIT_EXPLANATION, "cvv1", "jobv1")
    ctx = _ctx(
        actor_user_id=user_id,
        feature_key=FEATURE_CV_FIT_EXPLANATION,
        task_type="cv_fit_explanation",
        idempotency_key=key,
    )
    first = await record_billable_usage(
        db_session, ctx=ctx, result_status=RESULT_SUCCESS, base_units=1
    )
    second = await record_billable_usage(
        db_session, ctx=ctx, result_status=RESULT_SUCCESS, base_units=1
    )
    assert first.id == second.id  # same row returned, no second insert

    since = datetime.now(UTC) - timedelta(hours=1)
    summary = await billable_summary(db_session, actor_user_id=user_id, since=since)
    assert summary["total_units"] == 1  # charged once, not twice


async def test_no_idempotency_key_always_inserts(db_session) -> None:
    user_id = uuid.uuid4()
    a = await record_billable_usage(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=1
    )
    b = await record_billable_usage(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=1
    )
    assert a.id != b.id


async def test_billable_summary_totals_by_feature(db_session) -> None:
    user_id = uuid.uuid4()
    await record_billable_usage(
        db_session,
        ctx=_ctx(actor_user_id=user_id, feature_key=FEATURE_CHATBOT, task_type="ai_assistant_chat"),
        result_status=RESULT_SUCCESS,
        base_units=1,
    )
    await record_billable_usage(
        db_session,
        ctx=_ctx(
            actor_user_id=user_id,
            feature_key=FEATURE_CV_FIT_EXPLANATION,
            task_type="cv_fit_explanation",
        ),
        result_status=RESULT_SUCCESS,
        base_units=2,
    )
    # A blocked call for the same user contributes 0 to the meter.
    await record_billable_usage(
        db_session,
        ctx=_ctx(actor_user_id=user_id, feature_key=FEATURE_CHATBOT, task_type="ai_assistant_chat"),
        result_status=RESULT_BLOCKED,
        base_units=1,
    )
    since = datetime.now(UTC) - timedelta(hours=1)
    summary = await billable_summary(db_session, actor_user_id=user_id, since=since)
    assert summary["by_feature"][FEATURE_CHATBOT] == 1
    assert summary["by_feature"][FEATURE_CV_FIT_EXPLANATION] == 2
    assert summary["total_units"] == 3
