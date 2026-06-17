"""CV parsing through the configured LLM with a deterministic fallback."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from backend.src.core.config import settings
from backend.src.models.schemas import StudentProfile, normalize_skill_name, student_from_dict
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
    "TypeScript",
    "C++",
    "C#",
]

SELF_RATING_LABELS = {
    "beginner": 3,
    "basic": 4,
    "familiar": 5,
    "intermediate": 6,
    "proficient": 7,
    "advanced": 8,
    "expert": 9,
    "co ban": 4,
    "cơ bản": 4,
    "trung cap": 6,
    "trung cấp": 6,
    "thanh thao": 8,
    "thành thạo": 8,
    "nang cao": 8,
    "nâng cao": 8,
    "chuyen gia": 9,
    "chuyên gia": 9,
}

SELF_RATING_BLOCKED_CANDIDATE_WORDS = {
    "gpa",
    "grade",
    "graduated",
    "ranking",
    "revenue",
    "score",
    "top",
}


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


def parse_cv_form(form: dict[str, Any], use_llm: bool = True) -> StudentProfile:
    return parse_cv_form_with_metadata(form, use_llm=use_llm).student


def parse_cv_form_with_metadata(form: dict[str, Any], use_llm: bool = True) -> CvParseResult:
    raw_text = _cv_form_to_text(form)
    result = parse_cv_text_with_metadata(raw_text, use_llm=use_llm)
    parsed = result.student
    metadata = dict(parsed.metadata)

    if form.get("name"):
        parsed.name = str(form["name"]).strip()
    for key in ["email", "phone", "major", "year"]:
        if form.get(key):
            metadata[key] = str(form[key]).strip()
    parsed.metadata = metadata
    return CvParseResult(student=parsed, raw_text=raw_text, metadata=result.metadata)


def cv_parse_metadata_to_dict(metadata: CvParseMetadata) -> dict[str, Any]:
    return {
        "parser_mode": metadata.parser_mode,
        "model": metadata.model,
        "api_key_configured": metadata.api_key_configured,
        "used_llm": metadata.used_llm,
        "fallback_used": metadata.fallback_used,
        "error": metadata.error,
    }


def _cv_form_to_text(form: dict[str, Any]) -> str:
    lines = []
    simple_fields = [
        ("name", "Name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("major", "Major"),
        ("year", "Year"),
        ("skills", "Skills"),
    ]
    for key, label in simple_fields:
        value = str(form.get(key, "")).strip()
        if value:
            lines.append(f"{label}: {value}")

    section_fields = [
        ("education", "Education"),
        ("projects", "Projects"),
        ("experience", "Experience"),
    ]
    for key, label in section_fields:
        value = str(form.get(key, "")).strip()
        if not value:
            continue
        lines.append(f"{label}:")
        lines.extend(line.strip() for line in value.splitlines() if line.strip())

    return "\n".join(lines)


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
      "evidence": ["short evidence phrase from the CV"],
      "self_rating": {{
        "value": number if the CV shows a self-rating,
        "scale": number such as 5, 10, or 100,
        "normalized_score": number from 0 to 10,
        "source": "stars/percent/bar/level/slash",
        "raw": "original short rating text"
      }}
    }}
  }},
  "metadata": {{
    "email": "email if present",
    "phone": "phone if present",
    "major": "major if present",
    "year": "year if present",
    "education": [],
    "projects": [],
    "experience": []
  }}
}}

Score skills conservatively. Use evidence from projects, coursework, work experience, or explicit skills.
If the CV uses self-rated skill stars, bars, percentages, or labels such as Beginner/Intermediate/Advanced, preserve that signal in self_rating. Do not treat self_rating alone as strong evidence.
Language rules:
- Write every natural-language value in Vietnamese.
- Keep established skill, tool, framework, and model names unchanged, for example Python, SQL, React, FastAPI, Docker, RAG, LLM.
- Do not translate JSON keys.

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
        metadata.pop("raw_text", None)
    return _merge_self_ratings(data, raw_text)


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

    data = {
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
            "parser_note": "Bộ phân tích dự phòng theo quy tắc; hãy kiểm tra JSON trước khi lưu.",
        },
    }
    return _merge_self_ratings(data, raw_text)


def _merge_self_ratings(data: dict[str, Any], raw_text: str) -> dict[str, Any]:
    detected = _detect_self_ratings(raw_text)
    if not detected:
        return data

    skills = data.setdefault("skills", {})
    if not isinstance(skills, dict):
        return data

    for skill_name, rating in detected.items():
        skill = skills.get(skill_name)
        evidence = f"Tự đánh giá trong CV: {rating['raw']}"
        capped_score = min(float(rating["normalized_score"]), 7.0)
        if isinstance(skill, dict):
            skill["self_rating"] = rating
            existing_evidence = skill.setdefault("evidence", [])
            if isinstance(existing_evidence, list) and evidence not in existing_evidence:
                existing_evidence.append(evidence)
        else:
            skills[skill_name] = {
                "score": capped_score,
                "confidence": 0.45,
                "evidence": [evidence],
                "self_rating": rating,
            }

    metadata = data.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["self_ratings_detected"] = sorted(detected)
        metadata["self_rating_note"] = (
            "Các mức sao/thanh/% là tự đánh giá của ứng viên; điểm matching vẫn nên được kiểm tra cùng bằng chứng dự án hoặc kinh nghiệm."
        )
    return data


def _detect_self_ratings(raw_text: str) -> dict[str, dict[str, Any]]:
    ratings: dict[str, dict[str, Any]] = {}
    for line in raw_text.splitlines():
        clean = " ".join(line.strip(" -\t").split())
        if not clean:
            continue
        extracted = _extract_rating_from_line(clean)
        if not extracted:
            continue
        skill_name = _infer_rated_skill(clean, extracted["raw"])
        if not skill_name:
            continue
        previous = ratings.get(skill_name)
        if previous and float(previous["normalized_score"]) >= float(extracted["normalized_score"]):
            continue
        ratings[skill_name] = extracted
    return ratings


def _extract_rating_from_line(line: str) -> dict[str, Any] | None:
    star_match = re.search(r"[★☆⭐]{2,5}", line)
    if star_match:
        token = star_match.group(0)
        filled = sum(1 for char in token if char in {"★", "⭐"})
        return _rating(filled, len(token), "stars", line)

    slash_match = re.search(r"(?<!\d)(10(?:\.0)?|[0-9](?:\.\d+)?)\s*/\s*(5|10)(?!\d)", line)
    if slash_match:
        value = float(slash_match.group(1))
        scale = float(slash_match.group(2))
        if 0 <= value <= scale:
            return _rating(value, scale, "slash", line)

    percent_match = re.search(r"(?<!\d)(100|[1-9]?\d)\s*%", line)
    if percent_match:
        return _rating(float(percent_match.group(1)), 100.0, "percent", line)

    bar_match = re.search(r"[█▓▒░■□▰▱▮▯●○]{3,12}", line)
    if bar_match:
        token = bar_match.group(0)
        empty = {"░", "□", "▱", "▯", "○"}
        filled = sum(1 for char in token if char not in empty)
        return _rating(filled, len(token), "bar", line)

    lowered = line.lower()
    for label, score in SELF_RATING_LABELS.items():
        if re.search(rf"\b{re.escape(label)}\b", lowered):
            return _rating(float(score), 10.0, "level", line)
    return None


def _rating(value: float, scale: float, source: str, raw: str) -> dict[str, Any]:
    normalized = 0.0 if scale <= 0 else round((value / scale) * 10, 2)
    return {
        "value": value,
        "scale": scale,
        "normalized_score": max(0.0, min(normalized, 10.0)),
        "source": source,
        "raw": raw[:160],
    }


def _infer_rated_skill(line: str, rating_raw: str) -> str | None:
    lowered = line.lower()
    for known_skill in sorted(CV_SKILLS, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9+#.]){re.escape(known_skill.lower())}(?![a-z0-9+#.])", lowered):
            return normalize_skill_name(known_skill)

    rating_index = _rating_index(line)
    before_rating = line[:rating_index].strip(" :-|•\t") if rating_index is not None else line.strip(" :-|•\t")
    before_rating = re.sub(r"^(skills?|technical skills?|kỹ năng|ky nang)\s*[:|-]\s*", "", before_rating, flags=re.IGNORECASE)
    candidate_words = re.findall(r"[A-Za-z0-9+#.]+", before_rating)
    if not candidate_words:
        return None
    candidate = " ".join(candidate_words[-3:]).strip()
    if not candidate or len(candidate) > 40:
        return None
    if any(word.lower() in SELF_RATING_BLOCKED_CANDIDATE_WORDS for word in candidate_words):
        return None
    return normalize_skill_name(candidate)


def _rating_index(line: str) -> int | None:
    patterns = [
        r"[★☆⭐]{2,5}",
        r"(?<!\d)(10(?:\.0)?|[0-9](?:\.\d+)?)\s*/\s*(5|10)(?!\d)",
        r"(?<!\d)(100|[1-9]?\d)\s*%",
        r"[█▓▒░■□▰▱▮▯●○]{3,12}",
    ]
    indices = [match.start() for pattern in patterns if (match := re.search(pattern, line))]
    lowered = line.lower()
    for label in SELF_RATING_LABELS:
        match = re.search(rf"\b{re.escape(label)}\b", lowered)
        if match:
            indices.append(match.start())
    return min(indices) if indices else None


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
    return evidence[:3] or [f"Tìm thấy từ khóa kỹ năng: {skill}"]
