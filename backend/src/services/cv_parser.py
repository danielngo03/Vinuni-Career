"""CV parsing through the configured LLM with a deterministic fallback."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from backend.src.core.config import settings
from backend.src.models.schemas import StudentProfile, student_from_dict
from backend.src.provider import LLMProvider, get_llm_provider


CV_SKILLS = [
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
    "FastAPI",
    "Streamlit",
    "Pandas",
    "Excel",
    "Git",
    "Data Analysis",
]


@dataclass(frozen=True)
class CvParseMetadata:
    parser_mode: str
    model: str
    api_key_configured: bool
    used_llm: bool
    fallback_used: bool
    error: str | None = None


@dataclass(frozen=True)
class CvParseResult:
    student: StudentProfile
    raw_text: str
    metadata: CvParseMetadata


def parse_cv_text(raw_text: str, use_llm: bool = True) -> StudentProfile:
    return parse_cv_text_with_metadata(raw_text, use_llm=use_llm).student


def parse_cv_text_with_metadata(raw_text: str, use_llm: bool = True) -> CvParseResult:
    try:
        provider = get_llm_provider()
    except Exception as exc:
        return CvParseResult(
            student=student_from_dict(_fallback_parse(raw_text)),
            raw_text=raw_text,
            metadata=CvParseMetadata(
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
            parsed = _parse_with_provider(raw_text, provider)
            return CvParseResult(
                student=student_from_dict(parsed),
                raw_text=raw_text,
                metadata=CvParseMetadata(
                    parser_mode=provider.name,
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=True,
                    fallback_used=False,
                ),
            )
        except Exception as exc:
            return CvParseResult(
                student=student_from_dict(_fallback_parse(raw_text)),
                raw_text=raw_text,
                metadata=CvParseMetadata(
                    parser_mode="fallback",
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=False,
                    fallback_used=True,
                    error=str(exc),
                ),
            )

    return CvParseResult(
        student=student_from_dict(_fallback_parse(raw_text)),
        raw_text=raw_text,
        metadata=CvParseMetadata(
            parser_mode="fallback",
            model=provider.model,
            api_key_configured=provider.is_configured,
            used_llm=False,
            fallback_used=True,
            error=None if use_llm else "LLM parsing disabled for this call.",
        ),
    )


def cv_parse_metadata_to_dict(metadata: CvParseMetadata) -> dict[str, Any]:
    return {
        "parser_mode": metadata.parser_mode,
        "model": metadata.model,
        "api_key_configured": metadata.api_key_configured,
        "used_llm": metadata.used_llm,
        "fallback_used": metadata.fallback_used,
        "error": metadata.error,
    }


def _build_parse_prompt(raw_text: str) -> str:
    return f"""
Return only JSON for this student CV. Required schema:
{{
  "student_id": "generated id",
  "name": "student name",
  "skills": {{
    "Skill Name": {{
      "score": number from 0 to 10,
      "confidence": number from 0 to 1,
      "evidence": ["short evidence phrase from the CV"]
    }}
  }},
  "metadata": {{
    "email": "email if present",
    "phone": "phone if present",
    "major": "major if present",
    "year": "year if present",
    "education": [],
    "projects": [],
    "experience": [],
    "raw_text": "original text"
  }}
}}

Score skills conservatively. Use evidence from projects, coursework, work experience, or explicit skills.

CV:
{raw_text}
"""


def _parse_with_provider(raw_text: str, provider: LLMProvider) -> dict[str, Any]:
    text = provider.generate(_build_parse_prompt(raw_text))
    return _load_llm_json(text, raw_text)


def _load_llm_json(text: str, raw_text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    data = json.loads(match.group(0))
    data.setdefault("student_id", f"student_{uuid.uuid4().hex[:8]}")
    metadata = data.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata.setdefault("raw_text", raw_text)
    return data


def _fallback_parse(raw_text: str) -> dict[str, Any]:
    lowered = raw_text.lower()
    skills: dict[str, dict[str, Any]] = {}
    for skill in CV_SKILLS:
        if skill.lower() in lowered:
            skills[skill] = {
                "score": _infer_score(lowered, skill),
                "confidence": _infer_confidence(lowered, skill),
                "evidence": _infer_evidence(raw_text, skill),
            }

    if not skills:
        skills = {
            "Communication": {
                "score": 5,
                "confidence": 0.45,
                "evidence": ["Fallback inferred general communication from CV text"],
            }
        }

    return {
        "student_id": f"student_{uuid.uuid4().hex[:8]}",
        "name": _infer_name(raw_text),
        "skills": skills,
        "metadata": {
            "email": _infer_email(raw_text),
            "phone": _infer_phone(raw_text),
            "major": _infer_labeled_value(raw_text, "major"),
            "year": _infer_labeled_value(raw_text, "year"),
            "education": _infer_section_lines(raw_text, "education"),
            "projects": _infer_section_lines(raw_text, "projects"),
            "experience": _infer_section_lines(raw_text, "experience"),
            "raw_text": raw_text,
            "parser_note": "Deterministic fallback parser; review JSON before saving.",
        },
    }


def _infer_name(raw_text: str) -> str:
    for line in raw_text.splitlines():
        clean = line.strip(" -:#\t")
        if clean and "@" not in clean and len(clean.split()) <= 5:
            return clean[:80]
    return "Unnamed Student"


def _infer_email(raw_text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", raw_text)
    return match.group(0) if match else None


def _infer_phone(raw_text: str) -> str | None:
    match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", raw_text)
    return " ".join(match.group(0).split()) if match else None


def _infer_labeled_value(raw_text: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*:\s*(.+)", raw_text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _infer_section_lines(raw_text: str, label: str) -> list[str]:
    lines = []
    capture = False
    for line in raw_text.splitlines():
        clean = line.strip(" -\t")
        if not clean:
            continue
        if clean.lower().rstrip(":") == label:
            capture = True
            continue
        if capture and re.match(r"^[A-Z][A-Za-z ]{2,}:$", clean):
            break
        if capture:
            lines.append(clean[:160])
    return lines[:6]


def _infer_score(lowered: str, skill: str) -> int:
    skill_lower = skill.lower()
    if any(word in lowered for word in [f"advanced {skill_lower}", f"strong {skill_lower}", f"expert {skill_lower}"]):
        return 8
    if any(word in lowered for word in [f"basic {skill_lower}", f"familiar with {skill_lower}"]):
        return 5
    if any(word in lowered for word in ["internship", "project", "built", "developed", "implemented"]):
        return 7
    return 6


def _infer_confidence(lowered: str, skill: str) -> float:
    skill_lower = skill.lower()
    if any(word in lowered for word in ["project", "experience", "internship", "built", "developed"]) and skill_lower in lowered:
        return 0.75
    return 0.55


def _infer_evidence(raw_text: str, skill: str) -> list[str]:
    evidence = []
    for line in raw_text.splitlines():
        clean = line.strip(" -\t")
        if skill.lower() in clean.lower():
            evidence.append(clean[:140])
    return evidence[:3] or [f"Skill keyword found: {skill}"]
