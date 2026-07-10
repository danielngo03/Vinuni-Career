"""Pure CV-text projection for the talent-pool index.

Turns a committed CV's structured matching representation (the
``cv_profiles.matching_json`` shape: ``{sections: [{section_type, title,
content}]}``) into the three signals the semantic index needs:

- ``content_text`` — a normalized, capped concatenation (summary + role/org lines
  + skill names + education) that is embedded AND used for the deterministic
  keyword fallback. Never surfaced raw to a partner.
- ``skills`` — lowercased skill names for deterministic skill filtering.
- ``experience_years`` — a coarse best-effort years estimate for the
  ``min_experience`` filter.

Deterministic, no OCR/AI. Tolerant of the several key spellings CV sections use
(``role``/``title``/``position``, ``organization``/``company``/``employer`` …).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

_MAX_CONTENT_CHARS = 4000
_MAX_SKILLS = 60

_SKILL_SECTION_HINTS = ("skill", "kỹ năng", "tech", "công nghệ", "tool")
_EXPERIENCE_HINTS = ("experience", "work", "employment", "kinh nghiệm", "project", "dự án")
_EDUCATION_HINTS = ("education", "học vấn", "degree", "academic")
_SUMMARY_HINTS = ("summary", "objective", "about", "profile", "giới thiệu", "mục tiêu")

# 4-digit years 1970..2099 (guards against parsing phone digits as years).
_YEAR_RE = re.compile(r"\b(19[7-9]\d|20[0-4]\d)\b")


def _content_of(section: dict) -> dict:
    raw = section.get("content")
    if not isinstance(raw, dict):
        raw = section.get("content_json")
    return raw if isinstance(raw, dict) else {}


def _items_of(content: dict) -> list:
    items = content.get("items")
    return items if isinstance(items, list) else []


def _first_str(item: dict, *keys: str) -> str:
    for key in keys:
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _section_kind(section: dict) -> str:
    stype = str(section.get("section_type") or "").lower()
    title = str(section.get("title") or "").lower()
    hay = f"{stype} {title}"
    if any(h in hay for h in _SKILL_SECTION_HINTS):
        return "skills"
    if any(h in hay for h in _EXPERIENCE_HINTS):
        return "experience"
    if any(h in hay for h in _EDUCATION_HINTS):
        return "education"
    if any(h in hay for h in _SUMMARY_HINTS):
        return "summary"
    return "other"


def _summary_text(content: dict) -> str:
    for key in ("text", "content", "body", "value", "summary"):
        val = content.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Some builders store the summary as a single-item list.
    for item in _items_of(content):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            t = _first_str(item, "text", "content", "value")
            if t:
                return t
    return ""


def _skill_names(content: dict) -> list[str]:
    names: list[str] = []
    for item in _items_of(content):
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            name = _first_str(item, "name", "title", "label", "skill")
            if name:
                names.append(name)
    # Some builders store a comma list under "text".
    if not names:
        blob = _summary_text(content)
        if blob:
            names.extend(p.strip() for p in re.split(r"[,;\n·]+", blob) if p.strip())
    return names


def _experience_lines(content: dict) -> tuple[list[str], list[str]]:
    """Return ``(display_lines, timeframe_strings)`` for the experience items."""

    lines: list[str] = []
    timeframes: list[str] = []
    for item in _items_of(content):
        if not isinstance(item, dict):
            if isinstance(item, str) and item.strip():
                lines.append(item.strip())
            continue
        role = _first_str(item, "role", "title", "position")
        org = _first_str(item, "organization", "company", "employer")
        timeframe = _first_str(item, "timeframe", "period", "dates", "duration")
        highlights = item.get("highlights")
        parts = [p for p in (role, org, timeframe) if p]
        if parts:
            lines.append(" · ".join(parts))
        if timeframe:
            timeframes.append(timeframe)
        if isinstance(highlights, list):
            for h in highlights:
                if isinstance(h, str) and h.strip():
                    lines.append(h.strip())
    return lines, timeframes


def _education_lines(content: dict) -> list[str]:
    lines: list[str] = []
    for item in _items_of(content):
        if isinstance(item, str) and item.strip():
            lines.append(item.strip())
        elif isinstance(item, dict):
            degree = _first_str(item, "degree", "qualification", "program")
            school = _first_str(item, "institution", "school", "university", "organization")
            field = _first_str(item, "field", "major")
            parts = [p for p in (degree, field, school) if p]
            if parts:
                lines.append(" · ".join(parts))
    return lines


def _estimate_years(timeframes: list[str], n_experience_entries: int) -> int | None:
    """Coarse years-of-experience estimate.

    Prefers the span between the earliest and latest 4-digit year seen across the
    experience timeframes; falls back to ~1 year per experience entry (capped).
    Returns ``None`` when there is no experience signal at all.
    """

    years: list[int] = []
    for tf in timeframes:
        years.extend(int(m) for m in _YEAR_RE.findall(tf))
    if years:
        this_year = datetime.now(tz=UTC).year
        latest = max(years)
        # An open-ended "2022 - present" range has only one year token; treat the
        # current year as the end so ongoing roles still count.
        if len([tf for tf in timeframes if _YEAR_RE.search(tf)]) and latest < this_year:
            span_end = latest
        else:
            span_end = this_year
        span = span_end - min(years)
        return max(0, min(span, 50))
    if n_experience_entries > 0:
        return min(n_experience_entries, 15)
    return None


def project_cv(sections: list[dict]) -> tuple[str, list[str], int | None]:
    """Project structured CV sections into ``(content_text, skills, years)``.

    Pure + deterministic. ``skills`` are lowercased + de-duplicated (order kept);
    ``content_text`` is capped at :data:`_MAX_CONTENT_CHARS`.
    """

    summary_parts: list[str] = []
    skill_names: list[str] = []
    experience_lines: list[str] = []
    education_lines: list[str] = []
    timeframes: list[str] = []
    n_experience_entries = 0

    for section in sections:
        if not isinstance(section, dict):
            continue
        content = _content_of(section)
        kind = _section_kind(section)
        if kind == "summary":
            t = _summary_text(content)
            if t:
                summary_parts.append(t)
        elif kind == "skills":
            skill_names.extend(_skill_names(content))
        elif kind == "experience":
            lines, tfs = _experience_lines(content)
            experience_lines.extend(lines)
            timeframes.extend(tfs)
            n_experience_entries += len(_items_of(content))
        elif kind == "education":
            education_lines.extend(_education_lines(content))

    # De-dup skills, preserve order, lowercase.
    seen: set[str] = set()
    skills: list[str] = []
    for name in skill_names:
        low = name.lower().strip()
        if low and low not in seen:
            seen.add(low)
            skills.append(low)
        if len(skills) >= _MAX_SKILLS:
            break

    text_parts: list[str] = []
    text_parts.extend(summary_parts)
    if skills:
        text_parts.append("Skills: " + ", ".join(skills))
    text_parts.extend(experience_lines)
    text_parts.extend(education_lines)
    content_text = "\n".join(p for p in text_parts if p).strip()[:_MAX_CONTENT_CHARS]

    years = _estimate_years(timeframes, n_experience_entries)
    return content_text, skills, years
