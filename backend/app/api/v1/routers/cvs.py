from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.rbac import require_permission
from app.infra.database.models import CV, User
from app.infra.database.session import get_db
from app.schemas.cvs import (
    CVCreate,
    CVFormParseRequest,
    CVMaskRequest,
    CVMaskResponse,
    CVParseResponse,
    CVRawParseRequest,
    CVView,
)
from app.services.ai_service import mask_pii
from app.services.cv_service import create_cv, parse_cv_form, parse_cv_raw_text

router = APIRouter()
DEMO_DATA_DIR = Path(__file__).resolve().parents[4] / ".data" / "demo"
DEMO_STUDENTS_DIR = DEMO_DATA_DIR / "students"
DEMO_CVS_DIR = DEMO_DATA_DIR / "cvs"


@router.post("/mask", response_model=CVMaskResponse)
def mask_cv(
    payload: CVMaskRequest,
    _: User = Depends(require_permission("cv", "mask")),
) -> CVMaskResponse:
    masked_text, entities = mask_pii(payload.text)
    return CVMaskResponse(masked_text=masked_text, entities=entities)


@router.post("/parse/raw", response_model=CVParseResponse)
def parse_cv_from_raw_text(payload: CVRawParseRequest) -> CVParseResponse:
    return parse_cv_raw_text(payload.raw_text, student_id=payload.student_id)


@router.post("/parse/form", response_model=CVParseResponse)
def parse_cv_from_form(payload: CVFormParseRequest) -> CVParseResponse:
    return parse_cv_form(payload)


@router.post("/parse/upload", response_model=CVParseResponse)
async def parse_cv_from_upload(
    file: UploadFile = File(...),
    student_id: str | None = None,
) -> CVParseResponse:
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    return parse_cv_raw_text(text, student_id=student_id, source="upload")


@router.post("", response_model=CVView, status_code=201)
def create_student_cv(
    payload: CVCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> CV:
    return create_cv(db, payload)


@router.get("/demo/{student_id}", response_model=list[dict[str, Any]])
def list_demo_student_cvs(
    student_id: str,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _ensure_demo_cv_access(current_user, student_id)
    folder = DEMO_CVS_DIR / student_id
    if not folder.exists():
        return []
    cvs = [_read_json(path) for path in sorted(folder.glob("*.json"))]
    return sorted(cvs, key=lambda item: item.get("created_at", ""), reverse=True)


@router.post("/demo/{student_id}/parse/raw", response_model=CVParseResponse)
def parse_demo_student_cv(
    student_id: str,
    payload: CVRawParseRequest,
    current_user: User = Depends(get_current_user),
) -> CVParseResponse:
    _ensure_demo_cv_access(current_user, student_id)
    return parse_cv_raw_text(payload.raw_text, student_id=student_id)


@router.post("/demo/{student_id}", response_model=dict[str, Any], status_code=201)
def save_demo_student_cv(
    student_id: str,
    payload: CVCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_demo_cv_access(current_user, student_id)
    parsed_data = dict(payload.parsed_data)
    parsed_data["student_id"] = student_id
    raw_text = payload.raw_text or parsed_data.get("metadata", {}).get("cv_text_excerpt", "")
    parsed_data = _enrich_demo_cv_parsed_data(parsed_data, raw_text)
    cv = {
        "id": uuid.uuid4().hex,
        "student_id": student_id,
        "parsed_data": parsed_data,
        "raw_text": raw_text,
        "is_primary": payload.is_primary,
        "created_at": datetime.now(UTC).isoformat(),
    }
    folder = DEMO_CVS_DIR / student_id
    folder.mkdir(parents=True, exist_ok=True)
    if payload.is_primary:
        for path in folder.glob("*.json"):
            existing = _read_json(path)
            existing["is_primary"] = False
            _write_json(path, existing)
        _upsert_demo_student_from_cv(student_id, parsed_data)
    _write_json(folder / f"{cv['id']}.json", cv)
    return cv


@router.patch("/demo/{student_id}/{cv_id}", response_model=dict[str, Any])
def update_demo_student_cv(
    student_id: str,
    cv_id: str,
    payload: CVCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_demo_cv_access(current_user, student_id)
    path = DEMO_CVS_DIR / student_id / f"{cv_id}.json"
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found")

    existing = _read_json(path)
    parsed_data = dict(payload.parsed_data)
    parsed_data["student_id"] = student_id
    parsed_data = _enrich_demo_cv_parsed_data(parsed_data, payload.raw_text or existing.get("raw_text", ""))
    existing["parsed_data"] = parsed_data
    existing["raw_text"] = payload.raw_text or parsed_data.get("metadata", {}).get("cv_text_excerpt", "")
    existing["is_primary"] = payload.is_primary

    if payload.is_primary:
        folder = DEMO_CVS_DIR / student_id
        for sibling_path in folder.glob("*.json"):
            if sibling_path == path:
                continue
            sibling = _read_json(sibling_path)
            sibling["is_primary"] = False
            _write_json(sibling_path, sibling)
        _upsert_demo_student_from_cv(student_id, parsed_data)

    _write_json(path, existing)
    return existing


@router.post("/demo/{student_id}/{cv_id}/primary", response_model=dict[str, Any])
def set_demo_student_primary_cv(
    student_id: str,
    cv_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_demo_cv_access(current_user, student_id)
    folder = DEMO_CVS_DIR / student_id
    selected_path = folder / f"{cv_id}.json"
    if not selected_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found")

    selected_cv: dict[str, Any] | None = None
    for path in folder.glob("*.json"):
        cv = _read_json(path)
        cv["is_primary"] = path == selected_path
        _write_json(path, cv)
        if cv["is_primary"]:
            selected_cv = cv

    if selected_cv:
        selected_cv["parsed_data"] = _enrich_demo_cv_parsed_data(
            selected_cv.get("parsed_data", {}),
            selected_cv.get("raw_text", ""),
        )
        _write_json(selected_path, selected_cv)
        _upsert_demo_student_from_cv(student_id, selected_cv.get("parsed_data", {}))
        return selected_cv

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found")


@router.delete("/demo/{student_id}/{cv_id}", response_model=dict[str, str])
def delete_demo_student_cv(
    student_id: str,
    cv_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    _ensure_demo_cv_access(current_user, student_id)
    path = DEMO_CVS_DIR / student_id / f"{cv_id}.json"
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CV not found")

    cv = _read_json(path)
    if cv.get("is_primary"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete primary CV")

    path.unlink()
    return {"status": "deleted", "cv_id": cv_id}


def _ensure_demo_cv_access(user: User, student_id: str) -> None:
    if user.email.startswith("student_"):
        linked_id = _source_id_from_full_name(user.full_name) or user.email
        if linked_id != student_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _source_id_from_full_name(full_name: str) -> str | None:
    if not full_name.endswith(")"):
        return None
    marker = full_name.rfind("(")
    if marker == -1:
        return None
    return full_name[marker + 1 : -1]


def _upsert_demo_student_from_cv(student_id: str, parsed_data: dict[str, Any]) -> None:
    parsed_data = _enrich_demo_cv_parsed_data(parsed_data)
    existing_path = DEMO_STUDENTS_DIR / f"{student_id}.json"
    existing = _read_json(existing_path) if existing_path.exists() else {}
    profile = existing.get("profile", {})
    student = {
        "student_id": student_id,
        "name": profile.get("full_name")
        or existing.get("name")
        or parsed_data.get("name")
        or student_id,
        "skills": parsed_data.get("skills", {}),
        "target_position": parsed_data.get("target_position", ""),
        "work_experience": parsed_data.get("work_experience", []),
        "education": parsed_data.get("education", []),
        "profile_highlights": parsed_data.get("profile_highlights", {}),
        "metadata": parsed_data.get("metadata", {}),
        "profile": profile,
    }
    _write_json(DEMO_STUDENTS_DIR / f"{student_id}.json", student)


def _enrich_demo_cv_parsed_data(
    parsed_data: dict[str, Any],
    raw_text: str = "",
) -> dict[str, Any]:
    enriched = dict(parsed_data)
    enriched.setdefault("target_position", _infer_demo_target_position(enriched, raw_text))
    if not enriched.get("work_experience"):
        enriched["work_experience"] = _fallback_work_experience(enriched, raw_text)
    else:
        enriched["work_experience"] = [
            _score_work_experience_item(item, enriched, raw_text)
            for item in enriched.get("work_experience", [])
            if isinstance(item, dict)
        ]
    if not enriched.get("education"):
        enriched["education"] = _fallback_education(raw_text)
    else:
        enriched["education"] = [
            _score_education_item(item, raw_text)
            for item in enriched.get("education", [])
            if isinstance(item, dict)
        ]
    enriched["profile_highlights"] = _profile_highlights(enriched)
    return enriched


def _infer_demo_target_position(parsed_data: dict[str, Any], raw_text: str = "") -> str:
    existing = str(parsed_data.get("target_position") or "").strip()
    if existing:
        return existing
    legacy_name = str(parsed_data.get("name") or "").strip()
    if legacy_name.lower() not in {"", "not specified", "unknown", "demo student"}:
        return legacy_name

    skills = {skill.lower() for skill in parsed_data.get("skills", {})}
    lowered_text = raw_text.lower()
    if {"c#", "asp.net", "ado.net"} & skills or "asp.net" in lowered_text:
        return ".NET Developer"
    if {"electrical engineering", "systems engineering"} & skills:
        return "Electrical Engineer"
    if {"react", "javascript", "typescript"} & skills:
        return "Frontend Developer"
    if {"python", "fastapi", "django"} & skills:
        return "Backend Developer"
    if {"sql", "power bi", "excel", "tableau"} & skills:
        return "Data Analyst"
    if {"project management", "contract management"} & skills:
        return "Project Manager"
    return "General Candidate"


def _fallback_work_experience(parsed_data: dict[str, Any], raw_text: str = "") -> list[dict[str, str]]:
    skills = parsed_data.get("skills", {})
    if not skills:
        return []
    top_skills = sorted(
        skills.items(),
        key=lambda item: item[1].get("score", 0) if isinstance(item[1], dict) else 0,
        reverse=True,
    )[:4]
    skill_names = [skill.title() for skill, _ in top_skills]
    evidence = _first_skill_evidence(top_skills)
    summary = f"Demonstrated experience in {', '.join(skill_names)}."
    if evidence:
        summary = f"{summary} Evidence includes: {evidence}."
    return [
        _score_work_experience_item({
            "title": _infer_demo_target_position(parsed_data, raw_text),
            "company": "",
            "duration": "",
            "summary": summary[:500],
        }, parsed_data, raw_text)
    ]


def _fallback_education(raw_text: str = "") -> list[dict[str, str]]:
    if not raw_text:
        return []
    education_text = _education_section(raw_text)
    degree_match = re.search(
        r"(Bachelor|Master|PhD|Doctor|Associate|Diploma|Certificate)[^,\n|]{0,160}",
        education_text,
        flags=re.IGNORECASE,
    )
    institution_match = re.search(
        r"(?:University|College|Institute|School)\s+of\s+[A-Za-z ,.-]{2,80}|"
        r"[A-Z][A-Za-z ,.-]{2,80}\s+(?:University|College|Institute|School)",
        education_text,
    )
    year_match = re.search(r"(?:19|20)\d{2}", education_text)
    if not any((degree_match, institution_match, year_match)):
        return []
    return [
        _score_education_item(
            {
                "degree": degree_match.group(0).strip(" ,.-") if degree_match else "",
                "institution": institution_match.group(0).strip(" ,.-") if institution_match else "",
                "year": year_match.group(0) if year_match else "",
                "summary": "",
            },
            raw_text,
        )
    ]


def _score_work_experience_item(
    item: dict[str, Any],
    parsed_data: dict[str, Any],
    raw_text: str = "",
) -> dict[str, Any]:
    if item.get("score") and item.get("score_reason"):
        return item
    score = 4.0
    reasons = []
    if item.get("title"):
        score += 1.5
        reasons.append("clear role title")
    if item.get("company"):
        score += 1.0
        reasons.append("named company")
    if item.get("duration"):
        score += 0.8
        reasons.append("duration provided")
    if item.get("summary"):
        score += 1.0
        reasons.append("work summary available")
    if parsed_data.get("skills"):
        score += min(1.5, len(parsed_data["skills"]) * 0.3)
        reasons.append("supported by skill evidence")
    item["score"] = round(min(score, 10), 1)
    item["score_reason"] = (
        "Scored from " + ", ".join(reasons) + "."
        if reasons
        else "Limited structured experience detail available."
    )
    return item


def _profile_highlights(parsed_data: dict[str, Any]) -> dict[str, Any]:
    existing = parsed_data.get("profile_highlights")
    work_count = len(parsed_data.get("work_experience", []))
    education_count = len(parsed_data.get("education", []))
    skills = parsed_data.get("skills", {})
    default = {
        "work_experience_indexes": _top_item_indexes(parsed_data.get("work_experience", []), limit=2),
        "education_indexes": _top_item_indexes(parsed_data.get("education", []), limit=1),
        "skill_names": _top_skill_names(skills, limit=3),
    }
    if not isinstance(existing, dict):
        return default
    return {
        "work_experience_indexes": _valid_indexes(
            existing.get("work_experience_indexes"),
            work_count,
            limit=2,
        )
        or default["work_experience_indexes"],
        "education_indexes": _valid_indexes(
            existing.get("education_indexes"),
            education_count,
            limit=1,
        )
        or default["education_indexes"],
        "skill_names": _valid_skill_names(existing.get("skill_names"), skills, limit=3)
        or default["skill_names"],
    }


def _top_item_indexes(items: list[dict[str, Any]], *, limit: int) -> list[int]:
    scored = [
        (index, float(item.get("score", 0)) if isinstance(item, dict) else 0)
        for index, item in enumerate(items)
    ]
    return [index for index, _ in sorted(scored, key=lambda item: item[1], reverse=True)[:limit]]


def _top_skill_names(skills: dict[str, Any], *, limit: int) -> list[str]:
    return [
        skill
        for skill, _ in sorted(
            skills.items(),
            key=lambda item: item[1].get("score", 0) if isinstance(item[1], dict) else 0,
            reverse=True,
        )[:limit]
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


def _valid_skill_names(value: object, skills: dict[str, Any], *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    normalized = {skill.lower(): skill for skill in skills}
    for item in value:
        key = str(item).strip().lower()
        if key in normalized and normalized[key] not in names:
            names.append(normalized[key])
    return names[:limit]


def _score_education_item(item: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
    if item.get("score") and item.get("score_reason"):
        return item
    score = 3.5
    reasons = []
    degree = str(item.get("degree") or "").lower()
    if item.get("degree"):
        score += 1.5
        reasons.append("degree provided")
    if any(level in degree for level in ("master", "phd", "doctor")):
        score += 1.2
        reasons.append("advanced degree signal")
    elif "bachelor" in degree:
        score += 0.9
        reasons.append("bachelor degree signal")
    if item.get("institution"):
        score += 1.0
        reasons.append("institution provided")
    if item.get("year"):
        score += 0.6
        reasons.append("year provided")
    if item.get("summary"):
        score += 0.5
        reasons.append("education summary available")
    item["score"] = round(min(score, 10), 1)
    item["score_reason"] = (
        "Scored from " + ", ".join(reasons) + "."
        if reasons
        else "Limited structured education detail available."
    )
    return item


def _education_section(raw_text: str) -> str:
    match = re.search(
        r"education(?P<section>.*?)(?:professional training|certifications?|interests?|skills|experience|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match and match.group("section").strip():
        return match.group("section")
    return raw_text


def _first_skill_evidence(top_skills: list[tuple[str, Any]]) -> str:
    for _, detail in top_skills:
        if not isinstance(detail, dict):
            continue
        evidence = detail.get("evidence") or []
        if evidence:
            return str(evidence[0]).strip()[:180]
    return ""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
