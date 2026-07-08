"""Student chatbot debits AI energy per model-generated turn.

FINDING: the chatbot already ENFORCES energy (``usage_service.enforce_quota`` ->
``enforce_energy`` at ``send_message``/``stream_message``) but did NOT CHARGE it —
model turns spent 0 energy. These tests cover the wired charge: a model-generated
turn charges one chatbot credit to the student's user scope, keyed idempotently on
the assistant message id; deterministic fast-path / quick replies charge nothing.
"""

from __future__ import annotations

import uuid

from app.ai.energy.service import charge_units
from app.ai.observability.models import AiBillableUsage
from app.modules.ai_assistant.application import chat_service, usage_service
from sqlalchemy import func, select
from tests.documents_utils import make_student


async def _user_units(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _count(db, user_id) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AiBillableUsage).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# The charge seam directly: success + idempotency                              #
# --------------------------------------------------------------------------- #


async def test_charge_chat_turn_charges_student_once(db_session) -> None:
    _u, student = await make_student(db_session)
    msg_id = uuid.uuid4()

    await usage_service.charge_chat_turn(
        db_session, principal=student, message_id=msg_id, session_id=uuid.uuid4()
    )
    await db_session.commit()

    assert await _user_units(db_session, student.user_id) == charge_units("chatbot")
    row = (
        await db_session.execute(
            select(AiBillableUsage).where(AiBillableUsage.actor_user_id == student.user_id)
        )
    ).scalar_one()
    assert row.feature_key == "chatbot"
    assert row.billing_scope == "user"
    assert row.result_status == "success"


async def test_charge_chat_turn_is_idempotent(db_session) -> None:
    _u, student = await make_student(db_session)
    msg_id = uuid.uuid4()

    await usage_service.charge_chat_turn(db_session, principal=student, message_id=msg_id)
    await usage_service.charge_chat_turn(db_session, principal=student, message_id=msg_id)
    await db_session.commit()

    # Same assistant message id -> charged exactly once.
    assert await _count(db_session, student.user_id) == 1
    assert await _user_units(db_session, student.user_id) == charge_units("chatbot")


# --------------------------------------------------------------------------- #
# End-to-end send_message: model turn charges, fast-path does not              #
# --------------------------------------------------------------------------- #


async def test_send_message_model_turn_charges(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    # Force the LLM tool loop: skip the deterministic fast-path + agent planner so
    # the offline provider actually produces the reply.
    monkeypatch.setattr(chat_service, "fast_path_reply", lambda *a, **k: None)

    async def _no_plan(*a, **k):
        return None

    monkeypatch.setattr(chat_service, "build_agent_plan", _no_plan)

    sess = await chat_service.create_session(db_session, principal=student)
    await chat_service.send_message(
        db_session, principal=student, session_id=uuid.UUID(sess["id"]),
        text="Please give me detailed advice to strengthen my CV writing style.",
    )

    assert await _user_units(db_session, student.user_id) == charge_units("chatbot")


async def test_send_message_fast_path_does_not_charge(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    # Force the deterministic fast-path (no model call).
    monkeypatch.setattr(chat_service, "fast_path_reply", lambda *a, **k: "Hi there!")

    sess = await chat_service.create_session(db_session, principal=student)
    await chat_service.send_message(
        db_session, principal=student, session_id=uuid.UUID(sess["id"]), text="hello",
    )

    assert await _user_units(db_session, student.user_id) == 0


async def test_send_message_enforces_energy_when_exhausted(db_session, monkeypatch) -> None:
    """The pre-existing enforce gate still fires (regression guard)."""
    from app.shared.exceptions import QuotaExceededError

    _u, student = await make_student(db_session)
    sess = await chat_service.create_session(db_session, principal=student)

    async def _blocked(session, *, principal):
        raise QuotaExceededError("out of energy")

    monkeypatch.setattr(usage_service.energy_service, "enforce_energy", _blocked)

    raised = False
    try:
        await chat_service.send_message(
            db_session, principal=student, session_id=uuid.UUID(sess["id"]),
            text="anything at all",
        )
    except QuotaExceededError:
        raised = True
    assert raised
    assert await _user_units(db_session, student.user_id) == 0
