"""Lightweight JD language detection (no external ML deps).

Heuristic approach — fast, zero-dependency, good enough for the three main
cases in the Vietnamese hiring market: Vietnamese, English, and mixed.
"""

from __future__ import annotations

# Vietnamese-specific diacritical characters (tonal marks + vowel variants).
_VI_CHARS: frozenset[str] = frozenset(
    "àáâãèéêìíòóôõùúýăđơư"
    "ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ"
    "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯ"
    "ẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỶỸỴ"
)

# Hiragana + Katakana codepoint ranges
_JA_RANGES: tuple[tuple[int, int], ...] = ((0x3040, 0x309F), (0x30A0, 0x30FF))

_KO_LO, _KO_HI = 0xAC00, 0xD7A3   # Hangul syllables
_ZH_LO, _ZH_HI = 0x4E00, 0x9FFF   # CJK Unified Ideographs (main block)


def detect_language(text: str) -> str:
    """Return a BCP-47-ish language code for the dominant script in *text*.

    Returns:
        "vi"      — text is primarily Vietnamese
        "en"      — text is primarily Latin/English with no Vietnamese markers
        "mixed"   — text mixes Vietnamese and Latin scripts
        "ja"      — Japanese (hiragana/katakana dominant)
        "ko"      — Korean (Hangul dominant)
        "zh"      — Chinese (CJK ideographs dominant)
        "unknown" — text is too short or has no identifiable script markers
    """
    stripped = text.strip() if text else ""
    if len(stripped) < 20:
        return "unknown"

    # Count candidate characters (alpha + non-ASCII which covers all scripts)
    alpha = [c for c in stripped if c.isalpha() or ord(c) > 127]
    total = len(alpha)
    if total == 0:
        return "unknown"

    # CJK scripts — even a small ratio is highly distinctive
    ja_count = sum(1 for c in stripped if any(lo <= ord(c) <= hi for lo, hi in _JA_RANGES))
    ko_count = sum(1 for c in stripped if _KO_LO <= ord(c) <= _KO_HI)
    zh_count = sum(1 for c in stripped if _ZH_LO <= ord(c) <= _ZH_HI)

    if ja_count / total > 0.03:
        return "ja"
    if ko_count / total > 0.03:
        return "ko"
    if zh_count / total > 0.05:
        return "zh"

    vi_count = sum(1 for c in stripped if c in _VI_CHARS)
    vi_ratio = vi_count / total

    if vi_ratio > 0.08:
        return "vi"
    if vi_ratio > 0.02:
        return "mixed"
    return "en"


# Concrete languages we store as a JD's ``language_code`` (BCP-47-ish). "mixed"
# and "unknown" are resolved to a concrete dominant language below.
STORABLE_LANGUAGES: frozenset[str] = frozenset({"vi", "en", "ja", "ko", "zh"})


def resolve_original_language(*, hint: str | None, text: str) -> str:
    """Resolve the concrete ORIGINAL language to store for a JD.

    Order of trust:
    1. ``hint`` — the AI extraction's ``detected_language`` (image/text LLM,
       robust to Vietnamese JDs peppered with English technical terms) or a
       manual language chosen by the partner. Used when it is a concrete
       storable language.
    2. the zero-cost heuristic :func:`detect_language` over the JD text.

    A ``"mixed"`` result maps to ``"vi"`` — in the Vietnamese hiring market a
    mixed JD is overwhelmingly a Vietnamese posting with English tool/skill terms
    mixed in, and the original should read Vietnamese. ``"unknown"`` (too short /
    no markers) falls back to ``"en"``. The stored value drives the student-side
    "translate this JD" affordance, so it must be a concrete language, never
    "mixed"/"unknown".
    """
    if hint:
        normalized = hint.strip().lower()
        if normalized in STORABLE_LANGUAGES:
            return normalized
    code = detect_language(text or "")
    if code in STORABLE_LANGUAGES:
        return code
    if code == "mixed":
        return "vi"
    return "en"
