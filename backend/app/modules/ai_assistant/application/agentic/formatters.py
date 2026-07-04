"""User-facing response formatters for deterministic agent tool results."""

from __future__ import annotations

from typing import Any

from app.modules.ai_assistant.application.agentic.models import AgentPlan


def format_tool_result(plan: AgentPlan, result: dict[str, Any]) -> str:
    """Format deterministic agent tool results into concise Vietnamese."""
    if not result.get("ok"):
        return _tool_failure_reply(plan, result)

    if plan.tool_name == "get_salary_benchmark":
        return _format_salary_result(result, role=str((plan.tool_args or {}).get("role") or "IT"))
    if plan.tool_name in {"search_jobs", "recommend_jobs", "get_saved_jobs", "get_partner_jobs"}:
        return _format_jobs_result(result, plan=plan)
    if plan.tool_name == "get_job_detail":
        return _format_job_detail_result(result)
    if plan.tool_name == "get_skill_gap":
        return _format_skill_gap_result(result)
    if plan.tool_name == "get_my_cvs":
        return _format_cvs_result(result, plan=plan)
    if plan.tool_name == "get_my_applications":
        return _format_applications_result(result)
    if plan.tool_name in {"search_events", "get_upcoming_events", "get_my_registered_events"}:
        registered = plan.tool_name == "get_my_registered_events"
        return _format_events_result(result, registered=registered)
    if plan.tool_name == "search_companies":
        return _format_companies_result(result, plan=plan)
    if plan.tool_name == "get_company_detail":
        return _format_company_detail_result(result)
    if plan.tool_name == "get_company_reviews":
        return _format_company_reviews_result(result)
    if plan.tool_name == "get_profile_status":
        return _format_profile_result(result)
    if plan.tool_name == "get_upcoming_interviews":
        return _format_interviews_result(result)
    if plan.tool_name == "get_job_alerts":
        return _format_alerts_result(result)
    if plan.tool_name == "get_partner_pipeline_summary":
        return _format_partner_pipeline_result(result)
    if plan.tool_name == "get_career_advice":
        return _format_career_advice_result(result)
    if plan.tool_name == "start_interview_sim":
        return _format_interview_sim_result(result)
    return "Mình đã tra cứu dữ liệu hệ thống và sẵn sàng hỗ trợ bước tiếp theo."


def _tool_failure_reply(plan: AgentPlan, result: dict[str, Any]) -> str:
    error = result.get("error")
    if error in {"missing_job_id", "invalid_job_id", "no_recent_job"}:
        return "Mình chưa xác định được job cụ thể. Bạn hãy mở/tìm job trước rồi nói “job đó” nhé."
    if plan.tool_name == "recommend_jobs":
        return (
            "Mình chưa tạo được gợi ý việc làm lúc này. "
            "Bạn có thể mở trang **Việc làm** để duyệt các tin mới."
        )
    if plan.tool_name == "get_my_cvs":
        if plan.reason:
            return (
                "Mình chưa tải được thư viện CV lúc này. Bạn hãy kiểm tra lại trong "
                "**CV Studio**; khi đã có CV, hãy chọn một JD/job cụ thể để hệ thống "
                "so CV, kỹ năng thiếu và keyword cần bổ sung."
            )
        return "Mình chưa tải được thư viện CV. Bạn thử mở **CV Studio** hoặc tải lại trang nhé."
    if plan.tool_name == "get_my_applications":
        return "Mình chưa tải được đơn ứng tuyển. Bạn có thể kiểm tra trong **Đơn ứng tuyển**."
    if plan.tool_name == "get_skill_gap":
        return (
            "Mình chưa phân tích được độ phù hợp. "
            "Hãy chắc chắn bạn đã có CV và job cụ thể trong hệ thống."
        )
    return "Mình chưa lấy được dữ liệu hệ thống lúc này. Vui lòng thử lại sau."


def _format_salary_result(result: dict[str, Any], *, role: str) -> str:
    tiers = result.get("tiers") or []
    if not tiers:
        note = result.get("note") or "Hiện chưa có benchmark lương đủ tin cậy cho vị trí này."
        search_url = result.get("search_url")
        return (
            f"{note}\nBạn có thể xem thêm tin đang mở tại {search_url}."
            if search_url
            else str(note)
        )
    lines = [f"Benchmark lương tham khảo cho {result.get('role') or role}:"]
    for tier in tiers[:4]:
        lines.append(
            f"- {tier.get('years')} năm kinh nghiệm: "
            f"{tier.get('min')}–{tier.get('max')} {result.get('currency')}"
        )
    lines.append("Đây là khoảng tham khảo; thực tế phụ thuộc công ty, level, kỹ năng và phỏng vấn.")
    return "\n".join(lines)


def _format_jobs_result(result: dict[str, Any], *, plan: AgentPlan) -> str:
    jobs = result.get("recommendations") or result.get("jobs") or result.get("saved_jobs") or []
    if not jobs:
        return (
            "Mình chưa thấy việc làm phù hợp trong dữ liệu hiện tại. "
            "Bạn có thể thử từ khóa khác trên trang **Việc làm**."
        )
    if plan.tool_name == "recommend_jobs":
        if _is_platform_only_reason(plan.reason):
            heading = f"{plan.reason}\nMình sẽ gợi ý việc làm bằng dữ liệu nội bộ:"
        elif plan.reason:
            heading = (
                "Bạn muốn ứng tuyển, nên mình cần chọn đúng vị trí trước. "
                "Một số việc làm phù hợp với hồ sơ của bạn:"
            )
        else:
            heading = "Một số việc làm phù hợp với hồ sơ của bạn:"
    elif plan.tool_name == "get_saved_jobs":
        heading = "Các việc làm bạn đã lưu:"
    elif plan.tool_name == "get_partner_jobs":
        heading = "Các job đang quản lý:"
    else:
        if _is_platform_only_reason(plan.reason):
            heading = f"{plan.reason}\nMình tìm thấy các việc làm trong hệ thống:"
        else:
            heading = "Mình tìm thấy các việc làm sau:"
    lines = [heading]
    for index, item in enumerate(jobs[:5], start=1):
        company = item.get("company") or item.get("company_name") or ""
        lines.append(
            f"{index}. {item.get('title', 'Vị trí tuyển dụng')} · {company} · "
            f"{item.get('url', '/jobs')}"
        )
    lines.append(
        "Bạn có thể nói “xem chi tiết job thứ 2”, “so CV với job đó”, "
        "hoặc “apply job thứ 2”."
    )
    return "\n".join(lines)


def _format_job_detail_result(result: dict[str, Any]) -> str:
    job = result.get("job") or {}
    title = job.get("title") or "Vị trí tuyển dụng"
    company = job.get("company") or ""
    lines = [f"{title} · {company}".strip(" ·")]
    if job.get("employment_type") or job.get("location_type"):
        lines.append(
            f"- Hình thức: {job.get('employment_type', '')} · {job.get('location_type', '')}".strip(
                " ·"
            )
        )
    if job.get("salary_is_disclosed") and (job.get("salary_min") or job.get("salary_max")):
        lines.append(
            f"- Lương: {job.get('salary_min') or '?'}–{job.get('salary_max') or '?'} "
            f"{job.get('salary_currency') or ''}".strip()
        )
    if job.get("required_skills"):
        lines.append(
            "- Kỹ năng chính: " + ", ".join(str(skill) for skill in job["required_skills"][:8])
        )
    if job.get("application_deadline"):
        lines.append(f"- Hạn ứng tuyển: {job['application_deadline']}")
    lines.append(f"Xem chi tiết: {job.get('url', '/jobs')}")
    return "\n".join(lines)


def _format_skill_gap_result(result: dict[str, Any]) -> str:
    score = result.get("score", 0)
    lines = [
        f"Độ phù hợp giữa CV **{result.get('cv_title', 'CV')}** và job "
        f"**{result.get('job_title', 'này')}**: {score}/100."
    ]
    matched = result.get("matched_skills") or []
    gaps = result.get("gaps") or []
    if matched:
        lines.append("Kỹ năng đã khớp: " + ", ".join(str(skill) for skill in matched[:8]) + ".")
    if gaps:
        lines.append("Nên bổ sung/tô rõ: " + ", ".join(str(gap) for gap in gaps[:8]) + ".")
    if result.get("url"):
        lines.append(f"Bạn có thể xem lại JD tại {result['url']}.")
    return "\n".join(lines)


def _format_cvs_result(result: dict[str, Any], *, plan: AgentPlan) -> str:
    cvs = result.get("cvs") or []
    if not cvs:
        if plan.reason:
            return (
                "Bạn chưa có CV nào trong hệ thống. Hãy upload CV vào **CV Studio** trước; "
                "sau đó chọn một JD/job cụ thể để mình phân tích độ phù hợp, kỹ năng thiếu "
                "và keyword nên bổ sung."
            )
        return (
            "Bạn chưa có CV nào trong hệ thống. "
            "Hãy vào **CV Studio** để upload CV hoặc tạo CV từ mẫu."
        )
    total = result.get("total")
    if plan.reason:
        lines = [
            "Mình đã tìm thấy CV của bạn. Để check CV thật chính xác, "
            "hãy chọn một JD/job cụ thể để hệ thống so kỹ năng, keyword và độ phù hợp."
        ]
    else:
        count_text = f"Bạn đang có {total} CV trong thư viện." if total is not None else None
        lines = [count_text or "CV hiện có trong thư viện của bạn:", "Danh sách CV hiện có:"]
    for index, cv in enumerate(cvs[:5], start=1):
        primary = " · CV chính" if cv.get("is_primary") else ""
        lines.append(
            f"{index}. {cv.get('title', 'Untitled CV')} · {cv.get('status', 'draft')}{primary}"
        )
    if plan.reason:
        lines.append("Bạn có thể hỏi: “CV này nên apply JD nào?” hoặc “so CV với job thứ 1”.")
    return "\n".join(lines)


def _format_applications_result(result: dict[str, Any]) -> str:
    apps = result.get("applications") or []
    if not apps:
        return (
            "Bạn chưa có đơn ứng tuyển nào. "
            "Khi ứng tuyển, trạng thái sẽ nằm trong **Đơn ứng tuyển**."
        )
    lines = ["Các đơn ứng tuyển gần đây của bạn:"]
    for app in apps[:5]:
        lines.append(
            f"- {app.get('job_title', 'Vị trí')} · {app.get('company_name', '')} "
            f"· {app.get('status', 'submitted')}"
        )
    return "\n".join(lines)


def _format_events_result(result: dict[str, Any], *, registered: bool) -> str:
    events = result.get("registered_events") if registered else result.get("events")
    events = events or []
    if not events:
        return "Mình chưa thấy sự kiện phù hợp. Bạn có thể xem thêm ở trang **Sự kiện**."
    lines = ["Sự kiện bạn đã đăng ký:" if registered else "Một số sự kiện phù hợp:"]
    for index, event in enumerate(events[:5], start=1):
        lines.append(
            f"{index}. {event.get('title', 'Sự kiện')} · {event.get('starts_at', '')} "
            f"· {event.get('url', '/events')}"
        )
    return "\n".join(lines)


def _format_companies_result(result: dict[str, Any], *, plan: AgentPlan) -> str:
    companies = result.get("companies") or []
    if not companies:
        if _is_platform_only_reason(plan.reason):
            return (
                f"{plan.reason}\nMình chưa tìm thấy công ty phù hợp trong dữ liệu nội bộ. "
                "Bạn có thể thử tên công ty khác trong trang **Công ty**."
            )
        return (
            "Mình chưa tìm thấy công ty phù hợp. "
            "Bạn có thể thử từ khóa khác trong trang **Công ty**."
        )
    if _is_platform_only_reason(plan.reason):
        lines = [f"{plan.reason}\nMột số công ty phù hợp trong hệ thống:"]
    else:
        lines = ["Một số công ty phù hợp:"]
    for index, company in enumerate(companies[:5], start=1):
        lines.append(
            f"{index}. {company.get('name', 'Công ty')} · {company.get('industry', '')} "
            f"· {company.get('open_roles', 0)} vị trí mở · {company.get('url', '/companies')}"
        )
    lines.append("Bạn có thể hỏi “review công ty thứ 1” hoặc “chi tiết công ty đó”.")
    return "\n".join(lines)


def _is_platform_only_reason(reason: str | None) -> bool:
    return bool(reason and "không tra cứu internet" in reason.lower())


def _format_company_detail_result(result: dict[str, Any]) -> str:
    company = result.get("company") or {}
    lines = [str(company.get("name") or "Thông tin công ty")]
    if company.get("industry") or company.get("size"):
        lines.append(
            f"- Ngành/quy mô: {company.get('industry', '')} · {company.get('size', '')}".strip(" ·")
        )
    if company.get("city"):
        lines.append(f"- Trụ sở: {company['city']}")
    if company.get("open_job_count") is not None:
        lines.append(f"- Vị trí đang mở: {company.get('open_job_count', 0)}")
    if company.get("rating"):
        lines.append(f"- Đánh giá: {company['rating']} ({company.get('review_count', 0)} review)")
    if company.get("description"):
        lines.append(str(company["description"]))
    if company.get("url"):
        lines.append(f"Trang công ty: {company['url']}")
    return "\n".join(lines)


def _format_company_reviews_result(result: dict[str, Any]) -> str:
    reviews = result.get("recent_reviews") or []
    rating = result.get("rating") or {}
    lines = ["Tóm tắt review công ty:"]
    if rating:
        lines.append(
            "- Điểm tổng quan: "
            f"{rating.get('overall_avg')} từ {rating.get('review_count', 0)} review"
        )
    if not reviews:
        lines.append("Chưa có review công khai đủ dữ liệu cho công ty này.")
    for review in reviews[:3]:
        lines.append(
            f"- {review.get('overall', '')}/5 · {review.get('summary') or review.get('pros') or ''}"
        )
    if result.get("url"):
        lines.append(f"Xem thêm: {result['url']}")
    return "\n".join(lines)


def _format_profile_result(result: dict[str, Any]) -> str:
    missing = result.get("missing_sections") or []
    base = f"Hồ sơ của bạn đang hoàn thiện khoảng {result.get('completion_pct', 0)}%."
    if missing:
        return (
            base
            + "\nNếu bạn đang chưa rõ hướng đi, bước đầu nên bổ sung: "
            + ", ".join(str(item) for item in missing[:5])
            + ". Sau đó mình có thể gợi ý việc làm phù hợp hơn từ hồ sơ/CV của bạn."
        )
    return (
        base
        + "\nHồ sơ đã khá đầy đủ. Bạn có thể hỏi “gợi ý job phù hợp” hoặc "
        "“so CV với job thứ 1” để đi tiếp."
    )


def _format_interviews_result(result: dict[str, Any]) -> str:
    interviews = result.get("interviews") or []
    if not interviews:
        return "Bạn chưa có lịch phỏng vấn sắp tới trong hệ thống."
    lines = ["Lịch phỏng vấn sắp tới:"]
    for interview in interviews[:5]:
        lines.append(
            f"- {interview.get('job_title', 'Vị trí')} · {interview.get('company_name', '')} "
            f"· {interview.get('scheduled_at', '')}"
        )
    return "\n".join(lines)


def _format_alerts_result(result: dict[str, Any]) -> str:
    alerts = result.get("alerts") or []
    if not alerts:
        return (
            "Bạn chưa có job alert nào. Hãy tạo alert ở **Thông báo việc làm** để nhận tin phù hợp."
        )
    lines = ["Job alerts đang bật:"]
    for alert in alerts[:5]:
        lines.append(f"- {alert.get('name', 'Alert')} · {alert.get('keywords') or 'mọi từ khóa'}")
    return "\n".join(lines)


def _format_partner_pipeline_result(result: dict[str, Any]) -> str:
    lines = [
        f"Pipeline hiện có {result.get('total_active_candidates', 0)} ứng viên đang active "
        f"trên {result.get('job_count', 0)} job."
    ]
    for job in (result.get("jobs") or [])[:5]:
        lines.append(f"- {job.get('title', 'Job')} · {job.get('active_candidates', 0)} active")
    return "\n".join(lines)


def _format_career_advice_result(result: dict[str, Any]) -> str:
    skills = result.get("key_skills") or []
    fallback = f"Lộ trình {result.get('role', 'nghề nghiệp')} đang có nhu cầu trên thị trường."
    lines = [str(result.get("overview") or fallback)]
    if skills:
        lines.append(f"Kỹ năng nên tập trung: {', '.join(str(skill) for skill in skills[:6])}.")
    if result.get("growth_path"):
        lines.append(f"Lộ trình thường gặp: {result['growth_path']}.")
    if result.get("search_url"):
        lines.append(f"Bạn có thể xem việc liên quan tại {result['search_url']}.")
    return "\n".join(lines)


def _format_interview_sim_result(result: dict[str, Any]) -> str:
    question = result.get("opening_question") or result.get("question")
    tip = result.get("tip")
    if question:
        lines = [f"Mình có thể bắt đầu luyện phỏng vấn với câu hỏi này:\n{question}"]
        if tip:
            lines.append(f"Gợi ý trả lời: {tip}")
        return "\n".join(lines)
    return (
        "Mình chưa tạo được phiên luyện phỏng vấn lúc này. "
        "Bạn thử nêu rõ role hoặc job muốn luyện nhé."
    )
