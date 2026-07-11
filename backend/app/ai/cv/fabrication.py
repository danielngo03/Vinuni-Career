"""Fabrication check — flag CV claims unsupported by the evidence corpus.

This is the deterministic safety net behind every CV AI task: it scans proposed
``after`` content for high-risk claims (quantified outcomes, GPA, awards,
certifications) that do NOT appear in the grounding evidence and reports them.
When anything is flagged, the task sets ``requires_fact_confirmation = True`` so
the student must explicitly confirm before accept (``docs/CV_STUDIO_SPEC.md`` §3:
"AI cannot invent ... if the AI suggests an unverified fact, label it 'Cần xác
nhận'").
"""

from __future__ import annotations

import re

from app.ai.cv.grounding import normalize

# High-risk fabrication-target keywords (en + vi). Presence in ``after`` but not
# in evidence => unsupported claim.
_RISK_KEYWORDS = [
    "gpa",
    "award",
    "awards",
    "prize",
    "scholarship",
    "certified",
    "certificate",
    "certification",
    "toeic",
    "toefl",
    "ielts",
    "first place",
    "gold medal",
    "patent",
    "published",
    "honors",
    "dean's list",
    "giải nhất",
    "giải nhì",
    "huy chương",
    "học bổng",
    "chứng chỉ",
    "bằng khen",
    "thủ khoa",
    "xuất sắc nhất",
]

# A number, optional decimal, optional percent (e.g. "4.0", "30%", "1000").
_NUMBER_RE = re.compile(r"\d[\d.,]*%?")


def find_unsupported_claims(after_text: str, evidence_text: str) -> list[str]:
    """Return user-safe descriptions of claims in ``after`` not backed by evidence."""

    after_norm = normalize(after_text)
    ev = normalize(evidence_text)
    claims: list[str] = []

    for raw in _NUMBER_RE.findall(after_text):
        token = raw.strip().rstrip("%").rstrip(".,")
        if not token or len(token) < 1:
            continue
        if token not in ev:
            label = f"số liệu chưa có bằng chứng: '{raw.strip()}'"
            if label not in claims:
                claims.append(label)

    for kw in _RISK_KEYWORDS:
        if kw in after_norm and kw not in ev:
            label = f"tuyên bố cần xác nhận: '{kw}'"
            if label not in claims:
                claims.append(label)

    return claims
