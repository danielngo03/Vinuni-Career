"""User-facing response formatters for deterministic agent tool results.

Output text is localized via the ai_assistant message catalog; ``locale``
threads down from the request (Accept-Language) and defaults to ``vi`` so the
historical Vietnamese output stays byte-identical.
"""

from __future__ import annotations

from typing import Any

from app.modules.ai_assistant.application.agentic.models import AgentPlan
from app.modules.ai_assistant.application.messages import assistant_message


def format_tool_result(plan: AgentPlan, result: dict[str, Any], locale: str = "vi") -> str:
    """Format deterministic agent tool results into concise localized text."""
    if not result.get("ok"):
        return _tool_failure_reply(plan, result, locale)

    if plan.tool_name == "get_salary_benchmark":
        return _format_salary_result(
            result, role=str((plan.tool_args or {}).get("role") or "IT"), locale=locale
        )
    if plan.tool_name in {"search_jobs", "recommend_jobs", "get_saved_jobs", "get_partner_jobs"}:
        return _format_jobs_result(result, plan=plan, locale=locale)
    if plan.tool_name == "get_job_detail":
        return _format_job_detail_result(result, locale=locale)
    if plan.tool_name == "get_skill_gap":
        return _format_skill_gap_result(result, locale=locale)
    if plan.tool_name == "get_my_cvs":
        return _format_cvs_result(result, plan=plan, locale=locale)
    if plan.tool_name == "get_my_applications":
        return _format_applications_result(result, locale=locale)
    if plan.tool_name in {"search_events", "get_upcoming_events", "get_my_registered_events"}:
        registered = plan.tool_name == "get_my_registered_events"
        return _format_events_result(result, registered=registered, locale=locale)
    if plan.tool_name == "search_companies":
        return _format_companies_result(result, plan=plan, locale=locale)
    if plan.tool_name == "get_company_detail":
        return _format_company_detail_result(result, locale=locale)
    if plan.tool_name == "get_company_reviews":
        return _format_company_reviews_result(result, locale=locale)
    if plan.tool_name == "get_profile_status":
        return _format_profile_result(result, locale=locale)
    if plan.tool_name == "get_upcoming_interviews":
        return _format_interviews_result(result, locale=locale)
    if plan.tool_name == "get_job_alerts":
        return _format_alerts_result(result, locale=locale)
    if plan.tool_name == "get_partner_pipeline_summary":
        return _format_partner_pipeline_result(result, locale=locale)
    if plan.tool_name == "get_career_advice":
        return _format_career_advice_result(result, locale=locale)
    if plan.tool_name == "start_interview_sim":
        return _format_interview_sim_result(result, locale=locale)
    return assistant_message("fmt.tool.generic_ok", locale)


def _tool_failure_reply(plan: AgentPlan, result: dict[str, Any], locale: str) -> str:
    error = result.get("error")
    if error in {"missing_job_id", "invalid_job_id", "no_recent_job"}:
        return assistant_message("fmt.fail.no_specific_job", locale)
    if plan.tool_name == "recommend_jobs":
        return assistant_message("fmt.fail.recommend_jobs", locale)
    if plan.tool_name == "get_my_cvs":
        if plan.reason:
            return assistant_message("fmt.fail.cvs_with_reason", locale)
        return assistant_message("fmt.fail.cvs", locale)
    if plan.tool_name == "get_my_applications":
        return assistant_message("fmt.fail.applications", locale)
    if plan.tool_name == "get_skill_gap":
        return assistant_message("fmt.fail.skill_gap", locale)
    return assistant_message("fmt.fail.generic", locale)


def _format_salary_result(result: dict[str, Any], *, role: str, locale: str) -> str:
    tiers = result.get("tiers") or []
    if not tiers:
        note = result.get("note") or assistant_message("fmt.salary.no_benchmark", locale)
        search_url = result.get("search_url")
        return (
            assistant_message("fmt.salary.with_url", locale, note=note, search_url=search_url)
            if search_url
            else str(note)
        )
    lines = [
        assistant_message("fmt.salary.heading", locale, role=result.get("role") or role)
    ]
    for tier in tiers[:4]:
        lines.append(
            assistant_message(
                "fmt.salary.tier",
                locale,
                years=tier.get("years"),
                min=tier.get("min"),
                max=tier.get("max"),
                currency=result.get("currency"),
            )
        )
    lines.append(assistant_message("fmt.salary.footer", locale))
    return "\n".join(lines)


def _format_jobs_result(result: dict[str, Any], *, plan: AgentPlan, locale: str) -> str:
    jobs = result.get("recommendations") or result.get("jobs") or result.get("saved_jobs") or []
    if not jobs:
        return assistant_message("fmt.jobs.empty", locale)
    if plan.tool_name == "recommend_jobs":
        if _is_platform_only_reason(plan.reason):
            heading = assistant_message(
                "fmt.jobs.heading.recommend_platform_only", locale, reason=plan.reason
            )
        elif plan.reason:
            heading = assistant_message("fmt.jobs.heading.recommend_apply", locale)
        else:
            heading = assistant_message("fmt.jobs.heading.recommend", locale)
    elif plan.tool_name == "get_saved_jobs":
        heading = assistant_message("fmt.jobs.heading.saved", locale)
    elif plan.tool_name == "get_partner_jobs":
        heading = assistant_message("fmt.jobs.heading.partner", locale)
    else:
        if _is_platform_only_reason(plan.reason):
            heading = assistant_message(
                "fmt.jobs.heading.search_platform_only", locale, reason=plan.reason
            )
        else:
            heading = assistant_message("fmt.jobs.heading.search", locale)
    lines = [heading]
    title_fallback = assistant_message("fmt.jobs.item_title_fallback", locale)
    for index, item in enumerate(jobs[:5], start=1):
        company = item.get("company") or item.get("company_name") or ""
        lines.append(
            f"{index}. {item.get('title', title_fallback)} · {company} · "
            f"{item.get('url', '/jobs')}"
        )
    lines.append(assistant_message("fmt.jobs.footer", locale))
    return "\n".join(lines)


def _format_job_detail_result(result: dict[str, Any], *, locale: str) -> str:
    job = result.get("job") or {}
    title = job.get("title") or assistant_message("fmt.job_detail.title_fallback", locale)
    company = job.get("company") or ""
    lines = [f"{title} · {company}".strip(" ·")]
    if job.get("employment_type") or job.get("location_type"):
        lines.append(
            assistant_message(
                "fmt.job_detail.employment",
                locale,
                employment_type=job.get("employment_type", ""),
                location_type=job.get("location_type", ""),
            ).strip(" ·")
        )
    if job.get("salary_is_disclosed") and (job.get("salary_min") or job.get("salary_max")):
        lines.append(
            assistant_message(
                "fmt.job_detail.salary",
                locale,
                salary_min=job.get("salary_min") or "?",
                salary_max=job.get("salary_max") or "?",
                currency=job.get("salary_currency") or "",
            ).strip()
        )
    if job.get("required_skills"):
        lines.append(
            assistant_message(
                "fmt.job_detail.skills",
                locale,
                skills=", ".join(str(skill) for skill in job["required_skills"][:8]),
            )
        )
    if job.get("application_deadline"):
        lines.append(
            assistant_message(
                "fmt.job_detail.deadline", locale, deadline=job["application_deadline"]
            )
        )
    lines.append(assistant_message("fmt.job_detail.view", locale, url=job.get("url", "/jobs")))
    return "\n".join(lines)


def _format_skill_gap_result(result: dict[str, Any], *, locale: str) -> str:
    score = result.get("score", 0)
    job_fallback = assistant_message("fmt.skill_gap.job_fallback", locale)
    lines = [
        assistant_message(
            "fmt.skill_gap.heading",
            locale,
            cv_title=result.get("cv_title", "CV"),
            job_title=result.get("job_title", job_fallback),
            score=score,
        )
    ]
    matched = result.get("matched_skills") or []
    gaps = result.get("gaps") or []
    if matched:
        lines.append(
            assistant_message(
                "fmt.skill_gap.matched",
                locale,
                skills=", ".join(str(skill) for skill in matched[:8]),
            )
        )
    if gaps:
        lines.append(
            assistant_message(
                "fmt.skill_gap.gaps",
                locale,
                gaps=", ".join(str(gap) for gap in gaps[:8]),
            )
        )
    if result.get("url"):
        lines.append(assistant_message("fmt.skill_gap.view_jd", locale, url=result["url"]))
    return "\n".join(lines)


def _format_cvs_result(result: dict[str, Any], *, plan: AgentPlan, locale: str) -> str:
    cvs = result.get("cvs") or []
    if not cvs:
        if plan.reason:
            return assistant_message("fmt.cvs.empty_with_reason", locale)
        return assistant_message("fmt.cvs.empty", locale)
    total = result.get("total")
    if plan.reason:
        lines = [assistant_message("fmt.cvs.heading_with_reason", locale)]
    else:
        count_text = (
            assistant_message("fmt.cvs.count", locale, total=total) if total is not None else None
        )
        lines = [
            count_text or assistant_message("fmt.cvs.heading_no_count", locale),
            assistant_message("fmt.cvs.list_heading", locale),
        ]
    title_fallback = assistant_message("fmt.cvs.item_title_fallback", locale)
    for index, cv in enumerate(cvs[:5], start=1):
        lines.append(
            f"{index}. {cv.get('title', title_fallback)} · {cv.get('status', 'draft')}"
        )
    if plan.reason:
        lines.append(assistant_message("fmt.cvs.footer_with_reason", locale))
    return "\n".join(lines)


def _format_applications_result(result: dict[str, Any], *, locale: str) -> str:
    apps = result.get("applications") or []
    if not apps:
        return assistant_message("fmt.applications.empty", locale)
    lines = [assistant_message("fmt.applications.heading", locale)]
    job_fallback = assistant_message("fmt.applications.job_fallback", locale)
    for app in apps[:5]:
        lines.append(
            f"- {app.get('job_title', job_fallback)} · {app.get('company_name', '')} "
            f"· {app.get('status', 'submitted')}"
        )
    return "\n".join(lines)


def _format_events_result(result: dict[str, Any], *, registered: bool, locale: str) -> str:
    events = result.get("registered_events") if registered else result.get("events")
    events = events or []
    if not events:
        return assistant_message("fmt.events.empty", locale)
    lines = [
        assistant_message(
            "fmt.events.heading.registered" if registered else "fmt.events.heading.search",
            locale,
        )
    ]
    title_fallback = assistant_message("fmt.events.item_title_fallback", locale)
    for index, event in enumerate(events[:5], start=1):
        lines.append(
            f"{index}. {event.get('title', title_fallback)} · {event.get('starts_at', '')} "
            f"· {event.get('url', '/events')}"
        )
    return "\n".join(lines)


def _format_companies_result(result: dict[str, Any], *, plan: AgentPlan, locale: str) -> str:
    companies = result.get("companies") or []
    if not companies:
        if _is_platform_only_reason(plan.reason):
            return assistant_message(
                "fmt.companies.empty_platform_only", locale, reason=plan.reason
            )
        return assistant_message("fmt.companies.empty", locale)
    if _is_platform_only_reason(plan.reason):
        lines = [
            assistant_message("fmt.companies.heading_platform_only", locale, reason=plan.reason)
        ]
    else:
        lines = [assistant_message("fmt.companies.heading", locale)]
    name_fallback = assistant_message("fmt.companies.item_name_fallback", locale)
    for index, company in enumerate(companies[:5], start=1):
        open_roles = assistant_message(
            "fmt.companies.item_open_roles", locale, count=company.get("open_roles", 0)
        )
        lines.append(
            f"{index}. {company.get('name', name_fallback)} · {company.get('industry', '')} "
            f"· {open_roles} · {company.get('url', '/companies')}"
        )
    lines.append(assistant_message("fmt.companies.footer", locale))
    return "\n".join(lines)


def _is_platform_only_reason(reason: str | None) -> bool:
    return bool(reason and "không tra cứu internet" in reason.lower())


def _format_company_detail_result(result: dict[str, Any], *, locale: str) -> str:
    company = result.get("company") or {}
    company_name = company.get("name") or assistant_message(
        "fmt.company_detail.name_fallback", locale
    )
    lines = [str(company_name)]
    if company.get("industry") or company.get("size"):
        lines.append(
            assistant_message(
                "fmt.company_detail.industry_size",
                locale,
                industry=company.get("industry", ""),
                size=company.get("size", ""),
            ).strip(" ·")
        )
    if company.get("city"):
        lines.append(assistant_message("fmt.company_detail.hq", locale, city=company["city"]))
    if company.get("open_job_count") is not None:
        lines.append(
            assistant_message(
                "fmt.company_detail.open_roles", locale, count=company.get("open_job_count", 0)
            )
        )
    if company.get("rating"):
        lines.append(
            assistant_message(
                "fmt.company_detail.rating",
                locale,
                rating=company["rating"],
                review_count=company.get("review_count", 0),
            )
        )
    if company.get("description"):
        lines.append(str(company["description"]))
    if company.get("url"):
        lines.append(assistant_message("fmt.company_detail.page", locale, url=company["url"]))
    return "\n".join(lines)


def _format_company_reviews_result(result: dict[str, Any], *, locale: str) -> str:
    reviews = result.get("recent_reviews") or []
    rating = result.get("rating") or {}
    lines = [assistant_message("fmt.company_reviews.heading", locale)]
    if rating:
        lines.append(
            assistant_message(
                "fmt.company_reviews.overall",
                locale,
                overall_avg=rating.get("overall_avg"),
                review_count=rating.get("review_count", 0),
            )
        )
    if not reviews:
        lines.append(assistant_message("fmt.company_reviews.empty", locale))
    for review in reviews[:3]:
        lines.append(
            f"- {review.get('overall', '')}/5 · {review.get('summary') or review.get('pros') or ''}"
        )
    if result.get("url"):
        lines.append(assistant_message("fmt.company_reviews.view_more", locale, url=result["url"]))
    return "\n".join(lines)


def _format_profile_result(result: dict[str, Any], *, locale: str) -> str:
    # Identity-only profile (owner decision 2026-07-06): the only career signal is
    # ``is_open_to_work``; career detail lives in the student's CVs.
    if result.get("is_open_to_work"):
        return assistant_message("fmt.profile.open_to_work", locale)
    return assistant_message("fmt.profile.not_open_to_work", locale)


def _format_interviews_result(result: dict[str, Any], *, locale: str) -> str:
    interviews = result.get("interviews") or []
    if not interviews:
        return assistant_message("fmt.interviews.empty", locale)
    lines = [assistant_message("fmt.interviews.heading", locale)]
    job_fallback = assistant_message("fmt.interviews.job_fallback", locale)
    for interview in interviews[:5]:
        lines.append(
            f"- {interview.get('job_title', job_fallback)} · {interview.get('company_name', '')} "
            f"· {interview.get('scheduled_at', '')}"
        )
    return "\n".join(lines)


def _format_alerts_result(result: dict[str, Any], *, locale: str) -> str:
    alerts = result.get("alerts") or []
    if not alerts:
        return assistant_message("fmt.alerts.empty", locale)
    lines = [assistant_message("fmt.alerts.heading", locale)]
    name_fallback = assistant_message("fmt.alerts.item_name_fallback", locale)
    any_keyword = assistant_message("fmt.alerts.any_keyword", locale)
    for alert in alerts[:5]:
        lines.append(
            f"- {alert.get('name', name_fallback)} · {alert.get('keywords') or any_keyword}"
        )
    return "\n".join(lines)


def _format_partner_pipeline_result(result: dict[str, Any], *, locale: str) -> str:
    lines = [
        assistant_message(
            "fmt.partner_pipeline.heading",
            locale,
            active=result.get("total_active_candidates", 0),
            jobs=result.get("job_count", 0),
        )
    ]
    job_fallback = assistant_message("fmt.partner_pipeline.item_job_fallback", locale)
    for job in (result.get("jobs") or [])[:5]:
        lines.append(
            assistant_message(
                "fmt.partner_pipeline.item",
                locale,
                title=job.get("title", job_fallback),
                active=job.get("active_candidates", 0),
            )
        )
    return "\n".join(lines)


def _format_career_advice_result(result: dict[str, Any], *, locale: str) -> str:
    skills = result.get("key_skills") or []
    role_fallback = assistant_message("fmt.career.role_fallback", locale)
    fallback = assistant_message(
        "fmt.career.fallback_overview", locale, role=result.get("role", role_fallback)
    )
    lines = [str(result.get("overview") or fallback)]
    if skills:
        lines.append(
            assistant_message(
                "fmt.career.skills",
                locale,
                skills=", ".join(str(skill) for skill in skills[:6]),
            )
        )
    if result.get("growth_path"):
        lines.append(
            assistant_message("fmt.career.growth_path", locale, path=result["growth_path"])
        )
    if result.get("search_url"):
        lines.append(
            assistant_message("fmt.career.search_url", locale, url=result["search_url"])
        )
    return "\n".join(lines)


def _format_interview_sim_result(result: dict[str, Any], *, locale: str) -> str:
    question = result.get("opening_question") or result.get("question")
    tip = result.get("tip")
    if question:
        lines = [assistant_message("fmt.interview_sim.opening", locale, question=question)]
        if tip:
            lines.append(assistant_message("fmt.interview_sim.tip", locale, tip=tip))
        return "\n".join(lines)
    return assistant_message("fmt.interview_sim.unavailable", locale)
