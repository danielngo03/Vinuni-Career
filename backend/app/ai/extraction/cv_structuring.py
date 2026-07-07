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
    # Summary / objective
    "mục tiêu": "summary",
    "mục tiêu nghề nghiệp": "summary",
    "tóm tắt": "summary",
    "giới thiệu bản thân": "summary",
    "giới thiệu": "summary",
    "objective": "summary",
    "career objective": "summary",
    "professional summary": "summary",
    "summary": "summary",
    "profile": "summary",
    "about": "summary",
    "about me": "summary",
    # Education
    "học vấn": "education",
    "trình độ học vấn": "education",
    "education": "education",
    "educational background": "education",
    "academic background": "education",
    "quá trình học tập": "education",
    # Experience
    "kinh nghiệm": "experience",
    "kinh nghiệm làm việc": "experience",
    "experience": "experience",
    "work experience": "experience",
    "work history": "experience",
    "professional experience": "experience",
    "employment history": "experience",
    "career history": "experience",
    "previous roles": "experience",
    "previous experience": "experience",
    "quá trình làm việc": "experience",
    "lịch sử công việc": "experience",
    "quá trình công tác": "experience",
    # Projects
    "dự án": "projects",
    "projects": "projects",
    "project": "projects",
    "personal projects": "projects",
    # Skills
    "kỹ năng": "skills",
    "kỹ năng chuyên môn": "skills",
    "skills": "skills",
    "technical skills": "skills",
    "core skills": "skills",
    "key skills": "skills",
    "competencies": "skills",
    "professional skills": "skills",
    "additional skills": "skills",
    "năng lực chuyên môn": "skills",
    "kỹ năng bổ sung": "skills",
    # Certifications
    "chứng chỉ": "certifications",
    "certifications": "certifications",
    "certification": "certifications",
    "licenses & certifications": "certifications",
    "licenses and certifications": "certifications",
    "chứng nhận": "certifications",
    # Awards
    "giải thưởng": "awards",
    "thành tích": "awards",
    "awards": "awards",
    "honors & awards": "awards",
    "honors and awards": "awards",
    "achievements": "awards",
    # Languages
    "ngôn ngữ": "languages",
    "ngoại ngữ": "languages",
    "languages": "languages",
    "language skills": "languages",
    # Activities
    "hoạt động": "activities",
    "hoạt động ngoại khóa": "activities",
    "activities": "activities",
    "extracurricular activities": "activities",
    "volunteer": "activities",
    "volunteering": "activities",
    "tình nguyện": "activities",
    # Publications
    "ấn phẩm": "publications",
    "công bố khoa học": "publications",
    "publications": "publications",
    "publication": "publications",
    "research": "publications",
    # Interests
    "sở thích": "interests",
    "interests": "interests",
    "hobbies": "interests",
    "hobbies & interests": "interests",
    # References
    "người tham chiếu": "references",
    "tham chiếu": "references",
    "references": "references",
    "reference": "references",
    "referees": "references",
}

# Canonical, de-duplicated section types (``_HEADER_MAP`` has many synonyms per
# type). Ordered for stable review-field output. Both the deterministic and the
# vision structuring paths iterate this so the review/import screen treats every
# extraction engine identically.
SECTION_TYPES: tuple[str, ...] = (
    "summary",
    "education",
    "experience",
    "projects",
    "skills",
    "certifications",
    "awards",
    "languages",
    "activities",
    "publications",
    "interests",
    "references",
)

# Email: stop at the end of the TLD — do not absorb trailing non-ASCII /
# punctuation that bleeds from adjacent text in poorly-extracted PDFs.
# The lookahead rejects any match followed immediately by a letter (ASCII or
# Unicode) that is NOT a valid email character.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.(?:[a-zA-Z]{2,})(?=[^a-zA-Z\w]|$)")

# Phone: at least 7 digits in the match, no pure date ranges (YYYY - YYYY),
# no cross-line spans. The character class uses a space/tab literal instead of
# \s so we never consume newlines and the match stays on one line.
_PHONE_RE = re.compile(
    r"(?<!\d)"  # not preceded by a digit
    r"(?!\d{4}[ \t]*[-–][ \t]*\d{4})"  # not a four-digit year range
    r"(?:\+?\d)"  # start: optional + then a digit
    r"(?=[^\n]*(?:\d[^\n]*){5,})"  # lookahead: at least 5 more digits on same line
    r"[\d \t().-]{7,}"  # body: digits + space/tab + common phone chars (no newline)
    r"\d"  # must end on a digit
)

_VI_DIACRITICS_RE = re.compile(
    "[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    "óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]"
)

# CV-title words that appear as the very first line on many templates instead of
# the candidate name. When the first non-empty line matches one of these, skip it
# and look at the next line.
_CV_TITLE_WORDS: frozenset[str] = frozenset(
    {
        "curriculum vitae",
        "cv",
        "resume",
        "résumé",
        "portfolio",
        "sơ yếu lý lịch",
        "hồ sơ xin việc",
        "hồ sơ",
        "học phần",
    }
)

# OCR-transliterated forms of Vietnamese section headers.  Tesseract often strips
# diacritics so "kinh nghiệm" → "kinh nghiêm" / "kinh nghiem", etc.  These are
# NOT added to _HEADER_MAP (which drives actual parsing) — only used to disqualify
# lines from being accepted as a person's name.
_OCR_SECTION_KEYWORDS: frozenset[str] = frozenset({
    "kinh nghiem", "kinh nghiêm",           # work experience
    "thong tin", "thong tin lien he",        # contact
    "hoc van", "hoc vân",                    # education
    "ky nang", "kỹ nang", "ky nang chuyen mon",  # skills
    "muc tieu", "muc tieu nghe nghiep",     # objective
    "hoat dong", "hoat dong ngoai khoa",    # activities
    "chung chi", "chung nhan",              # certifications
    "giai thuong", "thanh tich",            # awards
    "ngoai ngu", "ngon ngu",               # languages
    "so thich",                             # interests
    "tham chieu", "nguoi tham chieu",       # references
})

# Sentinel: a line that starts with one of these substrings is a section header
# even when _header_type() returns None (e.g. partial two-column merge like
# "Uông Kinh nghiệm làm việc"). Used to disqualify a line from being the name.
_SECTION_KEYWORDS: tuple[str, ...] = tuple(
    set(_HEADER_MAP.keys()) | _OCR_SECTION_KEYWORDS
)

# Garbage patterns that disqualify a line from being a name candidate.
_CID_RE = re.compile(r"\(cid:")  # PDF font-substitution artifacts
_SPACED_LETTER_RE = re.compile(r"^(?:[A-ZÀÁẢÃẠĂẮẶẲẴẤẦẨẪẬÂÊẾỀỆỂỄÔỐỒỘỔỖƠỚỜỞỠỢƯỨỪỬỮỰĐ] ){4,}")

# Optional AI enhancer: callable(text, deterministic_result) -> dict | None.
StructuringEnhancer = Callable[[str, dict], dict | None]
_enhancer: StructuringEnhancer | None = None


def set_structuring_enhancer(enhancer: StructuringEnhancer | None) -> None:
    """Wire an AI structuring enhancer (ai-engineer slice). Default unset."""

    global _enhancer
    _enhancer = enhancer


def _header_type(line: str) -> str | None:
    """Return the canonical section type for a header line, or None.

    Normalisation applied before lookup:
    1. Strip leading ordinal numbers and punctuation (e.g. "2. Work Experience").
    2. Lowercase.
    3. Strip trailing colon.
    This handles ALL-CAPS headers, numbered sections, and trailing colons.
    """

    cleaned = line.strip()
    # Strip leading "1." / "II." / "A." ordinal prefixes.
    cleaned = re.sub(r"^[IVXivx\d]+[.)]\s*", "", cleaned)
    key = cleaned.lower().rstrip(":").strip()
    if len(key) > 60:
        return None
    result = _HEADER_MAP.get(key)
    if result:
        return result
    # Handle bilingual slash-separated headers: "Work Experience / Kinh nghiệm"
    for sep in (" / ", "/"):
        if sep in key:
            for part in key.split(sep):
                result = _HEADER_MAP.get(part.strip())
                if result:
                    return result
    return None


def _contains_section_keyword(line: str) -> bool:
    """True when the line contains a known section-header keyword as a substring.

    Used to reject two-column-merge lines like "Uông Kinh nghiệm làm việc"
    (where the PDF flattened name + section header onto a single line) from being
    mistaken for the candidate name.
    """

    lowered = line.lower()
    return any(kw in lowered for kw in _SECTION_KEYWORDS)


def _is_name_candidate(line: str) -> bool:
    """Return True when a line is plausibly a person's name.

    Rejects:
    - Lines with ``(cid:`` font-substitution garbage.
    - Very long lines (> 60 chars — addresses / sentences).
    - Lines with fewer than 3 word characters (single-glyph OCR artifacts like
      "Ễ Ờ" or stray punctuation).
    - Lines whose stripped lowercase matches a CV-title word.
    - Lines that contain a known section-header keyword.
    - Lines that look like "Hello My Name Is …" or "My name is …".
    - Lines that are ALL-UPPERCASE ASCII without any Vietnamese diacritics — these
      are job titles ("CUSTOMER SERVICE"), section headers we missed, or company
      names. Vietnamese names are mixed-case and always carry diacritics when
      written correctly.
    - Lines that look like dates (e.g. "27/03/2003" or spaced "2 7 / 0 3 / 2 0 0 3").
    - Lines made of individual spaced letters ("T R A N B I N H") — accepted as
      a last resort since the spacing is a PDF font artifact and there is no
      better candidate (the vision tier will correct it in production).
    """

    stripped = line.strip()
    if not stripped:
        return False
    # Font-substitution garbage
    if _CID_RE.search(stripped):
        return False
    # Too long to be a name
    if len(stripped) > 60:
        return False
    # Too few word-class characters to form a name (rejects lone glyphs like "Ễ Ờ")
    word_chars = re.findall(r"\w", stripped)
    if len(word_chars) < 3:
        return False
    lower = stripped.lower()
    # Exact CV-title word match
    if lower.rstrip(":") in _CV_TITLE_WORDS:
        return False
    # Contains a section-header keyword (catches two-column merges)
    if _contains_section_keyword(stripped):
        return False
    # "Hello my name is" / "My name is" prefix
    if re.match(r"(?i)^(hello\s+)?my\s+name\s+is\b", stripped):
        return False
    # Date-looking line: "27/03/2003" or spaced "2 7 / 0 3 / 2 0 0 3"
    # Also rejects standalone year ranges like "2021 - 2025".
    digits_only = re.sub(r"[\s./\-]", "", stripped)
    if digits_only.isdigit() and len(digits_only) >= 4:
        return False
    # Lines that CONTAIN an embedded date pattern (e.g. "BH 12/11/2002",
    # "THỰC TẬP SINH 12/2023 - Nay") are DOB lines or time-framed role labels.
    if re.search(r"\b\d{1,2}/\d{2,4}\b", stripped):
        return False
    # URL lines: "https://..." or "www." prefix (spaced or not).
    no_spaces = stripped.replace(" ", "")
    if re.match(r"(?i)https?://|www\.", no_spaces):
        return False
    # URL fragment / query string continuation (e.g. spaced "e e e ? m i b e x t i d =")
    if re.search(r"[?=&]", no_spaces):
        return False
    # Address-like lines: contain a comma followed by text (e.g. "Ba Đình, Hà Nội",
    # "Quận 1, TP.HCM", "District A, Ho Chi Minh City"). Vietnamese names never
    # contain commas.
    if "," in stripped:
        return False
    # Spaced-letter fragment: every token is a single character and they are all
    # lowercase (e.g. "n h ó m"). A real name in this pattern ("T R A N") is all-caps
    # or mixed; an all-lowercase single-letter sequence is a paragraph fragment.
    tokens = stripped.split()
    if len(tokens) >= 3 and all(len(t) == 1 for t in tokens) and stripped == stripped.lower():
        return False
    # All-uppercase ASCII-only word (no Vietnamese diacritics) on its own = likely
    # a section header or job title ("CUSTOMER SERVICE", "WORK EXPERIENCE"). Real
    # Vietnamese names always carry diacritics; bare ASCII all-caps names like
    # "TA BICH" are still accepted because they contain no lowercase, but they
    # ARE plausible romanised names — only reject when there are NO alpha chars
    # with diacritics AND the line looks like an English job title / section header.
    # Heuristic: all words are uppercase ASCII-only (no diacritics) AND there are
    # multiple words (a single-word surname like "TA" or "LINH" is still valid).
    words = stripped.split()
    all_ascii_upper = all(
        w.isupper() and w.isascii() for w in words if w.isalpha()
    )
    has_vi_diacritics = bool(_VI_DIACRITICS_RE.search(stripped))
    if (
        all_ascii_upper
        and not has_vi_diacritics
        and len(words) >= 2
        # Distinguish "TA BICH" (2 tokens, could be a name) from "CUSTOMER SERVICE"
        # by checking whether the phrase appears verbatim in a job-title word list.
        # Simpler heuristic: if any word is a common English noun/verb, it's a title.
        and any(
            w.lower() in {
                "service", "services", "engineer", "manager", "director",
                "officer", "specialist", "analyst", "developer", "designer",
                "consultant", "coordinator", "executive", "intern", "assistant",
                "account", "sales", "marketing", "operations", "business",
                "customer", "support", "product", "senior", "junior", "lead",
            }
            for w in words
        )
    ):
        return False
    return True


def _detect_language(text: str) -> str:
    """Ratio-based language detection. Returns 'vi', 'en', or 'mixed'.

    For short texts (fewer than 8 alpha chars — individual field values,
    short phrases) a single Vietnamese diacritic is a reliable signal;
    the ratio threshold is not meaningful at very small scales.
    """

    if not text:
        return "en"
    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars == 0:
        return "en"
    vi_chars = len(_VI_DIACRITICS_RE.findall(text))
    # Short fragments: any diacritic -> vi (avoids false-negative from ratio floor).
    if alpha_chars < 8:
        return "vi" if vi_chars > 0 else "en"
    ratio = vi_chars / alpha_chars
    if ratio >= 0.10:
        return "vi"
    if ratio >= 0.03:
        return "mixed"
    return "en"


def review_fields_for_extracted(extracted: dict) -> list[dict]:
    """Build field-level review markers from an ``extracted_data`` dict.

    Emits exactly the paths the review/import step understands —
    ``contact.<name|email|phone>`` and ``<section_type>[<idx>].text`` — so a
    result produced by ANY structuring engine (deterministic, LLM-on-text, or
    vision) can flow through the same review screen and per-field override logic.
    A field is flagged ``needs_review`` only when it is empty/missing; the caller
    may additionally flag low-confidence items.
    """

    review_fields: list[dict] = []
    contact = extracted.get("contact")
    contact = contact if isinstance(contact, dict) else {}
    for field in ("name", "email", "phone"):
        value = str(contact.get(field) or "").strip()
        review_fields.append(
            {"path": f"contact.{field}", "value": value, "needs_review": not value}
        )
    for section_type in SECTION_TYPES:
        section = extracted.get(section_type)
        if not isinstance(section, dict):
            continue
        items = section.get("items")
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            text = item.get("text") if isinstance(item, dict) else item
            text = str(text or "").strip()
            review_fields.append(
                {"path": f"{section_type}[{idx}].text", "value": text, "needs_review": not text}
            )
    return review_fields


_LEADING_ARTIFACT_RE = re.compile(r"^[^\wÀ-ɏḀ-ỿ]+")
_CAPITAL_TOKEN_RE = re.compile(r"^[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝÞŸ"
                                r"ĂĐÊÔƠƯẮẶẲẴẤẦẨẪẬẾỀỂỄỆỐỒỔỖỘỚỜỞỠỢỨỪỬỮỰ"
                                r"ÀÁẢÃẠĂẮẶẲẴẤẦẨẪẬÂÊẾỀỆỂỄÔỐỒỘỔỖƠỚỜỞỠỢƯỨỪỬỮỰĐÝ]")


def _rescue_name_from_body(text: str) -> str:
    """Secondary name scan for two-column layout artifacts.

    pdfplumber column-merge can place the candidate name as an isolated line
    inside section body text (e.g. after the career-objective section header).
    Scan the first 3000 chars for a standalone, properly capitalised name line
    that the main pre-header pass missed.
    """
    for raw in text[:3000].splitlines():
        line = raw.strip()
        if not line or len(line) > 50:
            continue
        if line[0] in "•-*○→◆▪":
            continue
        if not _is_name_candidate(line):
            continue
        tokens = line.split()
        # All tokens must start with a capital letter (Unicode-aware).
        if all(_CAPITAL_TOKEN_RE.match(t) for t in tokens) and 2 <= len(tokens) <= 5:
            return line
    return ""


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
            # Take the first non-empty, non-contact line before any header as the
            # candidate name — but only when it passes the name-quality filter.
            # This rejects: CV title words ("Curriculum Vitae"), section-header
            # lines that appear before the first recognised header (e.g. "Mục tiêu
            # nghề nghiệp" on some templates), two-column-merge artifacts, CID
            # garbage, and common template filler ("Hello My Name Is").
            # Also require the first token to start with an uppercase letter so
            # mid-sentence OCR fragments like "chiến dịch vẽ …" are skipped.
            if _is_name_candidate(line):
                first_tok = line.split()[0] if line.split() else ""
                if _CAPITAL_TOKEN_RE.match(first_tok):
                    name = line
            continue
        if current is not None:
            sections[current].append(line)

    # Secondary scan: column-merge layouts place the name inside section body.
    if not name:
        name = _rescue_name_from_body(text)

    # Strip leading OCR/font artifacts (backtick, stray punctuation, etc.)
    if name:
        name = _LEADING_ARTIFACT_RE.sub("", name).strip()

    # Email: search full text, prefer the first plausible email address.
    email_match = _EMAIL_RE.search(text)
    # Phone: search full text; the regex already rejects year-range patterns.
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

    _lang = _detect_language(text)
    detected_language = "vi" if _lang in ("vi", "mixed") else "en"
    mixed_language = _lang == "mixed"
    result = {
        "extracted_data": extracted,
        "review_fields": review_fields,
        "detected_language": detected_language,
        "mixed_language": mixed_language,
    }

    if _enhancer is not None:
        enhanced = _enhancer(text, result)
        if enhanced is not None:
            return enhanced
    return result
