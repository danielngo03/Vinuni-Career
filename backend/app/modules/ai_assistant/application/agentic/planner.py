"""Deterministic domain-agent planner for the AI assistant."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.application.agentic.memory import resolve_recent_entity
from app.modules.ai_assistant.application.agentic.models import AgentPlan
from app.modules.ai_assistant.domain.models import ChatSession
from app.shared.permissions import Principal

_ARITHMETIC_ONLY_RE = re.compile(
    r"^\s*\d+\s*[-+*/x×÷]\s*\d+\s*(=|bằng|is)?"
    r"\s*(mấy|gì|what)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)
_CODE_ANALYSIS_RE = re.compile(
    r"\b(phân tích|analyze|review|giải thích|explain)\b.{0,80}"
    r"\b(code|đoạn code|tsx|typescript|python|markdown|run state|run-state|batch)\b",
    re.IGNORECASE,
)
_THEME_RE = re.compile(
    r"\b(theme|appearance|giao\s*diện|dark|light|sáng|tối|màu|color)\b", re.IGNORECASE
)
_ACCOUNT_RE = re.compile(
    r"\b(tài\s*khoản|account|login|đăng\s*nhập|password|mật\s*khẩu|"
    r"security|bảo\s*mật|verify|xác\s*thực|email)\b",
    re.IGNORECASE,
)
_SETTINGS_RE = re.compile(
    r"\b(cài\s*đặt|settings|notification|thông\s*báo|language|ngôn\s*ngữ|"
    r"billing|plan|gói|quota|quyền|permission|role|vai\s*trò)\b",
    re.IGNORECASE,
)
_CONTACT_SUPPORT_RE = re.compile(
    r"\b(chat|nhắn|nói\s*chuyện|liên\s*hệ|contact|support|hỗ\s*trợ|gặp)\b"
    r".{0,30}\b(admin|cố\s*vấn|advisor|career\s*office|phòng\s*hỗ\s*trợ)\b"
    r"|\b(admin|cố\s*vấn|advisor|career\s*office|phòng\s*hỗ\s*trợ)\b"
    r".{0,30}\b(chat|nhắn|nói\s*chuyện|liên\s*hệ|contact|support|hỗ\s*trợ|gặp)\b",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"\b(lương|mức\s*lương|salary|compensation|thu\s*nhập|bao\s*nhiêu)\b", re.IGNORECASE
)
_IT_ROLE_RE = re.compile(
    r"\b(it|software|developer|dev|engineer|lập\s*trình|cntt)\b", re.IGNORECASE
)
_RECOMMEND_JOBS_RE = re.compile(
    r"\b(gợi\s*ý|phù\s*hợp|recommend|suggest).{0,40}\b(việc|job|intern|thực\s*tập)\b"
    r"|\b(việc|job|intern|thực\s*tập).{0,40}\b(phù\s*hợp|recommend|suggest)\b",
    re.IGNORECASE,
)
_NEXT_STEP_RE = re.compile(
    r"\b(tôi\s*nên\s*làm\s*gì|nên\s*làm\s*gì|bước\s*tiếp|next\s*step|"
    r"làm\s*gì\s*tiếp|hướng\s*dẫn\s*tôi)\b",
    re.IGNORECASE,
)
_SEARCH_JOBS_RE = re.compile(
    r"\b(tìm|search|browse|xem).{0,30}\b(việc|job|intern|thực\s*tập)\b", re.IGNORECASE
)
_JOB_DISCOVERY_RE = re.compile(
    r"\b(thực\s*tập|internship|intern|fresher|junior|remote|hybrid|onsite|"
    r"backend|frontend|full\s*stack|data|ai|ml|marketing|finance|business|"
    r"product|designer|software|developer|engineer)\b",
    re.IGNORECASE,
)
_CV_RE = re.compile(r"\b(cv|resume|hồ\s*sơ)\b", re.IGNORECASE)
_CV_REVIEW_RE = re.compile(
    r"\b(check|kiểm\s*tra|review|đánh\s*giá|chấm|nhận\s*xét|sửa|tối\s*ưu)\b"
    r".{0,25}\b(cv|resume|hồ\s*sơ)\b"
    r"|\b(cv|resume|hồ\s*sơ)\b.{0,25}"
    r"\b(check|kiểm\s*tra|review|đánh\s*giá|chấm|nhận\s*xét|sửa|tối\s*ưu)\b",
    re.IGNORECASE,
)
_APPLICATION_RE = re.compile(
    r"\b(đơn\s*ứng\s*tuyển|application|applied|ứng\s*tuyển)\b", re.IGNORECASE
)
_APPLICATION_STATUS_RE = re.compile(
    r"\b(trạng\s*thái|status|tiến\s*độ|sao\s*rồi|kết\s*quả|đến\s*đâu)\b"
    r".{0,40}\b(đơn|ứng\s*tuyển|application|apply)\b"
    r"|\b(đơn|ứng\s*tuyển|application|apply)\b.{0,40}"
    r"\b(trạng\s*thái|status|tiến\s*độ|sao\s*rồi|kết\s*quả|đến\s*đâu)\b",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(r"\b(event|sự\s*kiện|career\s*fair|workshop|webinar)\b", re.IGNORECASE)
_COMPANY_RE = re.compile(r"\b(company|công\s*ty|employer|nhà\s*tuyển\s*dụng)\b", re.IGNORECASE)
_KNOWN_COMPANY_RE = re.compile(
    r"\b(fpt|fpt\s*software|viettel|vingroup|vinai|momo|vng|shopee|grab|"
    r"google|microsoft|nvidia|samsung|tiki|zalopay|techcombank|vpbank|mb\s*bank)\b",
    re.IGNORECASE,
)
_COMPANY_LOOKUP_RE = re.compile(
    r"\b(là\s*ai|là\s*công\s*ty\s*gì|what\s+is|who\s+is|tell\s+me\s+about)\b",
    re.IGNORECASE,
)
_PROFILE_RE = re.compile(r"\b(profile|hồ\s*sơ|hoàn\s*thiện|completion)\b", re.IGNORECASE)
_INTERVIEW_RE = re.compile(r"\b(interview|phỏng\s*vấn|luyện\s*phỏng\s*vấn|mock)\b", re.IGNORECASE)
_ALERT_RE = re.compile(r"\b(alert|thông\s*báo\s*việc|job\s*alert)\b", re.IGNORECASE)
_SAVED_JOB_RE = re.compile(r"\b(saved|đã\s*lưu|bookmark|yêu\s*thích)\b", re.IGNORECASE)
_PARTNER_PIPELINE_RE = re.compile(r"\b(pipeline|candidate|ứng\s*viên|applicant)\b", re.IGNORECASE)
_CAREER_ADVICE_RE = re.compile(
    r"\b(lộ\s*trình|career\s*path|định\s*hướng|kỹ\s*năng|skill|"
    r"trở\s*thành|become|học\s*gì)\b",
    re.IGNORECASE,
)
_JOB_DETAIL_RE = re.compile(r"\b(chi\s*tiết|detail|xem\s*kỹ|jd|mô\s*tả)\b", re.IGNORECASE)
_SKILL_GAP_RE = re.compile(
    r"\b(phù\s*hợp|fit|match|so\s*(sánh)?\s*cv|gap|thiếu\s*kỹ\s*năng)\b", re.IGNORECASE
)
_SAVE_JOB_RE = re.compile(r"\b(lưu|save|bookmark|yêu\s*thích)\b", re.IGNORECASE)
_APPLY_JOB_RE = re.compile(r"\b(apply|ứng\s*tuyển|nộp\s*đơn)\b", re.IGNORECASE)
_JOB_TARGET_RE = re.compile(r"\b(jd|job|việc|vị\s*trí|role|position|thực\s*tập)\b", re.IGNORECASE)
_REVIEW_RE = re.compile(r"\b(review|đánh\s*giá|văn\s*hóa|culture|môi\s*trường)\b", re.IGNORECASE)
_PLATFORM_KB_RE = re.compile(
    r"\b(chính\s*sách|policy|quy\s*trình|hướng\s*dẫn|cách\s*dùng|"
    r"token\s*ai|ai\s*token|quota|nâng\s*gói|upgrade|billing|ưu\s*đãi|"
    r"student\s*plan|partner\s*plan|gói)\b",
    re.IGNORECASE,
)

_DOMAIN_KEYWORDS = (
    "việc",
    "job",
    "intern",
    "internship",
    "thực tập",
    "career",
    "nghề",
    "cv",
    "resume",
    "hồ sơ",
    "ứng tuyển",
    "application",
    "interview",
    "phỏng vấn",
    "salary",
    "lương",
    "event",
    "sự kiện",
    "company",
    "công ty",
    "employer",
    "recruit",
    "skill",
    "kỹ năng",
    "portfolio",
    "cover letter",
    "jd",
    "vinuni",
    "platform",
    "hệ thống",
    "student",
    "partner",
    "alumni",
    "dashboard",
    "notification",
    "alert",
    "theme",
    "giao diện",
    "cài đặt",
    "settings",
    "account",
    "tài khoản",
    "login",
    "đăng nhập",
    "password",
    "mật khẩu",
    "billing",
    "plan",
    "quota",
    "permission",
    "quyền",
    "role",
    "vai trò",
    "admin",
    "university",
    "lỗi",
    "error",
    "bug",
    "support",
    "hỗ trợ",
)


async def build_agent_plan(
    text: str,
    *,
    principal: Principal,
    session: AsyncSession,
    chat: ChatSession,
) -> AgentPlan | None:
    """Build a plan using live conversation memory before static routing."""

    if recent_plan := await _plan_with_recent_entities(text, session=session, chat=chat):
        return recent_plan
    return plan_for_text(text, principal=principal)


def plan_for_text(text: str, *, principal: Principal) -> AgentPlan | None:
    """Return a deterministic domain-agent plan when confidence is high."""
    lowered = text.lower()

    if _PLATFORM_KB_RE.search(text):
        return AgentPlan(
            agent="platform_knowledge",
            action="tool",
            status_code="using_tool",
            tool_name="knowledge_base_query",
            tool_args={"query": text[:240]},
        )

    support = _platform_support_reply(text)
    if support:
        return AgentPlan(
            agent="platform_support", action="reply", status_code="platform_support", reply=support
        )

    if _ARITHMETIC_ONLY_RE.match(text) or _CODE_ANALYSIS_RE.search(text):
        return _out_of_scope_plan()

    if _SALARY_RE.search(text):
        role = "software engineer" if _IT_ROLE_RE.search(text) else _extract_role_hint(text)
        return AgentPlan(
            agent="career_market",
            action="tool",
            status_code="using_tool",
            tool_name="get_salary_benchmark",
            tool_args={"role": role or "software engineer"},
        )

    if _APPLICATION_STATUS_RE.search(text):
        return AgentPlan(
            agent="application_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_applications",
            tool_args={},
        )

    if _KNOWN_COMPANY_RE.search(text) and (
        _COMPANY_LOOKUP_RE.search(text) or len(text.split()) <= 5
    ):
        return AgentPlan(
            agent="company_research",
            action="tool",
            status_code="using_tool",
            tool_name="search_companies",
            tool_args={"q": _extract_company_query(text)},
        )

    if _CV_REVIEW_RE.search(text):
        return AgentPlan(
            agent="cv_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_cvs",
            tool_args={},
            reason="CV review requires a selected job for precise skill-gap analysis.",
        )

    if _CV_RE.search(text) and (_APPLY_JOB_RE.search(text) or _JOB_TARGET_RE.search(text)):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="recommend_jobs",
            tool_args={"limit": 5},
        )

    if _APPLY_JOB_RE.search(text) and _JOB_TARGET_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="recommend_jobs",
            tool_args={"limit": 5},
        )

    if _NEXT_STEP_RE.search(text):
        return AgentPlan(
            agent="student_success",
            action="tool",
            status_code="using_tool",
            tool_name="get_profile_status",
            tool_args={},
        )

    if _RECOMMEND_JOBS_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="recommend_jobs",
            tool_args={"limit": 5},
        )

    if _JOB_TARGET_RE.search(text) and _JOB_DISCOVERY_RE.search(text):
        return AgentPlan(
            agent="job_search",
            action="tool",
            status_code="using_tool",
            tool_name="search_jobs",
            tool_args=_extract_job_search_args(text),
        )

    if _SEARCH_JOBS_RE.search(text):
        return AgentPlan(
            agent="job_search",
            action="tool",
            status_code="using_tool",
            tool_name="search_jobs",
            tool_args=_extract_job_search_args(text),
        )

    if _CV_RE.search(text) and not _APPLICATION_RE.search(text):
        return AgentPlan(
            agent="cv_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_cvs",
            tool_args={},
        )

    if _APPLICATION_RE.search(text):
        return AgentPlan(
            agent="application_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_applications",
            tool_args={},
        )

    if _EVENT_RE.search(text):
        registered = "của tôi" in lowered or "registered" in lowered or "đăng ký" in lowered
        return AgentPlan(
            agent="event_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_registered_events" if registered else "search_events",
            tool_args={} if registered else {"q": _extract_query(text)},
        )

    if _INTERVIEW_RE.search(text):
        if re.search(r"\b(luyện|practice|mock|chuẩn\s*bị)\b", text, re.IGNORECASE):
            return AgentPlan(
                agent="interview_coach",
                action="tool",
                status_code="using_tool",
                tool_name="start_interview_sim",
                tool_args={"role": _extract_role_hint(text) or "general role"},
            )
        return AgentPlan(
            agent="application_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_upcoming_interviews",
            tool_args={},
        )

    if _ALERT_RE.search(text):
        return AgentPlan(
            agent="notification_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_job_alerts",
            tool_args={},
        )

    if _SAVED_JOB_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="get_saved_jobs",
            tool_args={},
        )

    if _COMPANY_RE.search(text):
        return AgentPlan(
            agent="company_research",
            action="tool",
            status_code="using_tool",
            tool_name="search_companies",
            tool_args={"q": _extract_query(text)},
        )

    if _PROFILE_RE.search(text):
        return AgentPlan(
            agent="student_profile",
            action="tool",
            status_code="using_tool",
            tool_name="get_profile_status",
            tool_args={},
        )

    if _PARTNER_PIPELINE_RE.search(text) and principal.org_id is not None:
        return AgentPlan(
            agent="partner_recruiting",
            action="tool",
            status_code="using_tool",
            tool_name="get_partner_pipeline_summary",
            tool_args={},
        )

    if _CAREER_ADVICE_RE.search(text):
        return AgentPlan(
            agent="career_coach",
            action="tool",
            status_code="using_tool",
            tool_name="get_career_advice",
            tool_args={"role": _extract_role_hint(text) or "career path"},
        )

    if not any(keyword in lowered for keyword in _DOMAIN_KEYWORDS):
        return _out_of_scope_plan()

    return None


async def _plan_with_recent_entities(
    text: str,
    *,
    session: AsyncSession,
    chat: ChatSession,
) -> AgentPlan | None:
    if _SAVE_JOB_RE.search(text):
        entity = await resolve_recent_entity(session, session_id=chat.id, text=text, kinds={"job"})
        if entity and entity.id:
            return AgentPlan(
                agent="job_action",
                action="tool",
                status_code="confirming_action",
                tool_name="save_job",
                tool_args={"job_id": entity.id},
                reason=f"Save recent job: {entity.label}",
            )

    if _APPLY_JOB_RE.search(text):
        entity = await resolve_recent_entity(session, session_id=chat.id, text=text, kinds={"job"})
        if entity and entity.id:
            return AgentPlan(
                agent="application_agent",
                action="tool",
                status_code="confirming_action",
                tool_name="apply_job",
                tool_args={"job_id": entity.id},
                reason=f"Apply to recent job: {entity.label}",
            )

    if _SKILL_GAP_RE.search(text):
        entity = await resolve_recent_entity(session, session_id=chat.id, text=text, kinds={"job"})
        if entity and entity.id:
            return AgentPlan(
                agent="cv_match_agent",
                action="tool",
                status_code="using_tool",
                tool_name="get_skill_gap",
                tool_args={"job_id": entity.id},
                reason=f"Compare CV with recent job: {entity.label}",
            )

    if _JOB_DETAIL_RE.search(text):
        entity = await resolve_recent_entity(session, session_id=chat.id, text=text, kinds={"job"})
        if entity and entity.id:
            return AgentPlan(
                agent="job_research",
                action="tool",
                status_code="using_tool",
                tool_name="get_job_detail",
                tool_args={"job_id": entity.id},
                reason=f"Open recent job detail: {entity.label}",
            )

    if _REVIEW_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=text, kinds={"company"}
        )
        if entity and entity.id:
            return AgentPlan(
                agent="company_research",
                action="tool",
                status_code="using_tool",
                tool_name="get_company_reviews",
                tool_args={"slug": entity.id},
                reason=f"Review recent company: {entity.label}",
            )

    if _COMPANY_RE.search(text) and _JOB_DETAIL_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=text, kinds={"company"}
        )
        if entity and entity.id:
            return AgentPlan(
                agent="company_research",
                action="tool",
                status_code="using_tool",
                tool_name="get_company_detail",
                tool_args={"slug": entity.id},
                reason=f"Open recent company: {entity.label}",
            )

    return None


def _platform_support_reply(text: str) -> str | None:
    if _CONTACT_SUPPORT_RE.search(text):
        return (
            "Bạn có thể liên hệ admin/cố vấn qua mục **Tin nhắn** hoặc **Trợ giúp** "
            "trong hệ thống. Nếu đang ở workspace, hãy bấm biểu tượng chat hoặc avatar "
            "góc phải rồi chọn **Hỗ trợ**. Với lỗi tài khoản khẩn cấp, hãy gửi kèm email "
            "đăng ký và ảnh chụp màn hình để đội hỗ trợ kiểm tra nhanh hơn."
        )
    if _THEME_RE.search(text):
        return (
            "Bạn có thể đổi theme/giao diện tại **Cài đặt** → **Ngôn ngữ & khu vực** "
            "→ **Giao diện**. Chọn Sáng, Tối hoặc Theo hệ thống. Nếu đang ở workspace, "
            "hãy bấm avatar góc phải rồi vào **Cài đặt**."
        )
    if _ACCOUNT_RE.search(text):
        return (
            "Nếu tài khoản gặp vấn đề, hãy dùng **Quên mật khẩu** ở màn hình đăng nhập "
            "hoặc vào **Cài đặt** → **Bảo mật** khi còn đăng nhập được. Nếu tài khoản bị "
            "khóa hoặc email chưa xác thực, hãy liên hệ bộ phận hỗ trợ VinUni Career Platform."
        )
    if _SETTINGS_RE.search(text):
        return (
            "Các thiết lập hệ thống nằm trong **Cài đặt**: ngôn ngữ/giao diện, thông báo, "
            "bảo mật tài khoản, gói sử dụng và quyền/role. Một số mục chỉ hiện nếu tài khoản "
            "của bạn có quyền student, partner hoặc university tương ứng."
        )
    return None



# Public exports so the AI-safety output guard can run the SAME keyword gate
# and SAME refusal copy as a post-generation check (docs/AI_PRODUCT_SPEC.md
# ai.md item 1: pre-LLM regex routing only catches the head of off-topic
# phrasing; the long tail needs a fallback check on the model's own answer).
# ``app.ai.safety`` must not import ``app.modules.*`` (layering), so
# ``output_guard.enforce_keyword_scope`` takes these as plain arguments
# instead of importing this module itself.
DOMAIN_KEYWORDS = _DOMAIN_KEYWORDS
OUT_OF_SCOPE_REPLY = (
    "Mình chỉ hỗ trợ các nội dung liên quan đến VinUni Career Platform, tài khoản, "
    "cài đặt hệ thống, tìm việc, CV, ứng tuyển, phỏng vấn, sự kiện tuyển dụng, "
    "mức lương và định hướng nghề nghiệp. Bạn có thể hỏi mình về một thao tác "
    "trong hệ thống hoặc một cơ hội việc làm nhé."
)


def _out_of_scope_plan() -> AgentPlan:
    return AgentPlan(
        agent="scope_guard",
        action="reply",
        status_code="responding",
        reply=OUT_OF_SCOPE_REPLY,
    )


def _extract_query(text: str) -> str:
    cleaned = re.sub(
        r"\b(tìm|search|browse|xem|cho\s*tôi|giúp\s*tôi|việc|job|intern|"
        r"thực\s*tập|event|sự\s*kiện|company|công\s*ty)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.strip(" ?.!:;-").split())[:120]


def _extract_job_search_args(text: str) -> dict[str, str]:
    args: dict[str, str] = {}
    query = _extract_query(text)
    query = re.sub(
        r"\b(hà\s*nội|ha\s*noi|hanoi|tp\.?\s*hcm|hồ\s*chí\s*minh|"
        r"ho\s*chi\s*minh|saigon|sài\s*gòn)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    args["q"] = " ".join(query.split())[:120]
    province_code = _extract_province_code(text)
    if province_code:
        args["province_code"] = province_code
    return args


def _extract_province_code(text: str) -> str | None:
    if re.search(r"\b(hà\s*nội|ha\s*noi|hanoi)\b", text, re.IGNORECASE):
        return "HN"
    if re.search(
        r"\b(tp\.?\s*hcm|hồ\s*chí\s*minh|ho\s*chi\s*minh|saigon|sài\s*gòn)\b",
        text,
        re.IGNORECASE,
    ):
        return "HCM"
    return None


def _extract_company_query(text: str) -> str:
    match = _KNOWN_COMPANY_RE.search(text)
    if match:
        return " ".join(match.group(0).split())
    cleaned = _COMPANY_LOOKUP_RE.sub(" ", text)
    cleaned = re.sub(r"\b(công\s*ty|company|employer|nhà\s*tuyển\s*dụng)\b", " ", cleaned)
    return " ".join(cleaned.strip(" ?.!:;-").split())[:80]


def _extract_role_hint(text: str) -> str:
    cleaned = _SALARY_RE.sub("", text)
    cleaned = re.sub(
        r"\b(ở|tại|in|vietnam|việt nam|hà nội|hanoi|hcmc|tp\.?\s*hcm|"
        r"lộ\s*trình|career\s*path|định\s*hướng|kỹ\s*năng|skill|"
        r"trở\s*thành|become|học\s*gì|interview|phỏng\s*vấn|luyện|practice|mock)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return " ".join(cleaned.strip(" ?.!:;-").split())[:80]
