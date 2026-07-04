"""Deterministic, non-AI structuring of extracted CV text into review fields.

This is the lightweight first pass (``docs/AI_PRODUCT_SPEC.md`` §19: "lightweight
local parsing first; OCR and LLM structuring are fallback steps"). It groups text
under recognised section headers and pulls contact details with simple regexes. It
NEVER invents content and produces no AI internals.

An optional structuring enhancer hook is exposed for the future ai-engineer slice
(``set_structuring_enhancer``): when wired, it may refine/augment the deterministic
result behind AI confirmation rules. By default it is unset and this module stays
fully deterministic.

Output shape matches ``docs/API_CONTRACTS.md`` CV Parse Status:
``extracted_data`` (structured fields) + ``review_fields`` (path/value/needs_review).
Only the owner-only parse-run endpoint ever surfaces these fields.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Section header -> canonical section_type. Vietnamese + English.
_HEADER_MAP: dict[str, str] = {
    "mục tiêu": "summary",
    "tóm tắt": "summary",
    "objective": "summary",
    "summary": "summary",
    "học vấn": "education",
    "education": "education",
    "kinh nghiệm": "experience",
    "experience": "experience",
    "work history": "experience",
    "dự án": "projects",
    "projects": "projects",
    "project": "projects",
    "kỹ năng": "skills",
    "skills": "skills",
    "chứng chỉ": "certifications",
    "certifications": "certifications",
    "certification": "certifications",
    "giải thưởng": "awards",
    "awards": "awards",
    "ngôn ngữ": "languages",
    "languages": "languages",
    "hoạt động": "activities",
    "activities": "activities",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_VI_DIACRITICS_RE = re.compile(
    "[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    "óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]"
)

# Optional AI enhancer: callable(text, deterministic_result) -> dict | None.
StructuringEnhancer = Callable[[str, dict], dict | None]
_enhancer: StructuringEnhancer | None = None


def set_structuring_enhancer(enhancer: StructuringEnhancer | None) -> None:
    """Wire an AI structuring enhancer (ai-engineer slice). Default unset."""

    global _enhancer
    _enhancer = enhancer


def _header_type(line: str) -> str | None:
    key = line.strip().lower().rstrip(":").strip()
    if len(key) > 40:
        return None
    return _HEADER_MAP.get(key)


def _detect_language(text: str) -> str:
    # Cheap heuristic: presence of Vietnamese diacritics -> vi, else en.
    if _VI_DIACRITICS_RE.search(text.lower()):
        return "vi"
    return "en"


def structure_cv_text(text: str) -> dict:
    """Group ``text`` into sections + contact and build review fields.

    Returns ``{"extracted_data": {...}, "review_fields": [...],
    "detected_language": "vi"|"en"}``. Deterministic; no AI.
    """

    lines = [ln.rstrip() for ln in text.splitlines()]
    sections: dict[str, list[str]] = {}
    current: str | None = None
    name = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        header = _header_type(line)
        if header is not None:
            current = header
            sections.setdefault(current, [])
            continue
        if not name and current is None and "@" not in line and not _PHONE_RE.search(line):
            # First non-empty, non-contact line before any header = likely the name.
            name = line
            continue
        if current is not None:
            sections[current].append(line)

    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    contact = {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
    }

    extracted: dict = {"contact": contact}
    review_fields: list[dict] = []

    # Contact review fields (name/email/phone flagged for review when missing).
    review_fields.append(
        {"path": "contact.name", "value": contact["name"], "needs_review": not contact["name"]}
    )
    review_fields.append(
        {"path": "contact.email", "value": contact["email"], "needs_review": not contact["email"]}
    )
    review_fields.append(
        {"path": "contact.phone", "value": contact["phone"], "needs_review": not contact["phone"]}
    )

    for section_type, items in sections.items():
        cleaned = [it.lstrip("-• \t") for it in items if it.strip()]
        extracted[section_type] = {"items": [{"text": it} for it in cleaned]}
        for idx, it in enumerate(cleaned):
            # A line ending with "?" or containing a lone year range marker is uncertain.
            uncertain = it.endswith("?") or "?" in it
            review_fields.append(
                {
                    "path": f"{section_type}[{idx}].text",
                    "value": it,
                    "needs_review": uncertain,
                }
            )

    result = {
        "extracted_data": extracted,
        "review_fields": review_fields,
        "detected_language": _detect_language(text),
    }

    if _enhancer is not None:
        enhanced = _enhancer(text, result)
        if enhanced is not None:
            return enhanced
    return result
