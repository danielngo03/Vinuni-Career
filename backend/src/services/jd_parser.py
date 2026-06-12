"""JD parsing through Gemini with a deterministic fallback for local demos."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from backend.src.core.config import settings
from backend.src.models.schemas import JobRequirementProfile, job_from_dict
from backend.src.provider import LLMProvider, LLMProviderConfig, get_llm_provider
from backend.src.provider.gemini import GeminiProvider


DEFAULT_SKILLS = [
    "Python",
    "SQL",
    "Docker",
    "JavaScript",
    "React",
    "Machine Learning",
    "LLM",
    "Communication",
    "Documentation",
    "Dashboarding",
]


@dataclass(frozen=True)
class ParseMetadata:
    parser_mode: str
    model: str
    api_key_configured: bool
    used_llm: bool
    fallback_used: bool
    error: str | None = None


@dataclass(frozen=True)
class ParseResult:
    job: JobRequirementProfile
    metadata: ParseMetadata


def parse_jd_text(raw_text: str, company_id: str, use_llm: bool = True) -> JobRequirementProfile:
    return parse_jd_text_with_metadata(raw_text, company_id=company_id, use_llm=use_llm).job


def parse_jd_text_with_metadata(raw_text: str, company_id: str, use_llm: bool = True) -> ParseResult:
    try:
        provider = get_llm_provider()
    except Exception as exc:
        return ParseResult(
            job=job_from_dict(_fallback_parse(raw_text, company_id)),
            metadata=ParseMetadata(
                parser_mode="fallback",
                model=getattr(settings, "llm_model", "unknown"),
                api_key_configured=False,
                used_llm=False,
                fallback_used=True,
                error=str(exc) if use_llm else "LLM parsing disabled for this call.",
            ),
        )

    if use_llm and provider.is_configured:
        try:
            parsed = _parse_with_provider(raw_text, company_id, provider)
            return ParseResult(
                job=job_from_dict(parsed),
                metadata=ParseMetadata(
                    parser_mode=provider.name,
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=True,
                    fallback_used=False,
                ),
            )
        except Exception as exc:
            # Demo fallback keeps the module usable when the model or credentials fail.
            return ParseResult(
                job=job_from_dict(_fallback_parse(raw_text, company_id)),
                metadata=ParseMetadata(
                    parser_mode="fallback",
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=False,
                    fallback_used=True,
                    error=str(exc),
                ),
            )

    return ParseResult(
        job=job_from_dict(_fallback_parse(raw_text, company_id)),
        metadata=ParseMetadata(
            parser_mode="fallback",
            model=provider.model,
            api_key_configured=provider.is_configured,
            used_llm=False,
            fallback_used=True,
            error=None if use_llm else "LLM parsing disabled for this call.",
        ),
    )


def parse_jd_form(form: dict[str, Any], company_id: str, use_llm: bool = True) -> JobRequirementProfile:
    return parse_jd_form_with_metadata(form, company_id=company_id, use_llm=use_llm).job


def parse_jd_form_with_metadata(form: dict[str, Any], company_id: str, use_llm: bool = True) -> ParseResult:
    raw_text = "\n".join(f"{key}: {value}" for key, value in form.items() if value)
    result = parse_jd_text_with_metadata(raw_text, company_id=company_id, use_llm=use_llm)
    parsed = result.job
    if form.get("title"):
        parsed.title = str(form["title"])
    if form.get("location"):
        parsed.location = str(form["location"])
    if form.get("salary_range"):
        parsed.salary_range = str(form["salary_range"])
    return ParseResult(job=parsed, metadata=result.metadata)


def parse_metadata_to_dict(metadata: ParseMetadata) -> dict[str, Any]:
    return {
        "parser_mode": metadata.parser_mode,
        "model": metadata.model,
        "api_key_configured": metadata.api_key_configured,
        "used_llm": metadata.used_llm,
        "fallback_used": metadata.fallback_used,
        "error": metadata.error,
    }


def _build_parse_prompt(raw_text: str, company_id: str) -> str:
    prompt = f"""
Return only JSON for this job description. Required schema:
{{
  "job_id": "generated id",
  "company_id": "{company_id}",
  "title": "job title",
  "status": "draft",
  "employment_type": "internship/full-time/part-time/unspecified",
  "location": "location",
  "salary_range": "salary or unspecified",
  "benefits": ["benefit"],
  "skills": {{
    "Skill Name": {{
      "required_level": number from 1 to 10,
      "importance": number from 0 to 1,
      "required": boolean
    }}
  }}
}}

Job description:
{raw_text}
"""
    return prompt


def _parse_with_provider(raw_text: str, company_id: str, provider: LLMProvider) -> dict[str, Any]:
    text = provider.generate(_build_parse_prompt(raw_text, company_id))
    return _load_llm_json(text, raw_text, company_id)


def _parse_with_gemini(raw_text: str, company_id: str) -> dict[str, Any]:
    config = LLMProviderConfig(
        name="gemini",
        model=getattr(settings, "gemini_model", getattr(settings, "llm_model", "gemini-3.1-flash-lite")),
        temperature=getattr(settings, "llm_temperature", 0.0),
        api_key=getattr(settings, "gemini_api_key", getattr(settings, "google_api_key", None)),
    )
    return _parse_with_provider(raw_text, company_id, GeminiProvider(config))


def _load_llm_json(text: str, raw_text: str, company_id: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    data = json.loads(match.group(0))
    data["company_id"] = company_id
    data.setdefault("job_id", f"job_{uuid.uuid4().hex[:8]}")
    data.setdefault("status", "draft")
    data["raw_text"] = raw_text
    return data


def _fallback_parse(raw_text: str, company_id: str) -> dict[str, Any]:
    lowered = raw_text.lower()
    skills: dict[str, dict[str, Any]] = {}
    for skill in DEFAULT_SKILLS:
        if skill.lower() in lowered:
            skills[skill] = {
                "required_level": _infer_level(lowered, skill),
                "importance": _infer_importance(lowered, skill),
                "required": True,
            }

    if not skills:
        skills = {
            "Communication": {"required_level": 6, "importance": 0.7, "required": True},
            "Documentation": {"required_level": 5, "importance": 0.5, "required": False},
        }

    return {
        "job_id": f"job_{uuid.uuid4().hex[:8]}",
        "company_id": company_id,
        "title": _infer_title(raw_text),
        "status": "draft",
        "employment_type": "internship" if "intern" in lowered else "unspecified",
        "location": _infer_after_label(raw_text, "location") or "unspecified",
        "salary_range": _infer_after_label(raw_text, "salary") or "unspecified",
        "benefits": _infer_benefits(raw_text),
        "skills": skills,
        "raw_text": raw_text,
    }


def _infer_title(raw_text: str) -> str:
    for line in raw_text.splitlines():
        clean = line.strip(" -:#")
        if clean:
            if ":" in clean and len(clean.split(":", 1)[0]) < 20:
                maybe = clean.split(":", 1)[1].strip()
                if maybe:
                    return maybe[:80]
            return clean[:80]
    return "Untitled Job"


def _infer_after_label(raw_text: str, label: str) -> str | None:
    pattern = re.compile(rf"{label}\s*:\s*(.+)", re.IGNORECASE)
    match = pattern.search(raw_text)
    return match.group(1).strip() if match else None


def _infer_benefits(raw_text: str) -> list[str]:
    benefit_line = _infer_after_label(raw_text, "benefits")
    if not benefit_line:
        return []
    return [item.strip() for item in re.split(r",|;", benefit_line) if item.strip()]


def _infer_level(lowered: str, skill: str) -> int:
    context_required = any(word in lowered for word in ["senior", "advanced", "strong"])
    if context_required and skill.lower() in lowered:
        return 8
    if "basic" in lowered or "familiar" in lowered:
        return 5
    return 7


def _infer_importance(lowered: str, skill: str) -> float:
    if f"must have {skill.lower()}" in lowered or f"required {skill.lower()}" in lowered:
        return 0.9
    return 0.7
