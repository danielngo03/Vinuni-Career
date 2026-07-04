from __future__ import annotations

import uuid

from app.core.db import get_sessionmaker
from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.agentic.planner import build_agent_plan
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import register_verified


async def test_chat_session_is_committed_before_followup_request(db_session) -> None:
    user = await register_verified(db_session, email=f"chat_{uuid.uuid4().hex[:8]}@vinuni.edu.vn")
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())

    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as second_request:
        persisted = (
            await second_request.execute(select(ChatSession).where(ChatSession.id == session_id))
        ).scalar_one_or_none()
        assert persisted is not None

        reply = await chat_service.send_message(
            second_request,
            principal=principal,
            session_id=session_id,
            text="Gợi ý giúp tôi vài việc thực tập phù hợp.",
        )

    assert reply["role"] == "assistant"
    assert reply["content"]


async def test_chat_greeting_fast_path_is_clean_and_persisted(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_greeting_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Xin chào",
    )

    assert reply["role"] == "assistant"
    assert "Xin chào" in reply["content"]
    assert "[hệ thống AI]" not in reply["content"]

    events = [
        event
        async for event in chat_service.stream_message(
            db_session,
            principal=principal,
            session_id=session_id,
            text="hi",
        )
    ]

    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["role"] == "assistant"
    assert any(event["type"] == "status" for event in events)
    assert any(event["type"] == "token" for event in events)


async def test_chat_refuses_out_of_scope_math_and_code_analysis(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_scope_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    math_reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="1 + 1 bằng mấy?",
    )
    code_reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Hãy phân tích đoạn code này cho tôi # Run State — Batch 2",
    )

    assert "chỉ hỗ trợ" in math_reply["content"]
    assert "1 + 1 bằng 2" not in math_reply["content"]
    assert "chỉ hỗ trợ" in code_reply["content"]
    assert "Batch 2" not in code_reply["content"]


async def test_chat_allows_platform_support_questions(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_support_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    theme_reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tôi muốn thay đổi theme hệ thống",
    )
    account_reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tài khoản của tôi bị lỗi đăng nhập thì làm sao?",
    )

    assert "Cài đặt" in theme_reply["content"]
    assert "Giao diện" in theme_reply["content"]
    assert "chỉ hỗ trợ" not in theme_reply["content"]
    assert "Quên mật khẩu" in account_reply["content"]


async def test_chat_allows_contact_admin_as_platform_support(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_admin_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tôi muốn chat với admin",
    )

    assert "Tin nhắn" in reply["content"] or "Trợ giúp" in reply["content"]
    assert "chỉ hỗ trợ" not in reply["content"]


async def test_agent_planner_routes_known_company_lookup(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_company_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "FPT là ai",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "search_companies"
    assert plan.tool_args == {"q": "FPT"}


async def test_agent_planner_routes_cv_apply_questions_to_recommendations(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_cv_apply_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    cv_plan = await build_agent_plan(
        "Hiện tại CV của tôi nên apply JD nào",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    apply_plan = await build_agent_plan(
        "Tôi muốn apply vào các vị trí",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert cv_plan is not None
    assert cv_plan.tool_name == "recommend_jobs"
    assert apply_plan is not None
    assert apply_plan.tool_name == "recommend_jobs"


async def test_agent_planner_routes_application_status_and_next_steps(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_status_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    status_plan = await build_agent_plan(
        "Đơn ứng tuyển của tôi sao rồi?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    next_step_plan = await build_agent_plan(
        "Tôi nên làm gì tiếp theo?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert status_plan is not None
    assert status_plan.tool_name == "get_my_applications"
    assert next_step_plan is not None
    assert next_step_plan.tool_name == "get_profile_status"


async def test_agent_planner_routes_job_discovery_without_find_keyword(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_job_discovery_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Có vị trí thực tập backend ở Hà Nội không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "search_jobs"
    assert plan.tool_args is not None
    assert plan.tool_args["province_code"] == "HN"
    assert "backend" in plan.tool_args["q"].lower()


async def test_agent_planner_routes_platform_policy_questions_to_kb(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_policy_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Sinh viên VinUni có bao nhiêu token AI và nâng gói như thế nào?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "knowledge_base_query"
    assert plan.tool_args is not None
    assert "token AI" in plan.tool_args["query"]


async def test_chat_cv_review_intent_gives_job_specific_next_step(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_cv_review_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Check CV của tôi đi",
    )

    assert "JD/job cụ thể" in reply["content"] or "so CV" in reply["content"]
    assert "chỉ hỗ trợ" not in reply["content"]


async def test_chat_salary_intent_uses_tool_without_leaking_tool_json(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_salary_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    events = [
        event
        async for event in chat_service.stream_message(
            db_session,
            principal=principal,
            session_id=session_id,
            text="Mức lương IT bao nhiêu?",
        )
    ]

    final = events[-1]["message"]["content"]
    assert events[-1]["type"] == "done"
    assert any(
        event.get("type") == "tool_call" and event.get("name") == "get_salary_benchmark"
        for event in events
    )
    assert "Benchmark lương" in final
    assert "tool_call" not in final
    assert "job_title" not in final


async def test_chat_agent_router_persists_hidden_tool_results(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_agent_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Cho tôi xem các CV của tôi",
    )

    assert reply["role"] == "assistant"
    assert "CV" in reply["content"]

    hidden_tool_result = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "tool_result",
                ChatMessage.tool_name == "get_my_cvs",
            )
        )
    ).scalar_one_or_none()
    assert hidden_tool_result is not None

    visible_messages = await chat_service.get_session_messages(
        db_session,
        principal=principal,
        session_id=session_id,
    )
    assert all(message["role"] != "tool_result" for message in visible_messages)


async def test_agent_planner_resolves_recent_job_reference_from_tool_memory(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_memory_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()
    first_job_id = uuid.uuid4()
    second_job_id = uuid.uuid4()
    db_session.add(
        ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role="tool_result",
            content="hidden jobs",
            tool_name="search_jobs",
            tool_args={"q": "data"},
            tool_result={
                "ok": True,
                "jobs": [
                    {
                        "id": str(first_job_id),
                        "title": "Data Intern",
                        "company": "VinAI",
                        "url": f"/jobs/{first_job_id}",
                    },
                    {
                        "id": str(second_job_id),
                        "title": "Backend Intern",
                        "company": "FPT Software",
                        "url": f"/jobs/{second_job_id}",
                    },
                ],
            },
        )
    )
    await db_session.flush()

    plan = await build_agent_plan(
        "So CV của tôi với job thứ 2",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "get_skill_gap"
    assert plan.tool_args == {"job_id": str(second_job_id)}


async def test_recent_job_mutation_becomes_confirmation_tool_call(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_confirm_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    job_id = uuid.uuid4()
    db_session.add(
        ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role="tool_result",
            content="hidden jobs",
            tool_name="search_jobs",
            tool_args={"q": "backend"},
            tool_result={
                "ok": True,
                "jobs": [
                    {
                        "id": str(job_id),
                        "title": "Backend Intern",
                        "company": "FPT Software",
                        "url": f"/jobs/{job_id}",
                    }
                ],
            },
        )
    )
    await db_session.flush()

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Lưu job đó giúp tôi",
    )

    assert reply["role"] == "tool_call"
    assert reply["tool_name"] == "save_job"
    assert reply["tool_args"] == {"job_id": str(job_id)}
    assert reply["requires_confirmation"] is True
