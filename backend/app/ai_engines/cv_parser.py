from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

from app.infra.llm_gateway import ChatMessage, ChatRequest, get_llm_gateway
from app.infra.llm_gateway.errors import LLMGatewayError
from app.schemas.cvs import (
    CVEducation,
    CVFormParseRequest,
    CVParseResponse,
    CVProfileHighlights,
    CVParsedSkill,
    CVWorkExperience,
)
from app.services.ai_service import extract_skills

PROMPT_VERSION = "parse_cv_v1"
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


def parse_cv_raw_text(
    raw_text: str,
    *,
    student_id: str | None = None,
    source: str = "raw_text",
) -> CVParseResponse:
    text = raw_text.strip()
    return _parse_text(text, student_id=student_id, source=source)


def parse_cv_form(payload: CVFormParseRequest) -> CVParseResponse:
    text = _form_to_text(payload)
    if not payload.skills:
        return _parse_text(text, student_id=payload.student_id, source="form")

    skill_names = _normalize_skills(payload.skills)
    return CVParseResponse(
        student_id=payload.student_id or _slug("student"),
        target_position=_form_target_position(payload),
        work_experience=_form_work_experience(payload),
        education=_form_education(payload),
        profile_highlights=_default_highlights(
            _form_work_experience(payload),
            _form_education(payload),
            _student_skills(skill_names, text),
        ),
        skills=_student_skills(skill_names, text),
        metadata=_parse_metadata("form", text, parser_mode="deterministic_form"),
    )


def _parse_text(text: str, *, student_id: str | None, source: str) -> CVParseResponse:
    llm_attempt = _try_parse_with_llm(text)
    if llm_attempt.used and llm_attempt.parsed:
        skills = _coerce_llm_skills(llm_attempt.parsed.get("skills"), text)
        work_experience = _coerce_work_experience(llm_attempt.parsed.get("work_experience"))
        education = _coerce_education(llm_attempt.parsed.get("education"))
        return CVParseResponse(
            student_id=student_id or _slug("student"),
            target_position=_target_position_from_parse(llm_attempt.parsed, text),
            work_experience=work_experience,
            education=education,
            profile_highlights=_coerce_profile_highlights(
                llm_attempt.parsed.get("profile_highlights"),
                work_experience,
                education,
                skills,
            ),
            skills=skills,
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
    return CVParseResponse(
        student_id=student_id or _slug("student"),
        target_position=_infer_target_position(text, skills),
        work_experience=[],
        education=[],
        profile_highlights=_default_highlights([], [], _student_skills(skills, text)),
        skills=_student_skills(skills, text),
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
                max_tokens=1800,
                response_format={"type": "json_object"},
                metadata={"prompt_version": PROMPT_VERSION, "feature": "parse_cv"},
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
    return LLMParseAttempt(
        parsed=parsed,
        provider=response.provider,
        model=response.model,
        used=True,
    )


def _form_to_text(payload: CVFormParseRequest) -> str:
    parts = [
        _form_target_position(payload),
        payload.education,
        payload.experience,
        payload.projects,
        ", ".join(payload.skills),
        payload.raw_notes,
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _form_target_position(payload: CVFormParseRequest) -> str:
    return (payload.target_position or payload.name or "General Candidate").strip()


def _form_work_experience(payload: CVFormParseRequest) -> list[CVWorkExperience]:
    if not payload.experience:
        return []
    summary = _compact_summary(payload.experience)
    return [
        CVWorkExperience(
            summary=summary,
            score=5.5,
            score_reason="User-provided experience text without structured company, duration, or impact details.",
        )
    ] if summary else []


def _form_education(payload: CVFormParseRequest) -> list[CVEducation]:
    if not payload.education:
        return []
    summary = _compact_summary(payload.education)
    return [
        CVEducation(
            summary=summary,
            score=5.5,
            score_reason="User-provided education text without structured institution or completion details.",
        )
    ] if summary else []


def _target_position_from_parse(parsed: dict[str, object], text: str) -> str:
    value = parsed.get("target_position") or parsed.get("position") or parsed.get("role")
    if isinstance(value, str) and _is_meaningful_position(value):
        return value.strip()[:120]
    return _infer_target_position(text, _coerce_llm_skills(parsed.get("skills"), text).keys())


def _coerce_work_experience(value: object) -> list[CVWorkExperience]:
    if not isinstance(value, list):
        return []

    experiences: list[CVWorkExperience] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        summary = _compact_summary(str(item.get("summary") or item.get("description") or ""))
        experiences.append(
            CVWorkExperience(
                title=str(item.get("title") or item.get("role") or "")[:160].strip(),
                company=str(item.get("company") or item.get("organization") or "")[:160].strip(),
                duration=str(item.get("duration") or item.get("dates") or "")[:120].strip(),
                summary=summary,
                score=_clamp_float(item.get("score"), default=0, low=0, high=10),
                score_reason=str(item.get("score_reason") or item.get("reason") or "")[:300].strip(),
            )
        )
    return [experience for experience in experiences if any(experience.model_dump().values())]


def _coerce_education(value: object) -> list[CVEducation]:
    if not isinstance(value, list):
        return []

    education: list[CVEducation] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        summary = _compact_summary(str(item.get("summary") or item.get("notes") or ""))
        education.append(
            CVEducation(
                degree=str(item.get("degree") or item.get("qualification") or "")[:180].strip(),
                institution=str(item.get("institution") or item.get("school") or "")[:180].strip(),
                year=str(item.get("year") or item.get("duration") or item.get("dates") or "")[:120].strip(),
                summary=summary,
                score=_clamp_float(item.get("score"), default=0, low=0, high=10),
                score_reason=str(item.get("score_reason") or item.get("reason") or "")[:300].strip(),
            )
        )
    return [item for item in education if any(item.model_dump().values())]


def _coerce_profile_highlights(
    value: object,
    work_experience: list[CVWorkExperience],
    education: list[CVEducation],
    skills: dict[str, CVParsedSkill],
) -> CVProfileHighlights:
    default = _default_highlights(work_experience, education, skills)
    if not isinstance(value, dict):
        return default

    work_indexes = _valid_indexes(value.get("work_experience_indexes"), len(work_experience), limit=2)
    education_indexes = _valid_indexes(value.get("education_indexes"), len(education), limit=1)
    skill_names = [
        str(skill).strip().lower()
        for skill in value.get("skill_names", [])
        if str(skill).strip().lower() in skills
    ][:3] if isinstance(value.get("skill_names"), list) else []
    return CVProfileHighlights(
        work_experience_indexes=work_indexes or default.work_experience_indexes,
        education_indexes=education_indexes or default.education_indexes,
        skill_names=skill_names or default.skill_names,
    )


def _default_highlights(
    work_experience: list[CVWorkExperience],
    education: list[CVEducation],
    skills: dict[str, CVParsedSkill],
) -> CVProfileHighlights:
    return CVProfileHighlights(
        work_experience_indexes=_top_indexes(work_experience, limit=2),
        education_indexes=_top_indexes(education, limit=1),
        skill_names=[
            skill
            for skill, _ in sorted(
                skills.items(),
                key=lambda item: item[1].score,
                reverse=True,
            )[:3]
        ],
    )


def _top_indexes(items: list[object], *, limit: int) -> list[int]:
    scored = [
        (index, float(getattr(item, "score", 0)))
        for index, item in enumerate(items)
    ]
    return [
        index
        for index, _ in sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
    ]


def _valid_indexes(value: object, count: int, *, limit: int) -> list[int]:
    if not isinstance(value, list):
        return []
    indexes = []
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < count and index not in indexes:
            indexes.append(index)
    return indexes[:limit]


def _compact_summary(value: str, *, max_chars: int = 260) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars].rsplit(' ', maxsplit=1)[0]}..."


def _is_meaningful_position(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    if not normalized or len(normalized.split()) > 10:
        return False
    if normalized.startswith(("my ", "i ")):
        return False
    return normalized not in {
        "not specified",
        "unknown",
        "n/a",
        "na",
        "none",
    }


def _infer_target_position(text: str, skill_names: Iterable[str]) -> str:
    normalized_text = text.lower()
    normalized_skills = {skill.lower() for skill in skill_names}

    explicit_patterns = [
        r"(?:target|objective|position|role|title)\s*[:\-]\s*([A-Za-z][A-Za-z0-9 .+#/&-]{2,80})",
        r"(?:seeking|applying for)\s+(?:a|an|the)?\s*([A-Za-z][A-Za-z0-9 .+#/&-]{2,80})",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and _is_meaningful_position(match.group(1)):
            return match.group(1).strip()[:120]

    if {"c#", "asp.net"} & normalized_skills or "asp.net" in normalized_text:
        return ".NET Developer"
    if {"react", "javascript", "typescript"} & normalized_skills:
        return "Frontend Developer"
    if {"python", "django", "fastapi"} & normalized_skills:
        return "Backend Developer"
    if {"sql", "power bi", "excel", "tableau"} & normalized_skills:
        return "Data Analyst"
    if {"project management", "stakeholder management"} & normalized_skills:
        return "Project Manager"
    return "General Candidate"


def _student_skills(skill_names: Iterable[str], text: str) -> dict[str, CVParsedSkill]:
    normalized_skills = _normalize_skills(skill_names)
    if not normalized_skills:
        normalized_skills = ["communication", "documentation", "python"]

    return {
        skill: CVParsedSkill(
            score=_skill_score(skill, text),
            confidence=0.82,
            evidence=[f"Detected from CV text: {skill}"],
        )
        for skill in normalized_skills
    }


def _coerce_llm_skills(value: object, text: str) -> dict[str, CVParsedSkill]:
    if not isinstance(value, dict):
        return _student_skills(extract_skills(text), text)

    skills: dict[str, CVParsedSkill] = {}
    for raw_skill, raw_details in value.items():
        skill = str(raw_skill).strip().lower()
        if not skill:
            continue
        details = raw_details if isinstance(raw_details, dict) else {}
        evidence = details.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [str(evidence)]
        skills[skill] = CVParsedSkill(
            score=_clamp_float(details.get("score"), default=_skill_score(skill, text), low=0, high=10),
            confidence=_clamp_float(details.get("confidence"), default=0.7, low=0, high=1),
            evidence=[str(item) for item in evidence[:4]] or [f"Detected from CV text: {skill}"],
        )
    return skills or _student_skills(extract_skills(text), text)


def _normalize_skills(skill_names: Iterable[str]) -> list[str]:
    normalized = {
        re.sub(r"\s+", " ", skill.strip().lower())
        for skill in skill_names
        if skill and skill.strip()
    }
    return sorted(normalized)


def _skill_score(skill: str, text: str) -> float:
    count = len(re.findall(re.escape(skill), text, flags=re.IGNORECASE))
    return min(10.0, round(6.5 + max(count, 1) * 0.8, 1))


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
        "cv_text_excerpt": _short_excerpt(text),
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


def _slug(prefix: str) -> str:
    return f"mock-{prefix}-{uuid.uuid4().hex[:8]}"


def _short_excerpt(text: str, *, max_chars: int = 420) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = " ".join(lines)
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars].rsplit(' ', maxsplit=1)[0]}..."
