from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.infra.llm_gateway import ChatMessage, ChatRequest, get_llm_gateway
from app.infra.llm_gateway.errors import LLMGatewayError
from app.schemas.jobs import (
    JobEducationRequirements,
    JobExperienceRequirements,
    JobFormParseRequest,
    JobParsedSkill,
    JobParseResponse,
)
from app.services.ai_service import extract_skills

PROMPT_VERSION = "parse_jd_v1"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / f"{PROMPT_VERSION}.txt"


@dataclass(frozen=True)
class LLMParseAttempt:
    parsed: dict[str, object] | None
    provider: str | None
    model: str | None
    used: bool
    error_status_code: int | None = None
    error_code: str | None = None
    reason: str | None = None


def parse_jd_raw_text(
    raw_text: str,
    *,
    job_id: str | None = None,
    company_id: str | None = None,
    source: str = "raw_text",
) -> JobParseResponse:
    text = raw_text.strip()
    return _parse_text(text, job_id=job_id, company_id=company_id, source=source)


def parse_jd_form(payload: JobFormParseRequest) -> JobParseResponse:
    text = _form_to_text(payload)
    required = _normalize_skills(payload.required_skills)
    preferred = _normalize_skills(payload.preferred_skills)
    if not required and not preferred:
        return _parse_text(
            text,
            job_id=payload.job_id,
            company_id=payload.company_id,
            source="form",
        )

    return JobParseResponse(
        job_id=payload.job_id or _slug("job"),
        company_id=payload.company_id or "company_demo",
        title=payload.title.strip(),
        status="open",
        employment_type=payload.employment_type or _employment_type_from_text(text),
        location=payload.location or _location_from_text(text),
        salary_range=payload.salary_range or _salary_from_text(text),
        benefits=_clean_list(payload.benefits),
        skills=_job_skills(required, text, required=True)
        | _job_skills(preferred, text, required=False),
        experience_requirements=_experience_requirements_from_text(text),
        education_requirements=_education_requirements_from_text(text),
        raw_text=text,
        metadata=_parse_metadata("form", text, parser_mode="deterministic_form"),
    )


def _parse_text(
    text: str,
    *,
    job_id: str | None,
    company_id: str | None,
    source: str,
) -> JobParseResponse:
    llm_attempt = _try_parse_with_llm(text)
    if llm_attempt.used and llm_attempt.parsed:
        parsed = llm_attempt.parsed
        return JobParseResponse(
            job_id=job_id or _slug("job"),
            company_id=company_id or str(parsed.get("company_id") or "company_demo"),
            title=str(parsed.get("title") or _title_from_text(text)),
            status=str(parsed.get("status") or "open"),
            employment_type=_optional_str(parsed.get("employment_type"))
            or _employment_type_from_text(text),
            location=_optional_str(parsed.get("location")) or _location_from_text(text),
            salary_range=_optional_str(parsed.get("salary_range")) or _salary_from_text(text),
            benefits=_coerce_string_list(parsed.get("benefits")),
            skills=_coerce_llm_skills(parsed.get("skills"), text),
            experience_requirements=_coerce_experience_requirements(
                parsed.get("experience_requirements"),
                text,
            ),
            education_requirements=_coerce_education_requirements(
                parsed.get("education_requirements"),
                text,
            ),
            raw_text=text,
            metadata=_parse_metadata(
                source,
                text,
                parser_mode="llm_json",
                llm_used=True,
                provider=llm_attempt.provider,
                model=llm_attempt.model,
            ),
        )

    skills = extract_skills(text)
    return JobParseResponse(
        job_id=job_id or _slug("job"),
        company_id=company_id or "company_demo",
        title=_title_from_text(text),
        status="open",
        employment_type=_employment_type_from_text(text),
        location=_location_from_text(text),
        salary_range=_salary_from_text(text),
        benefits=_benefits_from_text(text),
        skills=_job_skills(skills, text, required=True),
        experience_requirements=_experience_requirements_from_text(text),
        education_requirements=_education_requirements_from_text(text),
        raw_text=text,
        metadata=_parse_metadata(
            source,
            text,
            parser_mode="deterministic_offline",
            fallback_used=True,
            error_status_code=llm_attempt.error_status_code,
            error_code=llm_attempt.error_code,
            fallback_reason=llm_attempt.reason,
            error=llm_attempt.reason,
        ),
    )


def _try_parse_with_llm(text: str) -> LLMParseAttempt:
    gateway = get_llm_gateway()
    if gateway.chat_chain == ["offline"] or not gateway.chat_chain:
        return LLMParseAttempt(
            parsed=None,
            provider=None,
            model=None,
            used=False,
            error_status_code=503,
            error_code="LLM_PROVIDER_CHAIN_OFFLINE_ONLY",
            reason="LLM provider chain is offline only. Configure LLM_PROVIDER_CHAIN with openai, gemini, or local to use a real model.",
        )

    try:
        response = gateway.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=PROMPT_PATH.read_text(encoding="utf-8")),
                    ChatMessage(role="user", content=text),
                ],
                temperature=0,
                max_tokens=1400,
                response_format={"type": "json_object"},
                metadata={"prompt_version": PROMPT_VERSION, "feature": "parse_jd"},
            )
        )
    except (LLMGatewayError, OSError):
        return LLMParseAttempt(
            parsed=None,
            provider=None,
            model=None,
            used=False,
            error_status_code=502,
            error_code="LLM_GATEWAY_FAILED",
            reason="LLM gateway failed before returning a response. Check API keys, base URLs, network, and provider configuration.",
        )

    if response.provider == "offline":
        return LLMParseAttempt(
            parsed=None,
            provider=response.provider,
            model=response.model,
            used=False,
            error_status_code=503,
            error_code="LLM_OFFLINE_FALLBACK_PROVIDER",
            reason="LLM gateway returned the offline fallback provider instead of a real model.",
        )

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        return LLMParseAttempt(
            parsed=None,
            provider=response.provider,
            model=response.model,
            used=False,
            error_status_code=502,
            error_code="LLM_INVALID_JSON",
            reason="LLM responded, but the response was not valid JSON.",
        )
    if not isinstance(parsed, dict):
        return LLMParseAttempt(
            parsed=None,
            provider=response.provider,
            model=response.model,
            used=False,
            error_status_code=502,
            error_code="LLM_JSON_NOT_OBJECT",
            reason="LLM responded with JSON, but the top-level value was not an object.",
        )
    return LLMParseAttempt(parsed=parsed, provider=response.provider, model=response.model, used=True)


def _form_to_text(payload: JobFormParseRequest) -> str:
    parts = [
        payload.title,
        payload.employment_type,
        payload.location,
        payload.salary_range,
        ", ".join(payload.benefits),
        ", ".join(payload.required_skills),
        ", ".join(payload.preferred_skills),
        payload.raw_notes,
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _title_from_text(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        return "Untitled Job"
    title = re.split(r"\.|\n| required skills?:", first, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return title[:255] or "Untitled Job"


def _employment_type_from_text(text: str) -> str:
    lowered = text.lower()
    if "intern" in lowered:
        return "Internship"
    if "part-time" in lowered or "part time" in lowered:
        return "Part-time"
    if "contract" in lowered or "freelance" in lowered:
        return "Contract"
    return "Full-time"


def _location_from_text(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    if "onsite" in lowered or "on-site" in lowered:
        return "On-site"
    return "Hybrid"


def _salary_from_text(text: str) -> str:
    match = re.search(r"(?i)(salary|compensation|pay)[:\s-]+([^\n.]+)", text)
    if match:
        return match.group(2).strip()[:255]
    if "competitive" in text.lower():
        return "Competitive"
    return "Competitive"


def _benefits_from_text(text: str) -> list[str]:
    lowered = text.lower()
    benefits: list[str] = []
    if "mentorship" in lowered or "mentor" in lowered:
        benefits.append("Mentorship")
    if "learning" in lowered or "training" in lowered:
        benefits.append("Project-based learning")
    return benefits


def _experience_requirements_from_text(text: str) -> JobExperienceRequirements:
    lowered = text.lower()
    explicit = bool(
        re.search(
            r"\b(experience|internship|portfolio|project experience|worked with|hands-on)\b",
            lowered,
        )
    )
    min_months = _months_from_text(text)
    required = bool(re.search(r"\b(required|must have|need)\b.{0,40}\bexperience\b", lowered))
    importance = 0.0
    if explicit:
        importance = 0.8 if required else 0.45
    if min_months:
        explicit = True
        importance = max(importance, 0.65)
    return JobExperienceRequirements(
        required=required,
        min_months=min_months,
        preferred_titles=_preferred_titles_from_text(text) if explicit else [],
        keywords=_experience_keywords_from_text(text),
        importance=importance,
    )


def _education_requirements_from_text(text: str) -> JobEducationRequirements:
    lowered = text.lower()
    fields = _fields_of_study_from_text(text)
    degrees = _degrees_from_text(text)
    certifications = _certifications_from_text(text)
    explicit = bool(fields or degrees or certifications)
    required = bool(
        re.search(
            r"\b(required|must have|need)\b.{0,60}\b(degree|student|graduate|certification|gpa)\b",
            lowered,
        )
    )
    importance = 0.0
    if explicit:
        importance = 0.8 if required else 0.5
    return JobEducationRequirements(
        required=required,
        degrees=degrees,
        fields_of_study=fields,
        certifications=certifications,
        keywords=_education_keywords_from_text(text),
        importance=importance,
    )


def _job_skills(
    skill_names: Iterable[str],
    text: str,
    *,
    required: bool,
) -> dict[str, JobParsedSkill]:
    normalized_skills = _normalize_skills(skill_names)
    if not normalized_skills:
        normalized_skills = ["communication", "documentation"]

    importance = 1.0 if required else 0.65
    return {
        skill: JobParsedSkill(
            required_level=_required_level(skill, text),
            importance=importance,
            required=required,
        )
        for skill in normalized_skills
    }


def _coerce_llm_skills(value: object, text: str) -> dict[str, JobParsedSkill]:
    if not isinstance(value, dict):
        return _job_skills(extract_skills(text), text, required=True)

    skills: dict[str, JobParsedSkill] = {}
    for raw_skill, raw_details in value.items():
        skill = str(raw_skill).strip().lower()
        if not skill:
            continue
        details = raw_details if isinstance(raw_details, dict) else {}
        required = bool(details.get("required", True))
        skills[skill] = JobParsedSkill(
            required_level=_clamp_float(
                details.get("required_level"),
                default=_required_level(skill, text),
                low=0,
                high=10,
            ),
            importance=_clamp_float(
                details.get("importance"),
                default=1.0 if required else 0.65,
                low=0,
                high=1,
            ),
            required=required,
        )
    return skills or _job_skills(extract_skills(text), text, required=True)


def _coerce_experience_requirements(value: object, text: str) -> JobExperienceRequirements:
    fallback = _experience_requirements_from_text(text)
    if not isinstance(value, dict):
        return fallback
    return JobExperienceRequirements(
        required=bool(value.get("required", fallback.required)),
        min_months=int(
            _clamp_float(
                value.get("min_months"),
                default=fallback.min_months,
                low=0,
                high=600,
            )
        ),
        preferred_titles=_coerce_string_list(value.get("preferred_titles")) or fallback.preferred_titles,
        keywords=_coerce_string_list(value.get("keywords")) or fallback.keywords,
        importance=_clamp_float(
            value.get("importance"),
            default=fallback.importance,
            low=0,
            high=1,
        ),
    )


def _coerce_education_requirements(value: object, text: str) -> JobEducationRequirements:
    fallback = _education_requirements_from_text(text)
    if not isinstance(value, dict):
        return fallback
    return JobEducationRequirements(
        required=bool(value.get("required", fallback.required)),
        degrees=_coerce_string_list(value.get("degrees")) or fallback.degrees,
        fields_of_study=(
            _coerce_string_list(value.get("fields_of_study"))
            or fallback.fields_of_study
        ),
        certifications=_coerce_string_list(value.get("certifications")) or fallback.certifications,
        keywords=_coerce_string_list(value.get("keywords")) or fallback.keywords,
        importance=_clamp_float(
            value.get("importance"),
            default=fallback.importance,
            low=0,
            high=1,
        ),
    )


def _months_from_text(text: str) -> int:
    match = re.search(r"(\d+)\s*\+?\s*(month|months|year|years|yr|yrs)\b", text, flags=re.IGNORECASE)
    if not match:
        return 0
    amount = int(match.group(1))
    unit = match.group(2).lower()
    return amount * 12 if unit.startswith(("year", "yr")) else amount


def _preferred_titles_from_text(text: str) -> list[str]:
    title = _title_from_text(text).lower()
    titles = [title] if title and title != "untitled job" else []
    lowered = text.lower()
    for keyword in ("frontend developer", "backend developer", "data analyst", "marketing assistant"):
        if keyword in lowered and keyword not in titles:
            titles.append(keyword)
    return titles[:5]


def _experience_keywords_from_text(text: str) -> list[str]:
    lowered = text.lower()
    keywords = []
    for keyword in (
        "internship",
        "project experience",
        "portfolio",
        "customer service",
        "web development",
        "data reporting",
        "hands-on",
    ):
        if keyword in lowered:
            keywords.append(keyword)
    if re.search(r"\bexperience\b", lowered):
        keywords.append("experience")
    return list(dict.fromkeys(keywords))[:8]


def _degrees_from_text(text: str) -> list[str]:
    lowered = text.lower()
    degrees = []
    for keyword in ("bachelor", "undergraduate student", "fresh graduate", "diploma", "certificate"):
        if keyword in lowered:
            degrees.append(keyword)
    if "student" in lowered and not degrees:
        degrees.append("student")
    return degrees[:6]


def _fields_of_study_from_text(text: str) -> list[str]:
    lowered = text.lower()
    fields = []
    for keyword in (
        "computer science",
        "software engineering",
        "information technology",
        "business administration",
        "marketing",
        "data science",
    ):
        if keyword in lowered:
            fields.append(keyword)
    return fields[:6]


def _certifications_from_text(text: str) -> list[str]:
    lowered = text.lower()
    certifications = []
    for keyword in ("aws", "google analytics", "excel certification", "pmp", "scrum"):
        if keyword in lowered:
            certifications.append(keyword)
    return certifications[:6]


def _education_keywords_from_text(text: str) -> list[str]:
    lowered = text.lower()
    keywords = []
    for keyword in ("final year student", "fresh graduate", "gpa", "coursework", "academic background"):
        if keyword in lowered:
            keywords.append(keyword)
    return keywords[:8]


def _normalize_skills(skill_names: Iterable[str]) -> list[str]:
    normalized = {
        re.sub(r"\s+", " ", skill.strip().lower())
        for skill in skill_names
        if skill and skill.strip()
    }
    return sorted(normalized)


def _required_level(skill: str, text: str) -> float:
    count = len(re.findall(re.escape(skill), text, flags=re.IGNORECASE))
    seniority_bonus = 1.0 if re.search(r"senior|lead|principal", text, flags=re.IGNORECASE) else 0.0
    intern_discount = -0.5 if re.search(r"intern|junior", text, flags=re.IGNORECASE) else 0.0
    return min(10.0, round(6.5 + max(count, 1) * 0.8 + seniority_bonus + intern_discount, 1))


def _clamp_float(value: object, *, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(min(high, max(low, number)), 2)


def _parse_metadata(
    source: str,
    text: str,
    *,
    parser_mode: str,
    llm_used: bool = False,
    fallback_used: bool = False,
    error_status_code: int | None = None,
    error_code: str | None = None,
    fallback_reason: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    error: str | None = None,
) -> dict[str, object]:
    gateway = get_llm_gateway()
    return {
        "source": source,
        "jd_text_excerpt": text[:6000],
        "parser_mode": parser_mode,
        "llm_used": llm_used,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "provider_chain": gateway.chat_chain,
        "provider": provider,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "error_status_code": error_status_code,
        "error_code": error_code,
        "error": error,
    }


def _clean_list(values: Iterable[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(prefix: str) -> str:
    return f"mock-{prefix}-{uuid.uuid4().hex[:8]}"
