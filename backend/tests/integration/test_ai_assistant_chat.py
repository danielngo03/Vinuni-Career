from __future__ import annotations

import uuid

from app.ai.prompts.assistant import v1 as assistant_prompt
from app.core.db import get_sessionmaker
from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.agentic.planner import build_agent_plan
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import register_verified


def test_student_assistant_prompt_is_student_first() -> None:
    prompt = assistant_prompt.SYSTEM_PROMPT.lower()

    assert "student career copilot" in prompt
    assert "partner recruiters" not in prompt
    assert "partner recruiting workflows" not in prompt


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


async def test_agent_planner_routes_bare_and_typo_apply_to_recommendations(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_bare_apply_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    bare_plan = await build_agent_plan(
        "tôi muốn apply",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    typo_plan = await build_agent_plan(
        "Sửa như này hay appyly vị trí nào",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert bare_plan is not None
    assert bare_plan.tool_name == "recommend_jobs"
    assert typo_plan is not None
    assert typo_plan.tool_name == "recommend_jobs"


async def test_chat_routes_cv_count_question_to_cv_library_not_salary(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_cv_count_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="CV của tôi đang có bao nhiêu",
    )

    assert "CV" in reply["content"]
    assert "Salary data" not in reply["content"]
    assert "mức lương" not in reply["content"].lower()
    assert "chỉ hỗ trợ" not in reply["content"]


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


async def test_agent_planner_refuses_external_job_search_without_tool(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_external_jobs_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Tìm job data analyst trên Linkedln ở Hà Nội",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.action == "reply"
    assert plan.tool_name is None
    assert plan.reply is not None
    assert "không tìm được trên LinkedIn" in plan.reply
    assert "VinUni Career Platform" in plan.reply


async def test_agent_planner_explains_capabilities_and_data_boundary(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_capability_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    capability = await build_agent_plan(
        "Chatbot này hỗ trợ gì cho tôi?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    boundary = await build_agent_plan(
        "Bạn có dùng internet hoặc LinkedIn để tra cứu không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert capability is not None
    assert capability.action == "reply"
    assert "student/người tìm việc" in (capability.reply or "")
    assert "Google" in (capability.reply or "")
    assert boundary is not None
    assert boundary.action == "reply"
    assert "không browse internet" in (boundary.reply or "")
    assert "VinUni Career Platform" in (boundary.reply or "")


async def test_agent_planner_does_not_treat_online_event_or_google_company_as_external(
    db_session,
) -> None:
    user = await register_verified(
        db_session, email=f"chat_external_precision_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    event_plan = await build_agent_plan(
        "Tìm sự kiện online về career fair",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    company_plan = await build_agent_plan(
        "Google là công ty gì?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert event_plan is not None
    assert event_plan.tool_name == "search_events"
    assert company_plan is not None
    assert company_plan.tool_name == "search_companies"
    assert company_plan.tool_args == {"q": "Google"}


async def test_agent_planner_allows_linkedin_profile_coaching_without_external_lookup(
    db_session,
) -> None:
    user = await register_verified(
        db_session, email=f"chat_linkedin_profile_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "LinkedIn/GitHub trong CV nên trình bày thế nào?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.action == "reply"
    assert "Portfolio/GitHub/LinkedIn" in (plan.reply or "")


async def test_agent_planner_refuses_external_company_news_without_tool(
    db_session,
) -> None:
    user = await register_verified(
        db_session, email=f"chat_external_company_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Có tin tức mới nhất trên Google về FPT không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.action == "reply"
    assert plan.tool_name is None
    assert plan.reply is not None
    assert "không tìm được trên Google" in plan.reply
    assert "VinUni Career Platform" in plan.reply


async def test_chat_external_search_does_not_dispatch_hidden_tool(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_external_no_tool_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])

    reply = await chat_service.send_message(
        db_session,
        principal=principal,
        session_id=session_id,
        text="Tìm job qua Google giúp tôi",
    )

    hidden_tool_result = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "tool_result",
            )
        )
    ).scalar_one_or_none()
    assert reply["role"] == "assistant"
    assert "không tìm được trên Google" in reply["content"]
    assert "VinUni Career Platform" in reply["content"]
    assert hidden_tool_result is None


async def test_agent_planner_handles_student_career_playbooks(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_playbooks_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    cover_letter = await build_agent_plan(
        "Viết cover letter như thế nào cho internship?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    portfolio = await build_agent_plan(
        "Portfolio/GitHub của tôi nên trình bày ra sao?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    rejection = await build_agent_plan(
        "Tôi vừa bị reject, giờ nên làm gì?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    first_job = await build_agent_plan(
        "Tôi chưa có kinh nghiệm thì tìm việc đầu tiên kiểu gì?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert cover_letter is not None and cover_letter.action == "reply"
    assert "thư ứng tuyển" in (cover_letter.reply or "")
    assert portfolio is not None and portfolio.action == "reply"
    assert "GitHub" in (portfolio.reply or "")
    assert rejection is not None and rejection.action == "reply"
    assert "từ chối" in (rejection.reply or "")
    assert first_job is not None and first_job.action == "reply"
    assert "internship/fresher" in (first_job.reply or "")


async def test_agent_planner_routes_vague_direction_to_profile_context(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_direction_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Tôi chưa biết ngành nào phù hợp với tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "get_profile_status"
    assert plan.reason is not None


async def test_agent_planner_handles_real_student_operations_without_unsafe_tooling(
    db_session,
) -> None:
    user = await register_verified(
        db_session, email=f"chat_student_ops_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    start_plan = await build_agent_plan(
        "Tôi muốn tìm việc nhưng chưa biết bắt đầu như thế nào",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    withdraw_plan = await build_agent_plan(
        "Tôi muốn rút đơn ứng tuyển",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    cv_plan = await build_agent_plan(
        "Làm sao để upload CV?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    scam_plan = await build_agent_plan(
        "Job này bắt tôi chuyển khoản phí ứng tuyển có lừa đảo không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert start_plan is not None
    assert start_plan.tool_name == "get_profile_status"
    assert withdraw_plan is not None
    assert withdraw_plan.action == "reply"
    assert "chưa thể rút/hủy đơn trực tiếp qua chat" in (withdraw_plan.reply or "")
    assert cv_plan is not None
    assert cv_plan.action == "reply"
    assert "CV Studio" in (cv_plan.reply or "")
    assert scam_plan is not None
    assert scam_plan.action == "reply"
    assert "báo cáo" in (scam_plan.reply or "")


async def test_agent_planner_separates_cv_management_from_cv_improvement(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_cv_management_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    edit_plan = await build_agent_plan(
        "Sửa CV của tôi giúp tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    delete_plan = await build_agent_plan(
        "Xóa CV cũ của tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    improve_plan = await build_agent_plan(
        "CV của tôi cần cải thiện gì?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert edit_plan is not None
    assert edit_plan.action == "reply"
    assert "không sửa trực tiếp" in (edit_plan.reply or "")
    assert "CV Studio" in (edit_plan.reply or "")
    assert delete_plan is not None
    assert delete_plan.action == "reply"
    assert "chưa xóa CV trực tiếp" in (delete_plan.reply or "")
    assert improve_plan is not None
    assert improve_plan.tool_name == "get_my_cvs"
    assert improve_plan.reason is not None


async def test_agent_planner_handles_saved_job_action_boundaries(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_saved_boundaries_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    list_plan = await build_agent_plan(
        "Cho tôi xem việc đã lưu",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    save_without_selection = await build_agent_plan(
        "Lưu job này giúp tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    unsave_plan = await build_agent_plan(
        "Bỏ lưu job này",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert list_plan is not None
    assert list_plan.tool_name == "get_saved_jobs"
    assert save_without_selection is not None
    assert save_without_selection.action == "reply"
    assert "xác định đúng tin tuyển dụng" in (save_without_selection.reply or "")
    assert unsave_plan is not None
    assert unsave_plan.action == "reply"
    assert "chưa bỏ lưu" in (unsave_plan.reply or "")


async def test_agent_planner_handles_unsupported_student_actions(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_action_boundaries_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    event_register = await build_agent_plan(
        "Đăng ký event career fair này cho tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    event_registered = await build_agent_plan(
        "Tôi đã đăng ký sự kiện nào?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    interview_action = await build_agent_plan(
        "Đổi lịch phỏng vấn giúp tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    alert_action = await build_agent_plan(
        "Tạo job alert cho data analyst",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    offer_action = await build_agent_plan(
        "Chấp nhận offer này giúp tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    application_edit = await build_agent_plan(
        "Sửa đơn ứng tuyển của tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert event_register is not None
    assert event_register.action == "reply"
    assert "chưa đăng ký sự kiện trực tiếp" in (event_register.reply or "")
    assert event_registered is not None
    assert event_registered.tool_name == "get_my_registered_events"
    assert interview_action is not None
    assert interview_action.action == "reply"
    assert "chưa xác nhận, hủy hoặc đổi lịch" in (interview_action.reply or "")
    assert alert_action is not None
    assert alert_action.action == "reply"
    assert "chưa tạo/bật job alert" in (alert_action.reply or "")
    assert offer_action is not None
    assert offer_action.action == "reply"
    assert "chưa chấp nhận" in (offer_action.reply or "")
    assert application_edit is not None
    assert application_edit.action == "reply"
    assert "chưa chỉnh sửa đơn ứng tuyển" in (application_edit.reply or "")


async def test_agent_planner_searches_role_requests_without_job_keyword(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_role_search_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Có remote data analyst ở Hà Nội không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "search_jobs"
    assert plan.tool_args is not None
    assert plan.tool_args["province_code"] == "HN"
    assert "data analyst" in plan.tool_args["q"].lower()


async def test_agent_planner_clarifies_domain_related_unknown_requests(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_domain_clarify_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()

    plan = await build_agent_plan(
        "Career của tôi đang hơi rối",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.action == "reply"
    assert "cần bạn nói rõ hơn" in (plan.reply or "")


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


async def test_agent_planner_resolves_job_and_cv_references_together(db_session) -> None:
    user = await register_verified(
        db_session, email=f"chat_job_cv_refs_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    session_id = uuid.UUID(created["id"])
    chat = (
        await db_session.execute(select(ChatSession).where(ChatSession.id == session_id))
    ).scalar_one()
    first_cv_id = uuid.uuid4()
    second_job_id = uuid.uuid4()
    db_session.add_all(
        [
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                role="tool_result",
                content="hidden cvs",
                tool_name="get_my_cvs",
                tool_args={},
                tool_result={
                    "ok": True,
                    "cvs": [
                        {
                            "id": str(first_cv_id),
                            "title": "Backend CV",
                            "status": "draft",
                        }
                    ],
                },
            ),
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                role="tool_result",
                content="hidden jobs",
                tool_name="recommend_jobs",
                tool_args={"limit": 5},
                tool_result={
                    "ok": True,
                    "recommendations": [
                        {
                            "id": str(uuid.uuid4()),
                            "title": "Data Intern",
                            "company": "VinAI",
                            "url": "/jobs/data",
                        },
                        {
                            "id": str(second_job_id),
                            "title": "Backend Intern",
                            "company": "FPT Software",
                            "url": f"/jobs/{second_job_id}",
                        },
                    ],
                },
            ),
        ]
    )
    await db_session.flush()

    skill_gap = await build_agent_plan(
        "So CV thứ 1 với job thứ 2",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    apply_plan = await build_agent_plan(
        "Apply job thứ 2 bằng CV thứ 1",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert skill_gap is not None
    assert skill_gap.tool_name == "get_skill_gap"
    assert skill_gap.tool_args == {"job_id": str(second_job_id), "cv_id": str(first_cv_id)}
    assert apply_plan is not None
    assert apply_plan.tool_name == "apply_job"
    assert apply_plan.tool_args == {"job_id": str(second_job_id), "cv_id": str(first_cv_id)}


# --------------------------------------------------------------------------- #
# Partner (recruiter) routing + dispatch RBAC (P3a)                            #
# --------------------------------------------------------------------------- #


async def _partner_chat(db_session) -> tuple[Principal, ChatSession]:
    """Create a real user + chat session and return a partner-persona principal."""
    user = await register_verified(
        db_session, email=f"partner_chat_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(
        user_id=user.id,
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(),
    )
    created = await chat_service.create_session(db_session, principal=principal)
    chat = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"]))
        )
    ).scalar_one()
    return principal, chat


async def test_partner_open_question_falls_through_to_llm_loop(db_session) -> None:
    # An open-ended recruiter task (draft a JD) is NOT a deterministic partner
    # intent, so the partner planner returns None and the message reaches the
    # LLM tool-calling loop (partner prompt + partner tools).
    principal, chat = await _partner_chat(db_session)

    plan = await build_agent_plan(
        "Viết cho tôi một JD cho vị trí backend engineer",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is None


async def test_partner_pipeline_summary_still_routes_deterministically(db_session) -> None:
    principal, chat = await _partner_chat(db_session)

    plan = await build_agent_plan(
        "Cho tôi xem pipeline ứng viên hiện tại",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.action == "tool"
    assert plan.tool_name == "get_partner_pipeline_summary"


async def test_partner_capability_and_data_boundary_use_partner_copy(db_session) -> None:
    principal, chat = await _partner_chat(db_session)

    capability = await build_agent_plan(
        "Bạn làm được gì cho tôi?",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    boundary = await build_agent_plan(
        "Bạn có tra cứu ứng viên trên LinkedIn không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert capability is not None
    assert capability.action == "reply"
    # Partner-scoped capability copy, not the student ("người tìm việc") copy.
    assert "vận hành tuyển dụng" in (capability.reply or "")
    assert boundary is not None
    assert boundary.action == "reply"
    assert "tổ chức bạn" in (boundary.reply or "")


async def test_partner_does_not_route_to_student_tools(db_session) -> None:
    # Phrases that would trigger STUDENT tools (recommend_jobs / get_my_cvs)
    # must NOT produce a student plan for a partner — they fall through to the
    # LLM loop instead of mis-routing onto student tooling.
    principal, chat = await _partner_chat(db_session)

    recommend = await build_agent_plan(
        "Gợi ý vài việc phù hợp với tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )
    my_cvs = await build_agent_plan(
        "Cho tôi xem CV của tôi",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert recommend is None
    assert my_cvs is None


async def test_student_planner_unchanged_by_partner_routing(db_session) -> None:
    # Regression guard: the student deterministic planner still routes a job
    # discovery request to search_jobs exactly as before.
    user = await register_verified(
        db_session, email=f"chat_student_regress_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    principal = Principal(user_id=user.id, persona="student", permissions=frozenset())
    created = await chat_service.create_session(db_session, principal=principal)
    chat = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"]))
        )
    ).scalar_one()

    plan = await build_agent_plan(
        "Có việc thực tập backend nào đang mở không?",
        principal=principal,
        session=db_session,
        chat=chat,
    )

    assert plan is not None
    assert plan.tool_name == "search_jobs"


async def test_dispatch_rejects_student_tool_for_partner_principal(db_session) -> None:
    from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool

    user = await register_verified(
        db_session, email=f"partner_dispatch_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    partner = Principal(
        user_id=user.id,
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(),
    )

    result = await dispatch_tool(
        "apply_job",
        {"job_id": str(uuid.uuid4())},
        session=db_session,
        principal=partner,
    )

    # Rejected at the persona gate BEFORE arg validation or execution.
    assert result == {"ok": False, "error": "tool_not_permitted"}


async def test_dispatch_rejects_partner_tool_for_student_principal(db_session) -> None:
    from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool

    user = await register_verified(
        db_session, email=f"student_dispatch_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    student = Principal(user_id=user.id, persona="student", permissions=frozenset())

    result = await dispatch_tool(
        "get_partner_pipeline_summary",
        {},
        session=db_session,
        principal=student,
    )

    assert result == {"ok": False, "error": "tool_not_permitted"}
