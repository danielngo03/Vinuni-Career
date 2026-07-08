"""Adapter interfaces + shared signal types for the CV ingestion cascade.

Each extraction stage (native text, layout, OCR, structuring, optional LLM) is a
swappable adapter behind a small interface so the product logic in
``documents.application.ingestion_service`` never depends on a single parser
library (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3). Every adapter reports an
INTERNAL ``engine_family`` + ``engine_version`` that is persisted for diagnostics
but is **never** surfaced in any user-facing response (``.claude/rules/backend.md``).

Privacy: the LLM structuring adapter operates on extracted TEXT/markdown ONLY —
raw PDF/image bytes never reach it (``docs/SECURITY_PRIVACY.md`` AI Safety).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Below this many characters of native text we treat a PDF page set as having
# "too little readable text" and fall through to the OCR stage.
OCR_TRIGGER_THRESHOLD = 40

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9_]{20,}\.[A-Za-z0-9_]{20,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT-ish
    re.compile(r"sk-[A-Za-z0-9]{16,}"),  # provider-style secret keys
]


def redact_secrets(text: str) -> str:
    """Best-effort redaction of obvious secrets before any LLM call.

    Removes key=value secret pairs and token-shaped strings. This is a privacy
    guard, not a security boundary; the LLM stage is also disabled by default.
    """

    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


@dataclass(slots=True)
class ExtractionSignals:
    """Output of the text-producing stages (native / layout / OCR).

    ``engine_family`` / ``engine_version`` are INTERNAL diagnostics only.
    """

    text: str = ""
    page_count: int = 0
    engine_family: str = "none"
    engine_version: str = "none"
    has_images: bool = False
    ocr_used: bool = False
    ocr_unavailable: bool = False
    layout_used: bool = False
    disordered: bool = False
    warnings: list[str] = field(default_factory=list)


_CID_RE = re.compile(r"\(cid:\d+\)")
_SPACED_WORD_RE = re.compile(r"\b[A-Za-zÀ-ỹ]\s[A-Za-zÀ-ỹ]\s[A-Za-zÀ-ỹ]")


def is_cid_corrupted(text: str) -> bool:
    """Heuristic: native-extracted text is dominated by CID font garbage.

    CID-encoded PDFs produce either literal ``(cid:N)`` sequences or words with
    spaces inserted between every letter ("E N G I N E E R").  Either pattern
    makes the text useless for structuring and signals that the vision-LLM tier
    should be used instead, even when ``len(text) > OCR_TRIGGER_THRESHOLD``.

    Returns True when either:
    - More than 5 % of non-whitespace characters are inside (cid:N) tokens, OR
    - More than 20 % of lines contain the spaced-letter pattern.
    """
    if not text:
        return False
    # (cid:N) ratio
    cid_chars = sum(len(m.group()) for m in _CID_RE.finditer(text))
    nonws = sum(1 for c in text if not c.isspace())
    if nonws > 0 and cid_chars / nonws > 0.05:
        return True
    # Spaced-letter ratio
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    spaced = sum(1 for ln in lines if _SPACED_WORD_RE.search(ln))
    return spaced / len(lines) > 0.20


def is_disordered(text: str) -> bool:
    """Heuristic: does native text look column-merged / out of reading order?

    A cheap signal used to decide whether the layout stage should run. Real
    layout engines are dependency-gated; when none is available this only sets a
    flag for diagnostics.
    """

    if not text:
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    # Many lines containing a wide internal gap suggest two columns flattened
    # onto one line by a naive extractor.
    wide_gap = sum(1 for ln in lines if "   " in ln.strip())
    return wide_gap >= max(3, len(lines) // 3)
