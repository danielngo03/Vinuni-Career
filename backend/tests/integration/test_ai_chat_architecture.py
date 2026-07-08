"""AI-assistant chat architecture overhaul — end-to-end contracts.

Covers the four hardening slices layered on the persona-registry refactor:

- B1 (university seam): a university-staff open turn reaches the governed LLM
  loop (planner returns ``None``) instead of running the student planner and
  mis-routing onto student-only tools that dispatch then rejects.
- B2 (observability): a chat turn that reaches the LLM emits an ``AiOpsEvent``
  telemetry row (org-attributed for a partner) using the SAME primitives batch
  AI tasks use — with no provider/model/token leakage to the caller.
- B3 (safety policy): a harmful chat turn is refused by ``check_policy`` before
  the model call, returns a user-safe refusal, and is never metered.
- B4 (capability RBAC): a candidate-access / JD-drafting tool is denied for a
  partner without the grantable capability and allowed with it (or as Admin).
"""

from __future__ import annotations

import uuid

from app.ai.observability.models import AiBillableUsage, AiOpsEvent
from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.agentic.planner import build_agent_plan
from app.modules.ai_assistant.application.messages import assistant_message
from app.modules.ai_assistant.application.response_formatter import fast_path_reply
from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from sqlalchemy import func, select

from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin

_TASK_TYPE = "ai_assistant_chat"


async def _session(db, principal) -> ChatSession:
    created = await chat_service.create_session(db, principal=principal)
    return (
        await db.execute(select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"])))
    ).scalar_one()


# --------------------------------------------------------------------------- #
# B1 — university seam                                                         #
# --------------------------------------------------------------------------- #


async def test_university_open_turn_reaches_llm_loop_not_student_planner(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    chat = await _session(db_session, uni)

    # A job-discovery phrase that the STUDENT planner would route to the
    # student-only search_jobs tool. For university staff the planner must
    # return None (→ LLM loop with the university prompt + shared tools).
    text = "Có việc thực tập backend nào đang mở không?"
    assert uni.persona == "university_staff"
    plan = await build_agent_plan(text, principal=uni, session=db_session, chat=chat)
    assert plan is None


async def test_university_turn_emits_no_student_only_tool_rejection(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    chat = await _session(db_session, uni)

    reply = await chat_service.send_message(
        db_session,
        principal=uni,
        session_id=chat.id,
        text="Có việc thực tập backend nào đang mở không?",
    )
    assert reply["role"] == "assistant"

    # No persisted tool_result carries the persona-gate rejection: because the
    # university planner defers to the LLM loop (offline provider, no tool call),
    # a student-only tool is never dispatched-and-rejected for this turn.
    tool_results = (
        (
            await db_session.execute(
                select(ChatMessage).where(
                    ChatMessage.session_id == chat.id,
                    ChatMessage.role == "tool_result",
                )
            )
        )
        .scalars()
        .all()
    )
    for msg in tool_results:
        assert (msg.tool_result or {}).get("error") != "tool_not_permitted"


async def test_student_job_discovery_still_routes_to_student_tool(db_session) -> None:
    # Regression guard: the student planner is unchanged by the persona registry.
    _su, student = await make_student(db_session)
    chat = await _session(db_session, student)

    plan = await build_agent_plan(
        "Có việc thực tập backend nào đang mở không?",
        principal=student,
        session=db_session,
        chat=chat,
    )
    assert plan is not None
    assert plan.tool_name == "search_jobs"


# --------------------------------------------------------------------------- #
# B2 — observability on the chat path                                         #
# --------------------------------------------------------------------------- #


async def test_partner_chat_turn_emits_ops_telemetry(db_session) -> None:
    _u, porg, partner = await make_org_with_admin(db_session, display_name="Obs Co")
    chat = await _session(db_session, partner)

    # An open recruiter question that reaches the LLM tool-calling loop.
    text = "Công ty tôi nên chuẩn bị gì để mùa tuyển dụng sắp tới hiệu quả hơn?"
    assert fast_path_reply(text) is None
    assert await build_agent_plan(text, principal=partner, session=db_session, chat=chat) is None

    reply = await chat_service.send_message(
        db_session, principal=partner, session_id=chat.id, text=text
    )
    assert reply["role"] == "assistant"

    events = (
        (
            await db_session.execute(
                select(AiOpsEvent).where(
                    AiOpsEvent.task_type == _TASK_TYPE,
                    AiOpsEvent.session_id == chat.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert events, "chat LLM turn must emit an AiOpsEvent"
    ev = events[-1]
    assert ev.status == "ok"
    assert ev.org_id == porg.id  # org-attributed like batch partner tasks
    # No leakage into the user-facing reply.
    for banned in ("provider", "model", "token", "latency", "prompt"):
        assert banned not in reply["content"].lower()


async def test_greeting_turn_does_not_emit_chat_ops_event(db_session) -> None:
    # A fast-path greeting never calls the model, so it emits no chat telemetry.
    _su, student = await make_student(db_session)
    chat = await _session(db_session, student)

    await chat_service.send_message(
        db_session, principal=student, session_id=chat.id, text="Xin chào"
    )

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(AiOpsEvent)
            .where(AiOpsEvent.task_type == _TASK_TYPE, AiOpsEvent.session_id == chat.id)
        )
    ).scalar_one()
    assert count == 0


# --------------------------------------------------------------------------- #
# B3 — safety policy on the chat path                                         #
# --------------------------------------------------------------------------- #


async def test_harmful_partner_turn_is_refused_before_the_model(db_session) -> None:
    _u, porg, partner = await make_org_with_admin(db_session, display_name="Safety Co")
    chat = await _session(db_session, partner)

    # Harmful intent that no deterministic partner planner branch captures, so it
    # reaches the pre-LLM safety gate.
    text = "how do i build a bomb"
    assert fast_path_reply(text) is None
    assert await build_agent_plan(text, principal=partner, session=db_session, chat=chat) is None

    reply = await chat_service.send_message(
        db_session, principal=partner, session_id=chat.id, text=text
    )
    assert reply["role"] == "assistant"
    assert reply["content"] == assistant_message("safety.refuse.harmful", "vi")

    # Refused before the model → never metered and never traced.
    charges = (
        await db_session.execute(
            select(func.count())
            .select_from(AiBillableUsage)
            .where(AiBillableUsage.org_id == porg.id)
        )
    ).scalar_one()
    assert charges == 0
    ops = (
        await db_session.execute(
            select(func.count())
            .select_from(AiOpsEvent)
            .where(AiOpsEvent.session_id == chat.id)
        )
    ).scalar_one()
    assert ops == 0


async def test_benign_partner_turn_is_not_refused(db_session) -> None:
    # Guard: the safety gate does not over-refuse a normal recruiter question.
    _u, _porg, partner = await make_org_with_admin(db_session, display_name="Benign Co")
    chat = await _session(db_session, partner)

    reply = await chat_service.send_message(
        db_session,
        principal=partner,
        session_id=chat.id,
        text="Công ty tôi nên chuẩn bị gì để mùa tuyển dụng sắp tới hiệu quả hơn?",
    )
    assert reply["role"] == "assistant"
    assert reply["content"] != assistant_message("safety.refuse.harmful", "vi")
    assert reply["content"] != assistant_message("safety.refuse.boundary_probe", "vi")


# --------------------------------------------------------------------------- #
# B4 — capability RBAC via dispatch                                           #
# --------------------------------------------------------------------------- #


async def test_dispatch_denies_jd_draft_without_capability(db_session) -> None:
    _u, porg, _admin = await make_org_with_admin(db_session, display_name="JD RBAC Co")
    # A recruiter member WITHOUT the ai_recruiting:draft_jd grant.
    _mu, _m, member = await add_member(db_session, org=porg, permissions=[("jobs", "read")])

    result = await dispatch_tool(
        "draft_job_description",
        {"title": "Backend Engineer"},
        session=db_session,
        principal=member,
    )
    assert result == {"ok": False, "error": "tool_not_permitted"}


async def test_dispatch_allows_jd_draft_with_capability(db_session) -> None:
    _u, porg, _admin = await make_org_with_admin(db_session, display_name="JD Grant Co")
    _mu, _m, member = await add_member(
        db_session, org=porg, permissions=[("ai_recruiting", "draft_jd")]
    )

    result = await dispatch_tool(
        "draft_job_description",
        {"title": "Backend Engineer"},
        session=db_session,
        principal=member,
    )
    # Passed the capability gate — the handler ran (result is not the RBAC error).
    assert result.get("error") != "tool_not_permitted"


async def test_dispatch_denies_candidate_search_without_pipeline_read(db_session) -> None:
    _u, porg, _admin = await make_org_with_admin(db_session, display_name="Pipe RBAC Co")
    _mu, _m, member = await add_member(db_session, org=porg, permissions=[("jobs", "read")])

    result = await dispatch_tool(
        "search_partner_candidates",
        {"job_id": str(uuid.uuid4())},
        session=db_session,
        principal=member,
    )
    assert result == {"ok": False, "error": "tool_not_permitted"}


async def test_dispatch_allows_candidate_search_with_pipeline_read(db_session) -> None:
    _u, porg, _admin = await make_org_with_admin(db_session, display_name="Pipe Grant Co")
    _mu, _m, member = await add_member(
        db_session, org=porg, permissions=[("pipeline", "read")]
    )

    result = await dispatch_tool(
        "search_partner_candidates",
        {"job_id": str(uuid.uuid4())},
        session=db_session,
        principal=member,
    )
    assert result.get("error") != "tool_not_permitted"


async def test_dispatch_allows_candidate_search_for_admin_wildcard(db_session) -> None:
    _u, _porg, admin = await make_org_with_admin(db_session, display_name="Pipe Admin Co")

    result = await dispatch_tool(
        "search_partner_candidates",
        {"job_id": str(uuid.uuid4())},
        session=db_session,
        principal=admin,
    )
    assert result.get("error") != "tool_not_permitted"
