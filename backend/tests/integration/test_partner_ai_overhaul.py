"""Partner AI overhaul — chat org-scope, energy metering, and analytics tool.

Covers the three backend contracts added for the partner assistant overhaul:

1. ``ChatSession.org_id`` is captured at session creation for a partner
   (recruiter) and stays NULL for a student (additive, no behaviour change).
2. A completed chatbot turn debits the durable energy ledger exactly ONCE per
   user message — org-attributed for a partner, idempotent on the user message
   id, and never charged for fast-path/greeting turns.
3. ``get_partner_analytics_summary`` returns org-scoped hiring aggregates and is
   dispatch-gated on the ``analytics:view_job_metrics`` capability (rejected for
   a partner without it and for a student).
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.energy.service import charge_units
from app.ai.observability.billable_usage import FEATURE_CHATBOT, SCOPE_ORG
from app.ai.observability.models import AiBillableUsage
from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.agentic.planner import build_agent_plan
from app.modules.ai_assistant.application.response_formatter import fast_path_reply
from app.modules.ai_assistant.application.tools import partner as partner_tools
from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool
from app.modules.ai_assistant.domain.models import ChatSession
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, apply_service
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _count_chatbot_rows(db, *, org_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(AiBillableUsage)
                .where(
                    AiBillableUsage.feature_key == FEATURE_CHATBOT,
                    AiBillableUsage.org_id == org_id,
                )
            )
        ).scalar_one()
    )


# --------------------------------------------------------------------------- #
# Task 1 — ChatSession.org_id                                                  #
# --------------------------------------------------------------------------- #


async def test_partner_chat_session_stores_org_id(db_session) -> None:
    _user, porg, partner = await make_org_with_admin(db_session, display_name="Chat Co")

    created = await chat_service.create_session(db_session, principal=partner)

    chat = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"]))
        )
    ).scalar_one()
    assert chat.org_id == porg.id
    assert chat.user_id == partner.user_id


async def test_student_chat_session_has_null_org_id(db_session) -> None:
    _su, student = await make_student(db_session)

    created = await chat_service.create_session(db_session, principal=student)

    chat = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"]))
        )
    ).scalar_one()
    assert chat.org_id is None


# --------------------------------------------------------------------------- #
# Task 2 — energy metering of a completed chat turn                            #
# --------------------------------------------------------------------------- #


async def test_charge_chatbot_turn_is_org_attributed_and_idempotent(db_session) -> None:
    _user, porg, partner = await make_org_with_admin(db_session, display_name="Meter Co")
    chat_id = uuid.uuid4()
    user_msg_id = uuid.uuid4()

    # First charge, then a retry of the SAME turn (same idempotency key = user
    # message id, matching how send_message/stream_message namespace the ledger).
    await chat_service._charge_chatbot_turn(
        db_session, principal=partner, chat_id=chat_id, idempotency_key=user_msg_id
    )
    await chat_service._charge_chatbot_turn(
        db_session, principal=partner, chat_id=chat_id, idempotency_key=user_msg_id
    )

    rows = (
        await db_session.execute(
            select(AiBillableUsage).where(
                AiBillableUsage.feature_key == FEATURE_CHATBOT,
                AiBillableUsage.org_id == porg.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1  # idempotent: retry did not double-charge
    row = rows[0]
    assert row.billing_scope == SCOPE_ORG
    assert row.actor_persona == "partner"
    assert row.actor_user_id == partner.user_id
    assert row.units_charged == charge_units(FEATURE_CHATBOT) > 0
    assert row.result_status == "success"


async def test_completed_partner_chat_turn_charges_exactly_one_credit(db_session) -> None:
    _user, porg, partner = await make_org_with_admin(db_session, display_name="Turn Co")

    created = await chat_service.create_session(db_session, principal=partner)
    session_id = uuid.UUID(created["id"])

    # A greeting is answered on the deterministic fast-path (no LLM call) and
    # must NOT be charged.
    greeting = await chat_service.send_message(
        db_session, principal=partner, session_id=session_id, text="Xin chào"
    )
    assert greeting["role"] == "assistant"
    assert await _count_chatbot_rows(db_session, org_id=porg.id) == 0

    # A general question that reaches the LLM tool-calling loop. Guard the test:
    # if a future planner captures it deterministically, these asserts fail
    # loudly instead of silently recording zero charges.
    text = "Công ty tôi nên chuẩn bị gì để mùa tuyển dụng sắp tới hiệu quả hơn?"
    assert fast_path_reply(text) is None
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()
    assert await build_agent_plan(text, principal=partner, session=db_session, chat=chat) is None

    reply = await chat_service.send_message(
        db_session, principal=partner, session_id=session_id, text=text
    )
    assert reply["role"] == "assistant"

    rows = (
        await db_session.execute(
            select(AiBillableUsage).where(
                AiBillableUsage.feature_key == FEATURE_CHATBOT,
                AiBillableUsage.org_id == porg.id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1  # exactly one charge for the completed turn
    assert rows[0].billing_scope == SCOPE_ORG
    assert rows[0].units_charged == charge_units(FEATURE_CHATBOT)


# --------------------------------------------------------------------------- #
# Task 3 — get_partner_analytics_summary tool                                  #
# --------------------------------------------------------------------------- #


async def _org_with_two_applications(db):
    _pu, porg, partner = await make_org_with_admin(db, display_name="Analytics Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title="Data Intern"
    )

    for _ in range(2):
        _su, student = await make_student(db)
        sel = await make_builder_cv(db, student=student)
        await apply_service.apply_to_job(
            db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
        )
    return porg, partner, job_id


async def test_get_partner_analytics_summary_returns_org_scoped_aggregates(db_session) -> None:
    porg, partner, job_id = await _org_with_two_applications(db_session)

    result = await partner_tools.get_partner_analytics_summary(db_session, partner)

    assert result["ok"] is True
    assert result["applications_total"] == 2
    # funnel counts sum to the org's total application volume
    assert sum(row["count"] for row in result["funnel"]) == 2
    assert all(
        isinstance(row["stage"], str) and "_" not in row["stage"] for row in result["funnel"]
    )
    # top job by application volume is the org's own job
    assert len(result["top_jobs"]) == 1
    assert result["top_jobs"][0]["application_count"] == 2
    assert str(job_id) in result["top_jobs"][0]["url"]
    assert "conversion" in result
    # no leakage of AI internals or raw candidate data
    dumped = str(result)
    for banned in ("provider", "model", "token", "prompt", "confidence", "cost"):
        assert banned not in dumped.lower()


async def test_partner_analytics_summary_is_org_isolated(db_session) -> None:
    porg, partner, _job_id = await _org_with_two_applications(db_session)
    # A different org's admin sees only their own (empty) analytics.
    _ou, _oorg, other_partner = await make_org_with_admin(db_session, display_name="Other Co")

    other = await partner_tools.get_partner_analytics_summary(db_session, other_partner)

    assert other["ok"] is True
    assert other["applications_total"] == 0
    assert other["top_jobs"] == []


async def test_dispatch_rejects_partner_without_analytics_capability(db_session) -> None:
    _user, porg, _admin = await make_org_with_admin(db_session, display_name="RBAC Co")
    # A recruiter member WITHOUT the analytics grant (only jobs:read).
    _mu, _membership, member = await add_member(
        db_session, org=porg, permissions=[("jobs", "read")]
    )

    result = await dispatch_tool(
        "get_partner_analytics_summary", {}, session=db_session, principal=member
    )
    assert result == {"ok": False, "error": "tool_not_permitted"}


async def test_dispatch_allows_partner_admin_with_wildcard(db_session) -> None:
    porg, partner, _job_id = await _org_with_two_applications(db_session)

    result = await dispatch_tool(
        "get_partner_analytics_summary", {}, session=db_session, principal=partner
    )
    assert result["ok"] is True
    assert result["applications_total"] == 2


async def test_dispatch_rejects_student_for_partner_analytics_tool(db_session) -> None:
    _su, student = await make_student(db_session)

    result = await dispatch_tool(
        "get_partner_analytics_summary", {}, session=db_session, principal=student
    )
    assert result == {"ok": False, "error": "tool_not_permitted"}


def test_student_principal_cannot_reach_partner_analytics_gate() -> None:
    """Persona gate rejects a student even before the capability check."""
    from app.modules.ai_assistant.application.tools.dispatch import _tool_not_permitted
    from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS

    student = Principal(user_id=uuid.uuid4(), persona="student", permissions=frozenset())
    assert _tool_not_permitted(student, TOOL_SPECS["get_partner_analytics_summary"]) is True
