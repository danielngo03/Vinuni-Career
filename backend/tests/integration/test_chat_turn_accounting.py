"""Per-turn telemetry + energy/billable accounting tests (Lane A).

- ``record_turn_billable`` is idempotent on the assistant message id (a double
  call yields exactly ONE ledger row).
- Offline turns are NEVER charged (no ``ai_billable_usage`` rows), but per-turn
  ops telemetry (``ai_ops_event``) still lands.
- Refused turns record a ``refused`` ops event and no usage-log rows.
- Ops events never carry prompt text (metadata-only columns by construction).
"""

from __future__ import annotations

import uuid

from app.ai.observability.models import AiBillableUsage, AiOpsEvent, AiUsageLog
from app.modules.ai_assistant.application import chat_service, turn_telemetry
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import register_verified
from tests.messaging_utils import make_partner


async def _student(db_session) -> Principal:
    user = await register_verified(
        db_session, email=f"acct_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    return Principal(user_id=user.id, persona="student", permissions=frozenset())


async def _count(db_session, model, *where) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(model).where(*where))
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Billable idempotency                                                         #
# --------------------------------------------------------------------------- #


async def test_record_turn_billable_is_idempotent_per_assistant_message(db_session) -> None:
    _user, org, principal = await make_partner(db_session)
    assistant_msg_id = uuid.uuid4()
    session_id = uuid.uuid4()

    await turn_telemetry.record_turn_billable(
        db_session,
        principal=principal,
        assistant_message_id=assistant_msg_id,
        session_id=session_id,
        provider_cost_usd=0.0005,
    )
    # Client retry / stream replay — must NOT double-charge.
    await turn_telemetry.record_turn_billable(
        db_session,
        principal=principal,
        assistant_message_id=assistant_msg_id,
        session_id=session_id,
        provider_cost_usd=0.0005,
    )
    await db_session.commit()

    rows = (
        (await db_session.execute(select(AiBillableUsage))).scalars().all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_persona == "partner"
    assert row.billing_scope == "org"  # org attribution for partner turns
    assert row.org_id == org.id
    assert row.units_charged == 1
    assert row.task_type == "ai_assistant_chat"
    assert row.idempotency_key == f"chatbot:{assistant_msg_id}"


async def test_student_turn_billable_lands_on_user_scope(db_session) -> None:
    principal = await _student(db_session)
    msg_id = uuid.uuid4()

    await turn_telemetry.record_turn_billable(
        db_session,
        principal=principal,
        assistant_message_id=msg_id,
        session_id=uuid.uuid4(),
    )
    await db_session.commit()

    row = (await db_session.execute(select(AiBillableUsage))).scalars().one()
    assert row.actor_persona == "student"
    assert row.billing_scope == "user"
    assert row.actor_user_id == principal.user_id


# --------------------------------------------------------------------------- #
# Offline turns: telemetry yes, charge no                                      #
# --------------------------------------------------------------------------- #


async def test_offline_partner_turn_records_ops_event_but_no_charge(db_session) -> None:
    _user, _org, principal = await make_partner(db_session)
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tóm tắt pipeline ứng viên của chúng tôi tuần này",
    )
    assert reply["role"] == "assistant"

    # Offline provider → never billed.
    assert await _count(db_session, AiBillableUsage) == 0
    # But the turn is observed (ops event with the chat task type).
    ops = (
        (
            await db_session.execute(
                select(AiOpsEvent).where(AiOpsEvent.task_type == "ai_assistant_chat")
            )
        )
        .scalars()
        .all()
    )
    assert ops, "per-turn ops telemetry must land even offline"
    assert all(e.user_id == principal.user_id for e in ops)


async def test_refused_turn_records_refused_ops_event_and_no_usage(db_session) -> None:
    _user, _org, principal = await make_partner(db_session)
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tìm ứng viên trên LinkedIn giúp tôi",
    )

    assert await _count(db_session, AiUsageLog) == 0  # no model call, no quota use
    assert await _count(db_session, AiBillableUsage) == 0  # no charge
    refused = (
        (
            await db_session.execute(
                select(AiOpsEvent).where(
                    AiOpsEvent.task_type == "ai_assistant_chat",
                    AiOpsEvent.status == "refused",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(refused) == 1


async def test_fast_path_turn_is_never_charged(db_session) -> None:
    principal = await _student(db_session)
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )

    assert await _count(db_session, AiBillableUsage) == 0


async def test_telemetry_never_raises_without_db(db_session) -> None:
    principal = await _student(db_session)
    # Passing db=None must be a harmless no-op (log line only).
    await turn_telemetry.record_chat_turn(
        None,
        principal=principal,
        session_id=None,
        alias="chat_default",
        status="ok",
        latency_ms=10,
        iterations=1,
        tool_names=["search_jobs"],
        guard_flags=[],
    )
    await turn_telemetry.record_turn_billable(
        None,
        principal=principal,
        assistant_message_id=uuid.uuid4(),
        session_id=None,
    )
