"""Grounding helpers: turn structured CV/source data into evidence text.

The evidence corpus is the ONLY thing the fabrication check trusts. The free-text
user ``instruction`` is deliberately EXCLUDED from evidence (an injected
instruction must never be able to validate a fabricated fact); ``raw_notes`` IS
included because it is the student's own first-person evidence.

Matching uses term expansion (``app.ai.cv.term_expansion``) so that "k8s" and
"kubernetes" are treated as equivalent, and "ml" matches "machine learning" in
either direction. This is a pure in-memory lookup — no network, no model calls.
"""

from __future__ import annotations

import re

from app.ai.cv.term_expansion import expand_text, term_matches

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "you",
    "your",
    "are",
    "our",
    "this",
    "that",
    "will",
    "have",
    "has",
    "from",
    "into",
    "about",
    "must",
    "should",
    "able",
    "các",
    "và",
    "của",
    "cho",
    "với",
    "trong",
    "một",
    "được",
    "này",
    "là",
    "có",
    "khi",
    "đến",
    "theo",
    "như",
    "tại",
    "về",
    "hoặc",
    "những",
}


def section_texts(content: dict | None) -> list[str]:
    """Extract human-readable strings from a section ``content_json`` blob.

    Handles both content shapes: list/skill sections (``{"items": [...]}``) and
    the structured entry sections (``{"entries": [{heading, subheading, timeframe,
    location, note, highlights[]}]}``). Entry text MUST be flattened here or the
    experience/education evidence is lost from CV-JD matching + grounding.
    """

    if not isinstance(content, dict):
        return []
    out: list[str] = []
    items = content.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                if item.strip():
                    out.append(item.strip())
            elif isinstance(item, dict):
                parts = [
                    str(v).strip()
                    for v in item.values()
                    if isinstance(v, str | int | float) and str(v).strip()
                ]
                if parts:
                    out.append(" ".join(parts))
    entries = content.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_parts = [
                str(entry.get(key)).strip()
                for key in ("heading", "subheading", "timeframe", "location", "note")
                if isinstance(entry.get(key), str) and str(entry.get(key)).strip()
            ]
            highlights = entry.get("highlights")
            if isinstance(highlights, list):
                entry_parts.extend(
                    h.strip() for h in highlights if isinstance(h, str) and h.strip()
                )
            if entry_parts:
                out.append(" ".join(entry_parts))
    return out


def content_to_text(content: dict | None) -> str:
    return " ".join(section_texts(content))


def sections_to_text(sections: list[dict] | None) -> str:
    if not sections:
        return ""
    parts: list[str] = []
    for s in sections:
        title = s.get("title") or s.get("section_type") or ""
        parts.append(str(title))
        parts.append(content_to_text(s.get("content") or s.get("content_json")))
    return " ".join(p for p in parts if p)


def extracted_to_text(extracted: dict | None) -> str:
    """Flatten an uploaded-CV ``extracted_data`` blob to text."""

    if not isinstance(extracted, dict):
        return ""
    parts: list[str] = []
    for value in extracted.values():
        if isinstance(value, dict):
            parts.append(content_to_text(value))
            # contact-style dicts: {name,email,phone}
            parts.extend(str(v) for v in value.values() if isinstance(v, str) and v.strip())
    return " ".join(p for p in parts if p)


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace. Use :func:`normalize_expanded` for matching."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def normalize_expanded(text: str) -> str:
    """Normalize AND append all term expansion aliases.

    Use this when building the CV text representation for skill matching so that
    abbreviations in the CV (e.g. "k8s") are matched by their canonical forms
    (e.g. "kubernetes") that appear in the JD — and vice-versa.
    """
    return expand_text(text)


def term_present(term: str, text_norm_expanded: str) -> bool:
    """Return True when ``term`` or any known alias appears in ``text_norm_expanded``.

    Relies on :func:`term_matches` from ``term_expansion`` for alias lookup, so
    "k8s" matches "kubernetes", "ml" matches "machine learning", etc.
    """
    return term_matches(term, text_norm_expanded)


def extract_keywords(text: str, *, limit: int = 20) -> list[str]:
    tokens = re.findall(r"[a-zA-Zà-ỹÀ-Ỹ][\w+#.\-]{2,}", (text or "").lower())
    seen: list[str] = []
    for tok in tokens:
        tok = tok.strip(".-")
        if len(tok) < 3 or tok in _STOPWORDS or tok in seen:
            continue
        seen.append(tok)
        if len(seen) >= limit:
            break
    return seen


def keyword_coverage(keywords: list[str], cv_text: str) -> tuple[list[str], list[str]]:
    """Return ``(present, missing)`` keywords given the CV evidence text.

    Uses expansion-aware matching so "kubernetes" in a keyword matches "k8s"
    in the CV text (and vice-versa).
    """
    cv = normalize_expanded(cv_text)
    present = [k for k in keywords if term_present(k, cv)]
    missing = [k for k in keywords if not term_present(k, cv)]
    return present, missing
