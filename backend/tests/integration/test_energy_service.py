"""AI-energy settlement choke point (``billing.energy_service.charge``).

The runner-facing settlement point recreated for the cost-control foundation:
every AI result records exactly one durable, idempotent ``ai_billable_usage``
row and — for a chargeable user/org-scoped result — decrements the masked
top-up wallet for the portion of the charge that overflows the weekly allowance.

Covers: charge idempotency (duplicate key == single charge, no double
decrement), ledger row written, masked wallet decrement, exhaustion read model,
and the never-raises-on-failure contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    PERSONA_PARTNER,
    PERSONA_STUDENT,
    RESULT_BLOCKED,
    RESULT_PROVIDER_FAILED,
    RESULT_SUCCESS,
    SCOPE_ORG,
    SCOPE_USER,
    UsageContext,
    make_idempotency_key,
)
from app.ai.observability.models import AiBillableUsage
from app.modules.billing.application import energy_service
from app.modules.billing.application.energy_service import (
    ACCOUNT_SCOPE_ORG,
    ACCOUNT_SCOPE_USER,
    base_units_for,
    charge,
    energy_state,
    is_exhausted,
)
from app.modules.billing.domain.models import AiEnergyAccount
from sqlalchemy import func, select


def _ctx(**over) -> UsageContext:
    base: dict = {
        "actor_persona": PERSONA_STUDENT,
        "feature_key": FEATURE_CHATBOT,
        "task_type": "ai_assistant_chat",
        "billing_scope": SCOPE_USER,
        "actor_user_id": uuid.uuid4(),
    }
    base.update(over)
    return UsageContext(**base)


async def _count_rows(session) -> int:
    return await session.scalar(select(func.count()).select_from(AiBillableUsage))


async def _sum_units(session) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0))
        )
    )


# --------------------------------------------------------------------------- #
# Ledger row written                                                          #
# --------------------------------------------------------------------------- #


async def test_success_writes_one_ledger_row_with_feature_weight(db_session) -> None:
    ctx = _ctx()
    await charge(db_session, ctx=ctx, result_status=RESULT_SUCCESS)
    await db_session.commit()

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].result_status == RESULT_SUCCESS
    assert rows[0].units_charged == base_units_for(FEATURE_CHATBOT) == 1
    assert rows[0].feature_key == FEATURE_CHATBOT


async def test_explicit_base_units_overrides_feature_weight(db_session) -> None:
    # A direct caller (e.g. the voice relay) may pass an explicit weight.
    await charge(db_session, ctx=_ctx(), result_status=RESULT_SUCCESS, base_units=7)
    await db_session.commit()

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 1
    assert rows[0].units_charged == 7


async def test_blocked_and_failed_record_zero_units(db_session) -> None:
    await charge(db_session, ctx=_ctx(), result_status=RESULT_BLOCKED, base_units=5)
    await charge(db_session, ctx=_ctx(), result_status=RESULT_PROVIDER_FAILED, base_units=5)
    await db_session.commit()

    rows = (await db_session.scalars(select(AiBillableUsage))).all()
    assert len(rows) == 2
    assert {r.result_status for r in rows} == {RESULT_BLOCKED, RESULT_PROVIDER_FAILED}
    assert all(r.units_charged == 0 for r in rows)


# --------------------------------------------------------------------------- #
# Idempotency (duplicate key == single charge)                                #
# --------------------------------------------------------------------------- #


async def test_duplicate_idempotency_key_charges_once(db_session) -> None:
    key = make_idempotency_key(FEATURE_CHATBOT, "session-x", "turn-7")
    ctx = _ctx(idempotency_key=key)

    for _ in range(3):  # client retries / celery redeliveries of the SAME turn
        await charge(db_session, ctx=ctx, result_status=RESULT_SUCCESS)
        await db_session.commit()

    assert await _count_rows(db_session) == 1
    assert await _sum_units(db_session) == 1


async def test_no_idempotency_key_allows_repeat_events(db_session) -> None:
    ctx = _ctx()  # no key → genuinely distinct one-off events
    for _ in range(2):
        await charge(db_session, ctx=ctx, result_status=RESULT_SUCCESS)
        await db_session.commit()

    assert await _count_rows(db_session) == 2


# --------------------------------------------------------------------------- #
# Masked wallet decrement                                                     #
# --------------------------------------------------------------------------- #


async def _seed_account(
    session,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    weekly_allowance_units: int | None,
    wallet_units: int,
    org_id: uuid.UUID | None = None,
) -> AiEnergyAccount:
    account = AiEnergyAccount(
        scope_type=scope_type,
        scope_id=scope_id,
        org_id=org_id,
        weekly_allowance_units=weekly_allowance_units,
        wallet_units=wallet_units,
    )
    session.add(account)
    await session.commit()
    return account


async def test_wallet_untouched_while_within_weekly_allowance(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=10,
        wallet_units=50,
    )
    # 3 units charged, allowance 10 → nothing overflows to the wallet.
    await charge(
        db_session,
        ctx=_ctx(actor_user_id=user_id),
        result_status=RESULT_SUCCESS,
        base_units=3,
    )
    await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 50


async def test_wallet_decremented_only_for_overflow(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=5,
        wallet_units=50,
    )
    # Charge 8 in one go: 5 covered by weekly allowance, 3 overflow → wallet -3.
    await charge(
        db_session,
        ctx=_ctx(actor_user_id=user_id),
        result_status=RESULT_SUCCESS,
        base_units=8,
    )
    await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 47


async def test_wallet_overflow_spans_multiple_charges(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=5,
        wallet_units=50,
    )
    # First charge 4 (total 4 ≤ 5) → no wallet spend.
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=4
    )
    await db_session.commit()
    # Second charge 4 (total 8, allowance 5) → only 3 overflow → wallet -3.
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=4
    )
    await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 47


async def test_wallet_never_goes_negative(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=1,
        wallet_units=2,
    )
    # Overflow (99) far exceeds the 2-unit wallet → floors at 0, never negative.
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=100
    )
    await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 0


async def test_duplicate_key_does_not_double_decrement_wallet(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=5,
        wallet_units=50,
    )
    key = make_idempotency_key(FEATURE_CHATBOT, "s", "turn-1")
    ctx = _ctx(actor_user_id=user_id, idempotency_key=key)
    for _ in range(3):  # retries of the same overflow charge
        await charge(db_session, ctx=ctx, result_status=RESULT_SUCCESS, base_units=8)
        await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 47  # decremented exactly once
    assert await _count_rows(db_session) == 1


async def test_org_scope_decrements_org_wallet(db_session) -> None:
    org_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_ORG,
        scope_id=org_id,
        weekly_allowance_units=5,
        wallet_units=40,
        org_id=org_id,
    )
    ctx = _ctx(
        actor_persona=PERSONA_PARTNER,
        billing_scope=SCOPE_ORG,
        org_id=org_id,
        actor_user_id=uuid.uuid4(),
    )
    await charge(db_session, ctx=ctx, result_status=RESULT_SUCCESS, base_units=8)
    await db_session.commit()

    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == org_id)
    )
    assert account.wallet_units == 37


async def test_no_account_row_still_writes_ledger(db_session) -> None:
    # Student with no wallet row: ledger is still written, nothing to decrement.
    await charge(db_session, ctx=_ctx(), result_status=RESULT_SUCCESS, base_units=3)
    await db_session.commit()
    assert await _count_rows(db_session) == 1


# --------------------------------------------------------------------------- #
# Exhaustion read model                                                       #
# --------------------------------------------------------------------------- #


async def test_energy_state_reports_remaining_and_exhaustion(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=10,
        wallet_units=5,
    )
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=4
    )
    await db_session.commit()

    state = await energy_state(
        db_session, scope_type=ACCOUNT_SCOPE_USER, scope_id=user_id
    )
    assert state.consumed_units == 4
    assert state.weekly_allowance_units == 10
    assert state.wallet_units == 5
    assert state.remaining_units == 11  # 10 + 5 - 4
    assert state.exhausted is False


async def test_is_exhausted_true_when_allowance_and_wallet_spent(db_session) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=3,
        wallet_units=2,
    )
    # Consume 5 (== allowance 3 + wallet 2) → exhausted.
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=5
    )
    await db_session.commit()

    assert await is_exhausted(
        db_session, scope_type=ACCOUNT_SCOPE_USER, scope_id=user_id
    ) is True


# --------------------------------------------------------------------------- #
# Never raises on failure (best-effort accounting contract)                   #
# --------------------------------------------------------------------------- #


async def test_charge_swallows_ledger_failure(db_session, monkeypatch) -> None:
    async def _boom(*_a, **_kw):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(energy_service, "record_billable_usage", _boom)
    # Must NOT raise — accounting failure can never break the AI response.
    await charge(db_session, ctx=_ctx(), result_status=RESULT_SUCCESS)


async def test_charge_swallows_wallet_failure_but_keeps_ledger(db_session, monkeypatch) -> None:
    user_id = uuid.uuid4()
    await _seed_account(
        db_session,
        scope_type=ACCOUNT_SCOPE_USER,
        scope_id=user_id,
        weekly_allowance_units=1,
        wallet_units=10,
    )

    async def _boom(*_a, **_kw):
        raise RuntimeError("wallet query exploded")

    monkeypatch.setattr(energy_service, "_consumed_this_week", _boom)
    # Wallet settlement blows up, but charge swallows it and the ledger row stays.
    await charge(
        db_session, ctx=_ctx(actor_user_id=user_id), result_status=RESULT_SUCCESS, base_units=8
    )
    await db_session.commit()

    assert await _count_rows(db_session) == 1
    account = await db_session.scalar(
        select(AiEnergyAccount).where(AiEnergyAccount.scope_id == user_id)
    )
    assert account.wallet_units == 10  # untouched — savepoint rolled back


async def test_charge_never_charges_on_non_success_even_with_units(db_session) -> None:
    ctx = _ctx()
    await charge(db_session, ctx=ctx, result_status="validation_failed", base_units=9)
    await db_session.commit()

    row = await db_session.scalar(select(AiBillableUsage))
    assert row.units_charged == 0


# --------------------------------------------------------------------------- #
# Sanity: week window helper                                                   #
# --------------------------------------------------------------------------- #


def test_week_start_is_utc_monday_midnight() -> None:
    # 2026-07-10 is a Friday; the week starts Monday 2026-07-06 00:00 UTC.
    friday = datetime(2026, 7, 10, 15, 30, tzinfo=UTC)
    ws = energy_service._week_start(friday)
    assert ws == datetime(2026, 7, 6, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("feature", [FEATURE_CHATBOT])
def test_chatbot_weight_is_one(feature: str) -> None:
    # The task_runner billable test relies on chatbot charging exactly 1 unit.
    assert base_units_for(feature) == 1
