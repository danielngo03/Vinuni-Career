"""Deterministic domain-agent planner for the AI assistant."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.application.agentic.memory import resolve_recent_entity
from app.modules.ai_assistant.application.agentic.models import AgentPlan
from app.modules.ai_assistant.application.messages import assistant_message
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
_CAPABILITY_RE = re.compile(
    r"\b(bạn|chatbot|assistant|trợ\s*lý|mày)\b.{0,40}"
    r"\b(làm\s*được\s*gì|giúp\s*gì|hỗ\s*trợ\s*gì|khả\s*năng|can\s*you\s*do|"
    r"help\s*me\s*with)\b"
    r"|\b(làm\s*được\s*gì|giúp\s*gì|hỗ\s*trợ\s*gì|khả\s*năng)\b.{0,40}"
    r"\b(bạn|chatbot|assistant|trợ\s*lý)\b",
    re.IGNORECASE,
)
_DATA_BOUNDARY_RE = re.compile(
    r"\b(dữ\s*liệu|nguồn|source|data|internet|web|google|linkedin|linkedln)\b"
    r".{0,50}\b(từ\s*đâu|ở\s*đâu|có\s*dùng|có\s*truy\s*cập|browse|search|tra\s*cứu)\b"
    r"|\b(có\s*dùng|có\s*truy\s*cập|browse|search|tra\s*cứu)\b.{0,50}"
    r"\b(internet|web|google|linkedin|linkedln|nguồn\s*ngoài)\b",
    re.IGNORECASE,
)
_EXTERNAL_SOURCE_RE = re.compile(
    r"\b(linked\s*in|linkedin|linkedln|linkdn|indeed|glassdoor|topcv|"
    r"vieclam24h|careerbuilder|google|internet|bên\s*ngoài|nguồn\s*ngoài)\b"
    r"|\bweb(?:site)?\s+(?:ngoài|external)\b|\bmạng\s+(?:ngoài|internet)\b",
    re.IGNORECASE,
)
_EXTERNAL_CHANNEL_RE = re.compile(
    r"\b(on|via|from|trên|qua|từ)\s+"
    r"(linked\s*in|linkedin|linkedln|linkdn|indeed|glassdoor|topcv|"
    r"vieclam24h|careerbuilder|google|internet|web|website|mạng)\b",
    re.IGNORECASE,
)
_EXTERNAL_LOOKUP_RE = re.compile(
    r"\b(search|tìm|kiếm|tra\s*cứu|browse|xem|lấy|crawl|scrape|"
    r"recommend|gợi\s*ý|review|đánh\s*giá|so\s*sánh|tin\s*tức|"
    r"mới\s*nhất|latest|news)\b",
    re.IGNORECASE,
)
_SALARY_RE = re.compile(
    r"\b(lương|mức\s*lương|salary|compensation|thu\s*nhập)\b"
    r"|\b(kiếm|earn|paid|trả)\b.{0,30}\b(bao\s*nhiêu|how\s*much)\b"
    r"|\b(bao\s*nhiêu|how\s*much)\b.{0,30}\b(lương|thu\s*nhập|salary|earn)\b",
    re.IGNORECASE,
)
_IT_ROLE_RE = re.compile(
    r"\b(it|software|developer|dev|engineer|lập\s*trình|cntt)\b", re.IGNORECASE
)
_RECOMMEND_JOBS_RE = re.compile(
    r"\b(gợi\s*ý|phù\s*hợp|recommend|suggest).{0,40}\b(việc|job|intern|thực\s*tập)\b"
    r"|\b(việc|job|intern|thực\s*tập).{0,40}\b(phù\s*hợp|recommend|suggest)\b",
    re.IGNORECASE,
)
_JOB_DISCOVERY_REQUEST_RE = re.compile(
    r"\b(có|available|open|opening|đang\s*tuyển|tuyển|remote|hybrid|onsite)\b"
    r".{0,60}\b(thực\s*tập|internship|intern|fresher|junior|backend|frontend|"
    r"full\s*stack|data|ai|ml|marketing|finance|business|product|designer|"
    r"software|developer|engineer|analyst|qa|qc|testing|research|consulting|"
    r"sales|hr|accounting|audit|operations|ux|ui|design)\b"
    r"|\b(thực\s*tập|internship|intern|fresher|junior|backend|frontend|"
    r"full\s*stack|data|ai|ml|marketing|finance|business|product|designer|"
    r"software|developer|engineer|analyst|qa|qc|testing|research|consulting|"
    r"sales|hr|accounting|audit|operations|ux|ui|design)\b"
    r".{0,60}\b(có|available|open|opening|đang\s*tuyển|tuyển|remote|hybrid|onsite)\b",
    re.IGNORECASE,
)
_NEXT_STEP_RE = re.compile(
    r"\b(tôi\s*nên\s*làm\s*gì|nên\s*làm\s*gì|bước\s*tiếp|next\s*step|"
    r"làm\s*gì\s*tiếp|hướng\s*dẫn\s*tôi)\b",
    re.IGNORECASE,
)
_SEARCH_JOBS_RE = re.compile(
    r"\b(tìm|search|browse|xem|kiếm|có|available|opening|tuyển)\b"
    r".{0,50}\b(việc|job|jobs|intern|internship|thực\s*tập|vị\s*trí|role|position)\b"
    r"|\b(việc|job|jobs|intern|internship|thực\s*tập|vị\s*trí|role|position)\b"
    r".{0,50}\b(nào|gì|mở|open|available|đang\s*tuyển|phù\s*hợp)\b",
    re.IGNORECASE,
)
_JOB_DISCOVERY_RE = re.compile(
    r"\b(thực\s*tập|internship|intern|fresher|junior|remote|hybrid|onsite|"
    r"backend|frontend|full\s*stack|data|ai|ml|marketing|finance|business|"
    r"product|designer|software|developer|engineer|analyst|qa|qc|testing|"
    r"research|lab|consulting|consultant|sales|hr|human\s*resources|"
    r"accounting|audit|operations|supply\s*chain|ux|ui|design)\b",
    re.IGNORECASE,
)
_CV_RE = re.compile(r"\b(cv|resume|hồ\s*sơ)\b", re.IGNORECASE)
_CV_NAV_RE = re.compile(
    r"\b(upload|tải\s*lên|tạo|create|xoá|xóa|delete|download|tải\s*xuống|"
    r"sửa|chỉnh|edit|rename|đổi\s*tên|duplicate|nhân\s*bản)\b"
    r".{0,35}\b(cv|resume|hồ\s*sơ)\b"
    r"|\b(cv|resume|hồ\s*sơ)\b.{0,35}"
    r"\b(upload|tải\s*lên|tạo|create|xoá|xóa|delete|download|tải\s*xuống|"
    r"sửa|chỉnh|edit|rename|đổi\s*tên|duplicate|nhân\s*bản)\b",
    re.IGNORECASE,
)
_CV_REVIEW_RE = re.compile(
    r"\b(check|kiểm\s*tra|review|đánh\s*giá|chấm|nhận\s*xét|tối\s*ưu|"
    r"cải\s*thiện|thiếu\s*gì|bổ\s*sung\s*gì|ats)\b"
    r".{0,25}\b(cv|resume|hồ\s*sơ)\b"
    r"|\b(cv|resume|hồ\s*sơ)\b.{0,25}"
    r"\b(check|kiểm\s*tra|review|đánh\s*giá|chấm|nhận\s*xét|tối\s*ưu|"
    r"cải\s*thiện|thiếu\s*gì|bổ\s*sung\s*gì|ats)\b",
    re.IGNORECASE,
)
_APPLICATION_RE = re.compile(
    r"\b(đơn\s*ứng\s*tuyển|application|applications|applied|ứng\s*tuyển|đã\s*nộp)\b",
    re.IGNORECASE,
)
_WITHDRAW_APPLICATION_RE = re.compile(
    r"\b(rút|huỷ|hủy|cancel|withdraw)\b.{0,40}"
    r"\b(đơn|ứng\s*tuyển|application|apply)\b"
    r"|\b(đơn|ứng\s*tuyển|application|apply)\b.{0,40}"
    r"\b(rút|huỷ|hủy|cancel|withdraw)\b",
    re.IGNORECASE,
)
_APPLICATION_STATUS_RE = re.compile(
    r"\b(trạng\s*thái|status|tiến\s*độ|sao\s*rồi|kết\s*quả|đến\s*đâu)\b"
    r".{0,40}\b(đơn|ứng\s*tuyển|application|apply)\b"
    r"|\b(đơn|ứng\s*tuyển|application|apply)\b.{0,40}"
    r"\b(trạng\s*thái|status|tiến\s*độ|sao\s*rồi|kết\s*quả|đến\s*đâu)\b",
    re.IGNORECASE,
)
_APPLICATION_NAV_RE = re.compile(
    r"\b(update|cập\s*nhật|sửa|chỉnh|edit|đổi|change)\b.{0,40}"
    r"\b(đơn|ứng\s*tuyển|application|apply)\b"
    r"|\b(đơn|ứng\s*tuyển|application|apply)\b.{0,40}"
    r"\b(update|cập\s*nhật|sửa|chỉnh|edit|đổi|change)\b",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(r"\b(event|sự\s*kiện|career\s*fair|workshop|webinar)\b", re.IGNORECASE)
_EVENT_ACTION_RE = re.compile(
    r"\b(đăng\s*ký|register|tham\s*gia|join|huỷ|hủy|cancel)\b.{0,45}"
    r"\b(event|sự\s*kiện|career\s*fair|workshop|webinar)\b"
    r"|\b(event|sự\s*kiện|career\s*fair|workshop|webinar)\b.{0,45}"
    r"\b(đăng\s*ký|register|tham\s*gia|join|huỷ|hủy|cancel)\b",
    re.IGNORECASE,
)
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
_ALERT_ACTION_RE = re.compile(
    r"\b(tạo|create|bật|turn\s*on|enable|tắt|turn\s*off|disable|xoá|xóa|delete|sửa|edit)\b"
    r".{0,45}\b(alert|thông\s*báo\s*việc|job\s*alert)\b"
    r"|\b(alert|thông\s*báo\s*việc|job\s*alert)\b.{0,45}"
    r"\b(tạo|create|bật|turn\s*on|enable|tắt|turn\s*off|disable|xoá|xóa|delete|sửa|edit)\b",
    re.IGNORECASE,
)
_SAVED_JOB_RE = re.compile(
    r"\b(saved|đã\s*lưu|danh\s*sách\s*lưu|yêu\s*thích)\b", re.IGNORECASE
)
_UNSAVE_JOB_RE = re.compile(
    r"\b(bỏ\s*lưu|unsave|unbookmark|remove\s+saved|xoá\s+khỏi\s+danh\s+sách\s+lưu)\b"
    r"|\b(xoá|xóa|remove)\b.{0,30}\b(saved|đã\s*lưu|bookmark)\b",
    re.IGNORECASE,
)
_PARTNER_PIPELINE_RE = re.compile(r"\b(pipeline|candidate|ứng\s*viên|applicant)\b", re.IGNORECASE)
_CAREER_ADVICE_RE = re.compile(
    r"\b(lộ\s*trình|career\s*path|định\s*hướng|kỹ\s*năng|skill|"
    r"trở\s*thành|become|học\s*gì|ngành\s*nào|nghề\s*nào|career\s*advice)\b",
    re.IGNORECASE,
)
_JOB_DETAIL_RE = re.compile(r"\b(chi\s*tiết|detail|xem\s*kỹ|jd|mô\s*tả)\b", re.IGNORECASE)
_SKILL_GAP_RE = re.compile(
    r"\b(phù\s*hợp|fit|match|so\s*(sánh)?\s*cv|gap|thiếu\s*kỹ\s*năng)\b", re.IGNORECASE
)
_SAVE_JOB_RE = re.compile(r"\b(lưu|save|bookmark|yêu\s*thích)\b", re.IGNORECASE)
_APPLY_JOB_RE = re.compile(
    r"\b(apply|applyy|aply|appyly|ứng\s*tuyển|nộp\s*đơn)\b", re.IGNORECASE
)
_JOB_TARGET_RE = re.compile(r"\b(jd|job|việc|vị\s*trí|role|position|thực\s*tập)\b", re.IGNORECASE)
_REVIEW_RE = re.compile(r"\b(review|đánh\s*giá|văn\s*hóa|culture|môi\s*trường)\b", re.IGNORECASE)
_COVER_LETTER_RE = re.compile(
    r"\b(cover\s*letter|thư\s*ứng\s*tuyển|motivation\s*letter|thư\s*xin\s*việc)\b",
    re.IGNORECASE,
)
_PORTFOLIO_RE = re.compile(
    r"\b(portfolio|github|linkedin|dự\s*án|project|profile\s*cá\s*nhân)\b",
    re.IGNORECASE,
)
_INTERVIEW_PREP_RE = re.compile(
    r"\b(prepare|chuẩn\s*bị|luyện|practice|mock|câu\s*hỏi|trả\s*lời)\b"
    r".{0,50}\b(interview|phỏng\s*vấn)\b"
    r"|\b(interview|phỏng\s*vấn)\b.{0,50}"
    r"\b(prepare|chuẩn\s*bị|luyện|practice|mock|câu\s*hỏi|trả\s*lời)\b",
    re.IGNORECASE,
)
_INTERVIEW_ACTION_RE = re.compile(
    r"\b(đổi\s*lịch|reschedule|huỷ|hủy|cancel|confirm|xác\s*nhận)\b"
    r".{0,50}\b(interview|phỏng\s*vấn)\b"
    r"|\b(interview|phỏng\s*vấn)\b.{0,50}"
    r"\b(đổi\s*lịch|reschedule|huỷ|hủy|cancel|confirm|xác\s*nhận)\b",
    re.IGNORECASE,
)
_OFFER_RE = re.compile(
    r"\b(offer|lời\s*mời|đề\s*nghị|deal|thương\s*lượng|negotiate|"
    r"negotiation|counter\s*offer|hợp\s*đồng|contract)\b",
    re.IGNORECASE,
)
_OFFER_ACTION_RE = re.compile(
    r"\b(accept|decline|reject|từ\s*chối|chấp\s*nhận|ký|sign|nộp|submit)\b"
    r".{0,45}\b(offer|lời\s*mời|hợp\s*đồng|contract)\b"
    r"|\b(offer|lời\s*mời|hợp\s*đồng|contract)\b.{0,45}"
    r"\b(accept|decline|reject|từ\s*chối|chấp\s*nhận|ký|sign|nộp|submit)\b",
    re.IGNORECASE,
)
_REJECTION_RE = re.compile(
    r"\b(reject|rejected|từ\s*chối|trượt|fail|rớt|không\s*đậu)\b", re.IGNORECASE
)
_CAREER_UNCERTAIN_RE = re.compile(
    r"\b(chưa\s*biết|không\s*biết|mơ\s*hồ|lost|confused|bối\s*rối|"
    r"nên\s*theo|nên\s*chọn|phù\s*hợp\s*với\s*tôi)\b",
    re.IGNORECASE,
)
_FIRST_JOB_RE = re.compile(
    r"\b(no\s*experience|không\s*có\s*kinh\s*nghiệm|chưa\s*có\s*kinh\s*nghiệm|"
    r"first\s*job|việc\s*đầu\s*tiên|năm\s*nhất|năm\s*hai|freshman|sophomore)\b",
    re.IGNORECASE,
)
_JOB_SEARCH_START_RE = re.compile(
    r"\b(tìm\s*việc|job\s*search|kiếm\s*việc|bắt\s*đầu\s*tìm|start\s*looking)\b"
    r".{0,80}\b(chưa\s*biết|không\s*biết|bắt\s*đầu|làm\s*gì|như\s*thế\s*nào|how)\b"
    r"|\b(chưa\s*biết|không\s*biết)\b.{0,80}\b(tìm\s*việc|kiếm\s*việc|apply)\b",
    re.IGNORECASE,
)
_SCAM_OR_SAFETY_RE = re.compile(
    r"\b(lừa\s*đảo|scam|đáng\s*ngờ|suspicious|thu\s*phí|phí\s*ứng\s*tuyển|"
    r"chuyển\s*khoản|đặt\s*cọc|giữ\s*chỗ|passport|cmnd|cccd|"
    r"quấy\s*rối|harassment|phân\s*biệt\s*đối\s*xử|discrimination)\b",
    re.IGNORECASE,
)
_PLATFORM_KB_RE = re.compile(
    r"\b(chính\s*sách|policy|quy\s*trình|hướng\s*dẫn|cách\s*dùng|"
    r"token\s*ai|ai\s*token|quota|nâng\s*gói|upgrade|billing|ưu\s*đãi|"
    r"student\s*plan|partner\s*plan|gói)\b",
    re.IGNORECASE,
)
# Partner asking about their OWN org's uploaded internal documents / policies.
# Routes to the RAG tool (server-side access scoping decides what is returned).
# Matches an internal-doc noun (policy/handbook/guideline/process/document...)
# OR an explicit possessive ("our"/"của công ty"/"nội bộ") near a doc/query verb.
_PARTNER_INTERNAL_DOCS_RE = re.compile(
    r"\b(nội\s*bộ|internal)\b"
    r"|\b(chính\s*sách|policy|policies|quy\s*trình|quy\s*định|quy\s*chế|"
    r"hướng\s*dẫn|guideline|guidelines|handbook|sổ\s*tay|playbook|"
    r"tài\s*liệu|document|documents|onboarding|benefit|phúc\s*lợi|"
    r"rubric|tiêu\s*chí\s*phỏng\s*vấn)\b"
    r".{0,40}\b(công\s*ty|tổ\s*chức|của\s*(chúng\s*)?(tôi|ta)|our|company|"
    r"nội\s*bộ|internal|nói\s*gì|quy\s*định|ra\s*sao|thế\s*nào)\b"
    r"|\b(công\s*ty|tổ\s*chức|của\s*(chúng\s*)?(tôi|ta)|our|company)\b"
    r".{0,40}\b(chính\s*sách|policy|policies|quy\s*trình|quy\s*định|quy\s*chế|"
    r"hướng\s*dẫn|guideline|guidelines|handbook|sổ\s*tay|playbook|"
    r"tài\s*liệu|document|documents|onboarding|benefit|phúc\s*lợi|"
    r"rubric|tiêu\s*chí\s*phỏng\s*vấn)\b",
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
    "apply",
    "application",
    "vị trí",
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
    "linkedin",
    "github",
    "project",
    "cover letter",
    "thư ứng tuyển",
    "jd",
    "offer",
    "hợp đồng",
    "thương lượng",
    "reject",
    "từ chối",
    "trượt",
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
    "scam",
    "lừa đảo",
    "đáng ngờ",
    "quấy rối",
    "phân biệt đối xử",
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
    locale: str = "vi",
) -> AgentPlan | None:
    """Build a deterministic plan before the LLM tool-calling loop fallback.

    Persona routing is resolved via the persona registry (a single source of
    truth) instead of scattered ``if persona == ...`` branches: each persona's
    :class:`PersonaProfile` names its own planner adapter (``student_agent_plan``
    / ``partner_agent_plan`` / ``university_agent_plan``). Returning ``None``
    sends the turn to the governed LLM tool-calling loop with that persona's
    system prompt + tool surface. Imported lazily to avoid a circular import
    (the registry imports this module for the planner adapters).
    """
    from app.modules.ai_assistant.application.agentic.persona_registry import (
        resolve_persona_profile,
    )

    profile = resolve_persona_profile(principal.persona)
    return await profile.planner(
        text, principal=principal, session=session, chat=chat, locale=locale
    )


async def student_agent_plan(
    text: str,
    *,
    principal: Principal,
    session: AsyncSession,
    chat: ChatSession,
    locale: str = "vi",
) -> AgentPlan | None:
    """Student/alumni deterministic planner: recent-entity resolver → full planner.

    Behaviour-identical to the historical student branch of ``build_agent_plan``.
    """
    if recent_plan := await _plan_with_recent_entities(
        text, session=session, chat=chat, locale=locale
    ):
        return recent_plan
    return plan_for_text(text, principal=principal, locale=locale)


async def partner_agent_plan(
    text: str,
    *,
    principal: Principal,
    session: AsyncSession,  # noqa: ARG001 — signature parity with the registry
    chat: ChatSession,  # noqa: ARG001 — signature parity with the registry
    locale: str = "vi",
) -> AgentPlan | None:
    """Partner-recruiter deterministic planner (SMALL, org-scoped intents only).

    Behaviour-identical to the historical partner branch: only the partner
    intent matcher runs; the student recent-entity resolver + full planner are
    intentionally NOT run (they only understand student tools). Everything else
    returns ``None`` → the LLM loop with the partner prompt + partner tools.
    """
    return plan_for_partner(text, principal=principal, locale=locale)


async def university_agent_plan(
    text: str,  # noqa: ARG001 — deliberate no-op minimal seam (see below)
    *,
    principal: Principal,  # noqa: ARG001
    session: AsyncSession,  # noqa: ARG001
    chat: ChatSession,  # noqa: ARG001
    locale: str = "vi",  # noqa: ARG001
) -> AgentPlan | None:
    """University-staff planner: minimal, correct seam.

    University staff have NO deterministic pre-LLM plan yet, so every open turn
    returns ``None`` and reaches the governed LLM tool-calling loop (which
    selects the university system prompt + the shared university tool surface).
    This is the correct fix for the previously broken stub, which ran the
    STUDENT planner and mis-routed university turns onto student-only tools that
    dispatch then rejected. A parallel workstream owns the full university
    planner; this function is the deliberate placeholder for it.
    """
    return None


def plan_for_partner(text: str, *, principal: Principal, locale: str = "vi") -> AgentPlan | None:
    """Deterministic partner-recruiter routing — a few safe, cheap replies only.

    Keeps ONLY: capability guide, data-boundary / external-source refusal,
    platform help/support, and the partner pipeline summary tool. EVERYTHING
    else returns ``None`` so the message falls through to the LLM tool-calling
    loop (partner system prompt + the 11 partner tools). Offline (no real
    provider) the loop degrades to an ai-unavailable reply — acceptable.

    This is intentionally NOT the full student planner: a partner must never be
    routed onto student tools (apply_job, get_my_cvs, recommend_jobs, ...) or a
    student clarifier reply.
    """
    if _CAPABILITY_RE.search(text):
        return AgentPlan(
            agent="partner_capability_guide",
            action="reply",
            status_code="responding",
            reply=_partner_capability_reply(locale),
        )

    # Data-boundary probe OR any external-source/channel lookup ("search on
    # LinkedIn", "google this company"): refuse with the partner-scoped copy.
    # ``_external_source_plan`` is reused purely as a detector here.
    if _DATA_BOUNDARY_RE.search(text) or _external_source_plan(text, locale) is not None:
        return AgentPlan(
            agent="partner_platform_boundary",
            action="reply",
            status_code="responding",
            reply=_partner_data_boundary_reply(locale),
        )

    if support := _platform_support_reply(text, locale):
        return AgentPlan(
            agent="platform_support",
            action="reply",
            status_code="platform_support",
            reply=support,
        )

    # Partner asking about their OWN org's internal documents / policies → RAG.
    # Access is scoped server-side in ``get_kb_ids_for_query`` (org-internal +
    # applicant-facing KBs the recruiter is authorized to read); another org's
    # internal docs are never reachable.
    if _PARTNER_INTERNAL_DOCS_RE.search(text) and principal.org_id is not None:
        return AgentPlan(
            agent="partner_knowledge",
            action="tool",
            status_code="using_tool",
            tool_name="knowledge_base_query",
            tool_args={"query": text[:240]},
        )

    if _PARTNER_PIPELINE_RE.search(text) and principal.org_id is not None:
        return AgentPlan(
            agent="partner_recruiting",
            action="tool",
            status_code="using_tool",
            tool_name="get_partner_pipeline_summary",
            tool_args={},
        )

    return None


def plan_for_text(text: str, *, principal: Principal, locale: str = "vi") -> AgentPlan | None:
    """Return a deterministic domain-agent plan when confidence is high."""
    lowered = text.lower()

    if _CAPABILITY_RE.search(text):
        return AgentPlan(
            agent="capability_guide",
            action="reply",
            status_code="responding",
            reply=_capability_reply(locale),
        )

    if _DATA_BOUNDARY_RE.search(text):
        return AgentPlan(
            agent="platform_boundary",
            action="reply",
            status_code="responding",
            reply=_data_boundary_reply(locale),
        )

    external_plan = _external_source_plan(text, locale)
    if external_plan:
        return external_plan

    if _PLATFORM_KB_RE.search(text):
        return AgentPlan(
            agent="platform_knowledge",
            action="tool",
            status_code="using_tool",
            tool_name="knowledge_base_query",
            tool_args={"query": text[:240]},
        )

    support = _platform_support_reply(text, locale)
    if support:
        return AgentPlan(
            agent="platform_support", action="reply", status_code="platform_support", reply=support
        )

    if _ARITHMETIC_ONLY_RE.match(text) or _CODE_ANALYSIS_RE.search(text):
        return _out_of_scope_plan(locale)

    if _SCAM_OR_SAFETY_RE.search(text):
        return AgentPlan(
            agent="student_safety",
            action="reply",
            status_code="responding",
            reply=_scam_or_safety_reply(locale),
        )

    if _OFFER_ACTION_RE.search(text):
        return AgentPlan(
            agent="offer_coach",
            action="reply",
            status_code="responding",
            reply=_offer_action_reply(locale),
        )

    if _REJECTION_RE.search(text):
        return AgentPlan(
            agent="career_coach",
            action="reply",
            status_code="responding",
            reply=_rejection_reply(locale),
        )

    if _COVER_LETTER_RE.search(text):
        return AgentPlan(
            agent="application_coach",
            action="reply",
            status_code="responding",
            reply=_cover_letter_reply(locale),
        )

    if _PORTFOLIO_RE.search(text) and not _SEARCH_JOBS_RE.search(text):
        return AgentPlan(
            agent="profile_coach",
            action="reply",
            status_code="responding",
            reply=_portfolio_reply(locale),
        )

    if _OFFER_RE.search(text) and not _SALARY_RE.search(text):
        return AgentPlan(
            agent="offer_coach",
            action="reply",
            status_code="responding",
            reply=_offer_reply(locale),
        )

    if _FIRST_JOB_RE.search(text):
        return AgentPlan(
            agent="career_coach",
            action="reply",
            status_code="responding",
            reply=_first_job_reply(locale),
        )

    if _JOB_SEARCH_START_RE.search(text) or (
        _CAREER_UNCERTAIN_RE.search(text)
        and not _CV_RE.search(text)
        and not _RECOMMEND_JOBS_RE.search(text)
    ):
        return AgentPlan(
            agent="career_coach",
            action="tool",
            status_code="using_tool",
            tool_name="get_profile_status",
            tool_args={},
            reason="Student is unsure about next career direction.",
        )

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

    if _WITHDRAW_APPLICATION_RE.search(text):
        return AgentPlan(
            agent="application_agent",
            action="reply",
            status_code="responding",
            reply=_withdraw_application_reply(locale),
        )

    if _APPLICATION_NAV_RE.search(text):
        return AgentPlan(
            agent="application_agent",
            action="reply",
            status_code="responding",
            reply=_application_navigation_reply(locale),
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

    if _CV_NAV_RE.search(text):
        return AgentPlan(
            agent="cv_agent",
            action="reply",
            status_code="responding",
            reply=_cv_navigation_reply(text, locale),
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

    if _APPLY_JOB_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="recommend_jobs",
            tool_args={"limit": 5},
            reason="Student wants to apply but has not selected a specific job yet.",
        )

    if _NEXT_STEP_RE.search(text):
        return AgentPlan(
            agent="student_success",
            action="tool",
            status_code="using_tool",
            tool_name="get_profile_status",
            tool_args={},
        )

    if _ALERT_ACTION_RE.search(text):
        return AgentPlan(
            agent="notification_agent",
            action="reply",
            status_code="responding",
            reply=_alert_action_reply(text, locale),
        )

    if _RECOMMEND_JOBS_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="recommend_jobs",
            tool_args={"limit": 5},
        )

    if _UNSAVE_JOB_RE.search(text):
        return AgentPlan(
            agent="job_action",
            action="reply",
            status_code="responding",
            reply=_unsave_job_reply(locale),
        )

    if _SAVE_JOB_RE.search(text) and not _SAVED_JOB_RE.search(text):
        return AgentPlan(
            agent="job_action",
            action="reply",
            status_code="responding",
            reply=_save_job_needs_selection_reply(locale),
        )

    if _JOB_DISCOVERY_REQUEST_RE.search(text):
        return AgentPlan(
            agent="job_search",
            action="tool",
            status_code="using_tool",
            tool_name="search_jobs",
            tool_args=_extract_job_search_args(text),
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

    registered_event_query = (
        "của tôi" in lowered
        or "registered" in lowered
        or "đã đăng ký" in lowered
        or "đăng ký rồi" in lowered
    )
    if _EVENT_ACTION_RE.search(text) and not registered_event_query:
        return AgentPlan(
            agent="event_agent",
            action="reply",
            status_code="responding",
            reply=_event_action_reply(text, locale),
        )

    if _EVENT_RE.search(text):
        return AgentPlan(
            agent="event_agent",
            action="tool",
            status_code="using_tool",
            tool_name="get_my_registered_events" if registered_event_query else "search_events",
            tool_args={} if registered_event_query else {"q": _extract_query(text)},
        )

    if _INTERVIEW_RE.search(text):
        if _INTERVIEW_ACTION_RE.search(text):
            return AgentPlan(
                agent="application_agent",
                action="reply",
                status_code="responding",
                reply=_interview_action_reply(locale),
            )
        if _INTERVIEW_PREP_RE.search(text):
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
        return _out_of_scope_plan(locale)

    return AgentPlan(
        agent="clarifier",
        action="reply",
        status_code="responding",
        reply=_domain_clarification_reply(locale),
    )


def _external_source_plan(text: str, locale: str) -> AgentPlan | None:
    source_match = _EXTERNAL_SOURCE_RE.search(text)
    channel_match = _EXTERNAL_CHANNEL_RE.search(text)
    if not (source_match or channel_match):
        return None
    if not (channel_match or _EXTERNAL_LOOKUP_RE.search(text)):
        return None

    source = _external_source_label(text, locale)
    # ``google_lookup`` is the sentinel for the Google-only case that must not
    # trigger the external-source refusal unless a channel phrase is present.
    if _external_source_is_google(text) and not channel_match:
        return None
    return AgentPlan(
        agent="platform_boundary",
        action="reply",
        status_code="responding",
        reply=_external_source_reply(source, locale),
    )


def _external_source_is_google(text: str) -> bool:
    lowered = text.lower()
    return (
        "google" in lowered
        and not re.search(r"\blinked\s*in\b|\blinkedin\b|\blinkedln\b|\blinkdn\b", lowered)
    )


def _external_source_label(text: str, locale: str) -> str:
    lowered = text.lower()
    if re.search(r"\blinked\s*in\b|\blinkedin\b|\blinkedln\b|\blinkdn\b", lowered):
        return "LinkedIn"
    if "google" in lowered:
        return "Google"
    if "indeed" in lowered:
        return "Indeed"
    if "glassdoor" in lowered:
        return "Glassdoor"
    if "topcv" in lowered:
        return "TopCV"
    if "vieclam24h" in lowered:
        return "Vieclam24h"
    if "careerbuilder" in lowered:
        return "CareerBuilder"
    if re.search(r"\bweb(?:site)?\b", lowered):
        return assistant_message("planner.external_source_label.external_website", locale)
    if re.search(r"\bmạng\b|\binternet\b", lowered):
        return assistant_message("planner.external_source_label.internet", locale)
    return assistant_message("planner.external_source_label.external_default", locale)


def _external_source_reply(source: str, locale: str) -> str:
    return assistant_message("planner.external_source", locale, source=source)


def _capability_reply(locale: str) -> str:
    return assistant_message("planner.capability", locale)


def _data_boundary_reply(locale: str) -> str:
    return assistant_message("planner.data_boundary", locale)


def _partner_capability_reply(locale: str) -> str:
    return assistant_message("planner.partner.capability", locale)


def _partner_data_boundary_reply(locale: str) -> str:
    return assistant_message("planner.partner.data_boundary", locale)


def _withdraw_application_reply(locale: str) -> str:
    return assistant_message("planner.withdraw_application", locale)


def _application_navigation_reply(locale: str) -> str:
    return assistant_message("planner.application_navigation", locale)


def _cv_navigation_reply(text: str, locale: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(upload|tải\s*lên|tạo|create)\b", lowered):
        return assistant_message("planner.cv_nav.upload_create", locale)
    if re.search(r"\b(xoá|xóa|delete)\b", lowered):
        return assistant_message("planner.cv_nav.delete", locale)
    if re.search(r"\b(download|tải\s*xuống)\b", lowered):
        return assistant_message("planner.cv_nav.download", locale)
    if re.search(r"\b(sửa|chỉnh|edit|rename|đổi\s*tên|duplicate|nhân\s*bản)\b", lowered):
        return assistant_message("planner.cv_nav.edit", locale)
    return assistant_message("planner.cv_nav.default", locale)


def _save_job_needs_selection_reply(locale: str) -> str:
    return assistant_message("planner.save_job_needs_selection", locale)


def _unsave_job_reply(locale: str) -> str:
    return assistant_message("planner.unsave_job", locale)


def _event_action_reply(text: str, locale: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(huỷ|hủy|cancel)\b", lowered):
        return assistant_message("planner.event_action.cancel", locale)
    return assistant_message("planner.event_action.register", locale)


def _interview_action_reply(locale: str) -> str:
    return assistant_message("planner.interview_action", locale)


def _alert_action_reply(text: str, locale: str) -> str:
    lowered = text.lower()
    action_key = "planner.alert_action.manage"
    if re.search(r"\b(tạo|create|bật|turn\s*on|enable)\b", lowered):
        action_key = "planner.alert_action.create"
    elif re.search(r"\b(tắt|turn\s*off|disable|xoá|xóa|delete|sửa|edit)\b", lowered):
        action_key = "planner.alert_action.edit"
    action = assistant_message(action_key, locale)
    return assistant_message("planner.alert_action", locale, action=action)


def _offer_action_reply(locale: str) -> str:
    return assistant_message("planner.offer_action", locale)


def _scam_or_safety_reply(locale: str) -> str:
    return assistant_message("planner.scam_or_safety", locale)


def _domain_clarification_reply(locale: str) -> str:
    return assistant_message("planner.domain_clarification", locale)


async def _plan_with_recent_entities(
    text: str,
    *,
    session: AsyncSession,
    chat: ChatSession,
    locale: str = "vi",
) -> AgentPlan | None:
    if _UNSAVE_JOB_RE.search(text):
        return AgentPlan(
            agent="job_action",
            action="reply",
            status_code="responding",
            reply=_unsave_job_reply(locale),
        )

    if _SAVED_JOB_RE.search(text):
        return AgentPlan(
            agent="job_matching",
            action="tool",
            status_code="using_tool",
            tool_name="get_saved_jobs",
            tool_args={},
        )

    if _SAVE_JOB_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=_reference_slice(text, kind="job"), kinds={"job"}
        )
        if entity and entity.id:
            return AgentPlan(
                agent="job_action",
                action="tool",
                status_code="confirming_action",
                tool_name="save_job",
                tool_args={"job_id": entity.id},
                reason=f"Lưu việc làm: {entity.label}",
            )

    if _APPLY_JOB_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=_reference_slice(text, kind="job"), kinds={"job"}
        )
        if entity and entity.id:
            tool_args = {"job_id": entity.id}
            cv_entity = await resolve_recent_entity(
                session, session_id=chat.id, text=_reference_slice(text, kind="cv"), kinds={"cv"}
            )
            if cv_entity and cv_entity.id and _CV_RE.search(text):
                tool_args["cv_id"] = cv_entity.id
            return AgentPlan(
                agent="application_agent",
                action="tool",
                status_code="confirming_action",
                tool_name="apply_job",
                tool_args=tool_args,
                reason=f"Ứng tuyển vị trí: {entity.label}",
            )

    if _SKILL_GAP_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=_reference_slice(text, kind="job"), kinds={"job"}
        )
        if entity and entity.id:
            tool_args = {"job_id": entity.id}
            cv_entity = await resolve_recent_entity(
                session, session_id=chat.id, text=_reference_slice(text, kind="cv"), kinds={"cv"}
            )
            if cv_entity and cv_entity.id and _CV_RE.search(text):
                tool_args["cv_id"] = cv_entity.id
            return AgentPlan(
                agent="cv_match_agent",
                action="tool",
                status_code="using_tool",
                tool_name="get_skill_gap",
                tool_args=tool_args,
                reason=f"So CV với việc làm: {entity.label}",
            )

    if _JOB_DETAIL_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=_reference_slice(text, kind="job"), kinds={"job"}
        )
        if entity and entity.id:
            return AgentPlan(
                agent="job_research",
                action="tool",
                status_code="using_tool",
                tool_name="get_job_detail",
                tool_args={"job_id": entity.id},
                reason=f"Mở chi tiết việc làm: {entity.label}",
            )

    if _INTERVIEW_PREP_RE.search(text):
        entity = await resolve_recent_entity(
            session, session_id=chat.id, text=_reference_slice(text, kind="job"), kinds={"job"}
        )
        if entity and entity.id:
            return AgentPlan(
                agent="interview_coach",
                action="tool",
                status_code="using_tool",
                tool_name="start_interview_sim",
                tool_args={"job_id": entity.id},
                reason=f"Luyện phỏng vấn cho vị trí: {entity.label}",
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


def _platform_support_reply(text: str, locale: str) -> str | None:
    if _CONTACT_SUPPORT_RE.search(text):
        return assistant_message("planner.support.contact", locale)
    if _THEME_RE.search(text):
        return assistant_message("planner.support.theme", locale)
    if _ACCOUNT_RE.search(text):
        return assistant_message("planner.support.account", locale)
    if _SETTINGS_RE.search(text):
        return assistant_message("planner.support.settings", locale)
    return None


def _cover_letter_reply(locale: str) -> str:
    return assistant_message("planner.cover_letter", locale)


def _portfolio_reply(locale: str) -> str:
    return assistant_message("planner.portfolio", locale)


def _offer_reply(locale: str) -> str:
    return assistant_message("planner.offer", locale)


def _rejection_reply(locale: str) -> str:
    return assistant_message("planner.rejection", locale)


def _first_job_reply(locale: str) -> str:
    return assistant_message("planner.first_job", locale)



# Public exports so the AI-safety output guard can run the SAME keyword gate
# and SAME refusal copy as a post-generation check (docs/AI_PRODUCT_SPEC.md
# ai.md item 1: pre-LLM regex routing only catches the head of off-topic
# phrasing; the long tail needs a fallback check on the model's own answer).
# ``app.ai.safety`` must not import ``app.modules.*`` (layering), so
# ``output_guard.enforce_keyword_scope`` takes these as plain arguments
# instead of importing this module itself.
DOMAIN_KEYWORDS = _DOMAIN_KEYWORDS
# Default-locale (vi) constant kept for backward-compatible callers such as the
# post-generation keyword scope guard, which uses a single default refusal
# string. Locale-aware callers should use ``out_of_scope_reply(locale)``.
OUT_OF_SCOPE_REPLY = assistant_message("planner.out_of_scope")


def out_of_scope_reply(locale: str = "vi") -> str:
    return assistant_message("planner.out_of_scope", locale)


def _out_of_scope_plan(locale: str = "vi") -> AgentPlan:
    return AgentPlan(
        agent="scope_guard",
        action="reply",
        status_code="responding",
        reply=out_of_scope_reply(locale),
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


def _strip_external_sources(text: str) -> str:
    cleaned = _EXTERNAL_SOURCE_RE.sub(" ", text)
    cleaned = re.sub(r"\b(on|trên|from|từ)\b", " ", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _reference_slice(text: str, *, kind: str) -> str:
    """Narrow ordinal parsing when a turn references both a job and a CV."""

    if kind == "cv":
        match = re.search(r"\b(cv|resume|hồ\s*sơ)\b", text, re.IGNORECASE)
        return text[match.start() : match.start() + 80] if match else text
    match = re.search(r"\b(job|việc|vị\s*trí|jd|role|position|thực\s*tập)\b", text, re.IGNORECASE)
    if not match:
        return text
    segment = text[match.start() : match.start() + 90]
    cv_marker = re.search(r"\b(cv|resume|hồ\s*sơ)\b", segment, re.IGNORECASE)
    if cv_marker and cv_marker.start() > 0:
        segment = segment[: cv_marker.start()]
    return segment


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
