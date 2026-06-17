from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

from app.infra.llm_gateway import ChatMessage, ChatRequest, get_llm_gateway
from app.infra.llm_gateway.errors import LLMGatewayError
from app.schemas.cvs import CVFormParseRequest, CVParseResponse, CVParsedSkill
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
        name=payload.name.strip(),
        skills=_student_skills(skill_names, text),
        metadata=_parse_metadata("form", text, parser_mode="deterministic_form"),
    )


def _parse_text(text: str, *, student_id: str | None, source: str) -> CVParseResponse:
    llm_attempt = _try_parse_with_llm(text)
    if llm_attempt.used and llm_attempt.parsed:
        return CVParseResponse(
            student_id=student_id or _slug("student"),
            name=str(llm_attempt.parsed.get("name") or _name_from_text(text)),
            skills=_coerce_llm_skills(llm_attempt.parsed.get("skills"), text),
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
        name=_name_from_text(text),
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
                max_tokens=1200,
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
        payload.name,
        payload.education,
        payload.experience,
        payload.projects,
        ", ".join(payload.skills),
        payload.raw_notes,
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _name_from_text(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first and len(first.split()) <= 5 and not any(char.isdigit() for char in first):
        return first[:120]
    return "Demo Student"


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
        "cv_text_excerpt": text[:6000],
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
