"""Language proficiency normalization to CEFR for CV-JD matching.

Converts diverse proficiency indicators to a CEFR level so cross-format
comparison works correctly:

    JD: "IELTS 6.5 or above"  → C B2
    CV: "APTIS B2"             → C B2  → MATCH ✓
    CV: "TOEFL iBT 85"        → C B2  → MATCH ✓
    CV: "TOEIC 800"            → C B2  → MATCH ✓
    CV: "Cambridge FCE"        → C B2  → MATCH ✓
    CV: "Fluent English"       → C B2  → MATCH ✓ (soft signal)
    CV: "IELTS 5.5"           → C B1  → GAP   ✗

Also normalises GPA scales (4.0 / 10.0 / letter / Vietnamese classification)
and Vietnamese degree/education naming so deterministic matching works without
any model call.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# ---------------------------------------------------------------------------
# 1. CEFR level ordering
# ---------------------------------------------------------------------------

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
_CEFR_ORDER: dict[str, int] = {lvl: i for i, lvl in enumerate(CEFR_LEVELS)}


def cefr_meets(achieved: str, required: str) -> bool:
    """Return True when ``achieved`` CEFR level >= ``required``."""
    return _CEFR_ORDER.get(achieved.upper(), -1) >= _CEFR_ORDER.get(required.upper(), 0)


# ---------------------------------------------------------------------------
# 2. IELTS score → CEFR  (Cambridge assessment framework)
# ---------------------------------------------------------------------------

def _ielts_to_cefr(score: float) -> str:
    if score >= 8.0:
        return "C2"
    if score >= 7.0:
        return "C1"
    if score >= 5.5:
        return "B2"
    if score >= 4.0:
        return "B1"
    if score >= 3.0:
        return "A2"
    return "A1"


# ---------------------------------------------------------------------------
# 3. TOEFL iBT score → CEFR
# ---------------------------------------------------------------------------

def _toefl_to_cefr(score: float) -> str:
    if score >= 95:
        return "C1"
    if score >= 72:
        return "B2"
    if score >= 43:
        return "B1"
    if score >= 18:
        return "A2"
    return "A1"


# ---------------------------------------------------------------------------
# 4. TOEIC (Listening+Reading total) → CEFR
# ---------------------------------------------------------------------------

def _toeic_to_cefr(score: float) -> str:
    if score >= 945:
        return "C1"
    if score >= 785:
        return "B2"
    if score >= 550:
        return "B1"
    if score >= 225:
        return "A2"
    return "A1"


# ---------------------------------------------------------------------------
# 5. PTE Academic → CEFR
# ---------------------------------------------------------------------------

def _pte_to_cefr(score: float) -> str:
    if score >= 76:
        return "C1"
    if score >= 59:
        return "B2"
    if score >= 43:
        return "B1"
    if score >= 30:
        return "A2"
    return "A1"


# ---------------------------------------------------------------------------
# 6. SAT/ACT reading – not used for CEFR; DUOLINGO English Test → CEFR
# ---------------------------------------------------------------------------

def _duolingo_to_cefr(score: float) -> str:
    if score >= 125:
        return "C1"
    if score >= 100:
        return "B2"
    if score >= 75:
        return "B1"
    if score >= 55:
        return "A2"
    return "A1"


# ---------------------------------------------------------------------------
# 7. VSTEP (Vietnam Standardized Test of English Proficiency) → CEFR
# ---------------------------------------------------------------------------

def _vstep_to_cefr(score: float) -> str:
    """VSTEP uses a 10-50 total score mapped directly to CEFR B1-C1."""
    if score >= 41:
        return "C1"
    if score >= 31:
        return "B2"
    if score >= 16:
        return "B1"
    return "A2"


# ---------------------------------------------------------------------------
# 8. Named exam / descriptor → CEFR  (no score, just name recognition)
# ---------------------------------------------------------------------------

_NAMED_EXAM_CEFR: dict[str, str] = {
    # Cambridge ESOL
    "cpe": "C2", "c2 proficiency": "C2",
    "cae": "C1", "c1 advanced": "C1",
    "fce": "B2", "b2 first": "B2", "cambridge b2": "B2",
    "pet": "B1", "b1 preliminary": "B1",
    "ket": "A2", "a2 key": "A2",
    # APTIS (British Council) — APTIS reports A/B/C bands directly as CEFR
    "aptis c": "C1", "aptis b2": "B2", "aptis b": "B2",
    "aptis b1": "B1", "aptis a": "A2",
    # DELF/DALF (French) — not English but shows CEFR awareness
    "dalf c2": "C2", "dalf c1": "C1",
    "delf b2": "B2", "delf b1": "B1", "delf a2": "A2", "delf a1": "A1",
    # JLPT (Japanese) — approximate CEFR mapping
    "jlpt n1": "C1", "jlpt n2": "B2", "jlpt n3": "B1",
    "jlpt n4": "A2", "jlpt n5": "A1",
    # HSK (Chinese)
    "hsk 6": "C1", "hsk 5": "B2", "hsk 4": "B1",
    "hsk 3": "A2", "hsk 2": "A1",
    # VSTEP named bands
    "vstep c1": "C1", "vstep b2": "B2", "vstep b1": "B1",
    # Verbal descriptors — soft signals (lowest CEFR for that label)
    "native": "C2", "native speaker": "C2", "bilingual": "C1",
    "mastery": "C2", "proficiency": "C1",
    "fluent": "C1", "fluently": "C1", "advanced": "C1",
    "upper intermediate": "B2", "upper-intermediate": "B2",
    "intermediate": "B1",
    "pre-intermediate": "A2", "pre intermediate": "A2",
    "elementary": "A2", "basic": "A1", "beginner": "A1",
    # Vietnamese descriptors
    "thành thạo": "C1", "lưu loát": "C1",
    "khá": "B1", "trung bình": "B1",
    "cơ bản": "A2",
}

# Direct CEFR band references
_CEFR_DIRECT_RE = re.compile(
    r"\b(c2|c1|b2|b1|a2|a1)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# 9. Regex extractors for scored tests
# ---------------------------------------------------------------------------

# Captures: (test_name, score)
_SCORED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ielts\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I), "ielts"),
    (re.compile(r"toefl(?:\s*ibt)?\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I),
     "toefl"),
    (re.compile(r"toeic\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I), "toeic"),
    (re.compile(r"pte(?:\s*academic)?\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I),
     "pte"),
    (re.compile(r"duolingo\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I), "duolingo"),
    (re.compile(r"vstep\s*(?:[:\-≥≤>=<]+\s*)?(?:từ\s*)?(\d+(?:\.\d+)?)", re.I), "vstep"),
]

_SCORE_FNS: dict[str, Callable[[float], str]] = {
    "ielts": _ielts_to_cefr,
    "toefl": _toefl_to_cefr,
    "toeic": _toeic_to_cefr,
    "pte": _pte_to_cefr,
    "duolingo": _duolingo_to_cefr,
    "vstep": _vstep_to_cefr,
}


# ---------------------------------------------------------------------------
# 10. Public API
# ---------------------------------------------------------------------------

def normalize_proficiency(text: str) -> str | None:
    """Extract and normalize a language proficiency claim to a CEFR level.

    Tries (in order):
    1. Named exam + score  (e.g. "IELTS 6.5", "TOEFL iBT 87")
    2. Direct CEFR band    (e.g. "B2", "C1")
    3. Named exam without score (e.g. "Cambridge FCE", "APTIS B2")
    4. Verbal descriptor   (e.g. "Fluent", "Intermediate")

    Returns the CEFR level string ("A1"–"C2") or None when no signal found.
    """
    if not text:
        return None
    t = text.strip().lower()

    # 1. Scored test
    for pattern, name in _SCORED_PATTERNS:
        m = pattern.search(t)
        if m:
            score = float(m.group(1).replace(",", "."))
            fn = _SCORE_FNS[name]
            return fn(score)  # type: ignore[call-arg]

    # 2. Direct CEFR band
    m = _CEFR_DIRECT_RE.search(t)
    if m:
        return m.group(1).upper()

    # 3. Named exam / descriptor (longest match first)
    for phrase in sorted(_NAMED_EXAM_CEFR, key=len, reverse=True):
        if phrase in t:
            return _NAMED_EXAM_CEFR[phrase]

    return None


def cefr_expansion_tokens(level: str) -> list[str]:
    """Return tokens for a CEFR level and all weaker equivalent test scores.

    Used to expand CV text so that "IELTS 7.0" in a CV matches a JD requirement
    phrased as "TOEFL 95" or "C1 English".
    """
    level = level.upper()
    idx = _CEFR_ORDER.get(level, -1)
    if idx < 0:
        return []
    levels_at_or_above = [CEFR_LEVELS[i] for i in range(idx, len(CEFR_LEVELS))]
    tokens: list[str] = []
    for lvl in levels_at_or_above:
        tokens.append(lvl.lower())
    return tokens


# ---------------------------------------------------------------------------
# 11. GPA scale normalisation
# ---------------------------------------------------------------------------

_GPA_LETTER: dict[str, float] = {
    "a+": 4.0, "a": 4.0, "a-": 3.7,
    "b+": 3.3, "b": 3.0, "b-": 2.7,
    "c+": 2.3, "c": 2.0, "c-": 1.7,
    "d+": 1.3, "d": 1.0, "f": 0.0,
}

_GPA_VI_CLASS: dict[str, tuple[float, float]] = {
    "xuất sắc": (3.9, 4.0),
    "giỏi": (3.5, 3.8),
    "khá": (3.0, 3.4),
    "trung bình khá": (2.5, 2.9),
    "trung bình": (2.0, 2.4),
    "yếu": (0.0, 1.9),
    # English equivalents
    "distinction": (3.8, 4.0),
    "merit": (3.3, 3.7),
    "pass": (2.0, 3.2),
    "high distinction": (3.9, 4.0),
    "credit": (3.0, 3.5),
}

_GPA_10_RE = re.compile(r"gpa\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*/\s*10", re.I)
_GPA_4_RE = re.compile(r"gpa\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*/\s*4", re.I)
_GPA_BARE_RE = re.compile(r"gpa\s*[:\-]?\s*(\d+(?:[.,]\d+)?)", re.I)
_GPA_LETTER_RE = re.compile(r"\bgpa\s*[:\-]?\s*([abcdf][+\-]?)\b", re.I)


def normalize_gpa_to_4(text: str) -> float | None:
    """Parse any GPA mention in *text* and return it on a 4.0 scale.

    Returns None when no GPA signal is found.
    """
    if not text:
        return None
    t = text.strip()

    # Letter grade GPA
    m = _GPA_LETTER_RE.search(t)
    if m:
        return _GPA_LETTER.get(m.group(1).lower())

    # /10 scale → /4
    m = _GPA_10_RE.search(t)
    if m:
        raw = float(m.group(1).replace(",", "."))
        return round(raw / 10 * 4, 2)

    # /4 scale
    m = _GPA_4_RE.search(t)
    if m:
        return float(m.group(1).replace(",", "."))

    # Bare number – only trust if it looks like a GPA
    m = _GPA_BARE_RE.search(t)
    if m:
        raw = float(m.group(1).replace(",", "."))
        if raw <= 4.0:
            return raw
        if raw <= 10.0:  # assume /10 scale
            return round(raw / 10 * 4, 2)

    # Vietnamese classification
    tl = t.lower()
    for label, (lo, hi) in _GPA_VI_CLASS.items():
        if label in tl:
            return (lo + hi) / 2

    return None


def gpa_meets(cv_text: str, required_gpa_4: float) -> bool | None:
    """Return True/False/None (True=meets, False=doesn't meet, None=no signal)."""
    gpa = normalize_gpa_to_4(cv_text)
    if gpa is None:
        return None
    return gpa >= required_gpa_4
