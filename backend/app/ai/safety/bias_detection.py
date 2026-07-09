"""Deterministic, rule-based bias/discrimination checker for JD text.

AI_PRODUCT_SPEC.md §3 lists ``bias_detection`` (permission_class:
``human_review``) as a JD bias checker for partner/university use. This is
the first real implementation of it: a fully deterministic, offline,
zero-cost pattern scanner — no LLM call, following the project rule "prefer
deterministic/local parsing ... before spending real model calls" and
mirroring the existing rule-based safety modules
(``app.ai.safety.input_guard``, ``app.ai.safety.policy_orchestrator``).

This module is ADVISORY ONLY (§1, §9.3): it never blocks JD publication and
never makes a final moderation decision. It returns structured findings for
a human (partner, then university moderator for high-risk flags) to review
and edit. Bilingual (Vietnamese + English) since partner JD text is
predominantly Vietnamese in production.

Scope of this MVP: age, explicit gender exclusion, disability exclusion, and
appearance/marital-status requirements — the categories with clear-cut,
low-false-positive lexical signals. It intentionally does NOT attempt to
detect subtler statistical bias (e.g. masculine-coded adjective clustering)
that needs a labeled corpus and real precision/recall tuning — that is a
tracked follow-up requiring an eval-driven ML approach, not a v1 regex pass.

Human-review-queue persistence (writing high-risk findings to a reviewable
queue table, §9.3) is NOT wired here — this module only returns the
structured result. Wiring it into ``human_review_queue`` needs a migration
and is tracked separately (see docs/IMPLEMENTATION_STATUS.md).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

CATEGORY_AGE = "age_discrimination"
CATEGORY_GENDER = "gender_exclusion"
CATEGORY_DISABILITY = "disability_exclusion"
CATEGORY_APPEARANCE = "appearance_marital_status"

RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"


@dataclass(slots=True)
class BiasFinding:
    category: str
    risk_level: str
    matched_phrase: str
    suggestion: str


@dataclass(slots=True)
class BiasCheckResult:
    findings: list[BiasFinding] = field(default_factory=list)

    @property
    def requires_human_review(self) -> bool:
        """True when any HIGH-risk (likely-illegal discrimination) finding exists."""
        return any(f.risk_level == RISK_HIGH for f in self.findings)

    @property
    def flagged(self) -> bool:
        return bool(self.findings)

    def as_dict(self) -> dict:
        return {
            "flagged": self.flagged,
            "requires_human_review": self.requires_human_review,
            "findings": [
                {
                    "category": f.category,
                    "risk_level": f.risk_level,
                    "matched_phrase": f.matched_phrase,
                    "suggestion": f.suggestion,
                }
                for f in self.findings
            ],
        }


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFKC", text)


# Each rule: (compiled pattern, category, risk_level, suggestion). Patterns
# are matched case-insensitively against NFKC-normalized text. Vietnamese
# diacritics are matched literally (not stripped) to avoid false positives
# from folding distinct words together.
_RULES: list[tuple[re.Pattern, str, str, str]] = [
    # --- Age discrimination ---
    (
        re.compile(r"\bdưới\s*(\d{2})\s*tuổi\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_MEDIUM,
        "Thay vì giới hạn độ tuổi, hãy mô tả yêu cầu kinh nghiệm/kỹ năng cụ thể "
        "(ví dụ: '2+ năm kinh nghiệm').",
    ),
    (
        re.compile(r"\btừ\s*\d{2}\s*(?:-|đến)\s*\d{2}\s*tuổi\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_MEDIUM,
        "Khoảng tuổi cụ thể có thể loại trừ ứng viên phù hợp; cân nhắc mô tả "
        "theo số năm kinh nghiệm thay vì độ tuổi.",
    ),
    (
        re.compile(r"\b(?:only\s+)?under\s*(?:the\s*)?age\s*of\s*\d{2}\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_MEDIUM,
        "Replace an age ceiling with an experience-level requirement instead.",
    ),
    (
        re.compile(r"\btrẻ\s*trung\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_LOW,
        "Cụm từ 'trẻ trung' có thể ngầm loại trừ ứng viên lớn tuổi; cân nhắc "
        "mô tả văn hoá công ty theo cách trung lập hơn (ví dụ: 'năng động').",
    ),
    (
        re.compile(r"\byoung\s+and\s+(?:energetic|dynamic)\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_LOW,
        "Consider 'energetic and motivated' instead of 'young and energetic'.",
    ),
    (
        re.compile(
            r"\b(?:chỉ\s+tuyển|ưu\s+tiên)\s+sinh\s+viên\s+mới\s+ra\s+trường\b", re.IGNORECASE
        ),
        CATEGORY_AGE,
        RISK_MEDIUM,
        "Giới hạn 'chỉ mới ra trường' loại trừ ứng viên chuyển ngành hợp lệ; "
        "hãy mô tả yêu cầu kinh nghiệm cụ thể thay vì tình trạng tốt nghiệp.",
    ),
    (
        re.compile(r"\bdigital\s+native\b", re.IGNORECASE),
        CATEGORY_AGE,
        RISK_LOW,
        "'Digital native' is often read as an age proxy; describe the actual "
        "technical skill required instead.",
    ),
    # --- Explicit gender exclusion ---
    (
        re.compile(r"\bchỉ\s+tuyển\s+(?:nam|nữ)\b", re.IGNORECASE),
        CATEGORY_GENDER,
        RISK_HIGH,
        "Yêu cầu giới tính cụ thể không có cơ sở nghề nghiệp là hình thức phân "
        "biệt đối xử; hãy xoá yêu cầu này trừ khi có lý do nghề nghiệp chính đáng.",
    ),
    (
        re.compile(r"\bưu\s+tiên\s+(?:nam|nữ)\s+giới\b", re.IGNORECASE),
        CATEGORY_GENDER,
        RISK_HIGH,
        "Ưu tiên theo giới tính không có cơ sở nghề nghiệp cần được xem xét lại.",
    ),
    (
        re.compile(r"\b(?:male|female)s?\s+only\b", re.IGNORECASE),
        CATEGORY_GENDER,
        RISK_HIGH,
        "A gender-only requirement without a genuine occupational reason should be removed.",
    ),
    (
        re.compile(r"\bnam\s+giới\s+ưu\s+tiên\b", re.IGNORECASE),
        CATEGORY_GENDER,
        RISK_HIGH,
        "Ưu tiên nam giới không có cơ sở nghề nghiệp cần được xem xét lại.",
    ),
    # --- Disability exclusion ---
    (
        re.compile(r"\bkhông\s+(?:có\s+)?khuyết\s+tật\b", re.IGNORECASE),
        CATEGORY_DISABILITY,
        RISK_HIGH,
        "Yêu cầu 'không khuyết tật' là hình thức phân biệt đối xử; nếu công "
        "việc có yêu cầu thể chất cụ thể, hãy mô tả yêu cầu đó thay vì loại "
        "trừ người khuyết tật nói chung.",
    ),
    (
        re.compile(r"\bable[\s-]?bodied\s+only\b", re.IGNORECASE),
        CATEGORY_DISABILITY,
        RISK_HIGH,
        "Describe the genuine physical requirement of the role instead of "
        "excluding disabled candidates generally.",
    ),
    (
        re.compile(r"\bno\s+disabilit(?:y|ies)\b", re.IGNORECASE),
        CATEGORY_DISABILITY,
        RISK_HIGH,
        "This phrasing excludes disabled candidates broadly; describe the "
        "specific essential function instead.",
    ),
    # --- Appearance / marital status ---
    (
        re.compile(r"\bngoại\s+hình\s+(?:ưa\s+nhìn|dễ\s+nhìn|đẹp)\b", re.IGNORECASE),
        CATEGORY_APPEARANCE,
        RISK_MEDIUM,
        "Yêu cầu ngoại hình không liên quan trực tiếp đến công việc nên được "
        "xem xét lại hoặc thay bằng yêu cầu chuyên môn cụ thể.",
    ),
    (
        re.compile(r"\battractive\s+appearance\b", re.IGNORECASE),
        CATEGORY_APPEARANCE,
        RISK_MEDIUM,
        "Appearance requirements unrelated to the job's genuine needs should be reconsidered.",
    ),
    (
        re.compile(r"\bchưa\s+(?:lập\s+gia\s+đình|kết\s+hôn)\b", re.IGNORECASE),
        CATEGORY_APPEARANCE,
        RISK_HIGH,
        "Yêu cầu về tình trạng hôn nhân không có cơ sở nghề nghiệp là hình "
        "thức phân biệt đối xử và nên được xoá.",
    ),
    (
        re.compile(r"\b(?:single|unmarried)\s+(?:preferred|only|required)\b", re.IGNORECASE),
        CATEGORY_APPEARANCE,
        RISK_HIGH,
        "Marital-status requirements without a genuine occupational reason should be removed.",
    ),
]


def check_bias(text: str) -> BiasCheckResult:
    """Scan ``text`` (a JD draft or published description) for biased phrasing.

    Deterministic and offline — safe to run on every JD save with zero cost.
    Returns every match found; overlapping matches from different rules are
    all reported (a human reviewer decides what to act on).
    """
    normalized = _normalize(text)
    if not normalized.strip():
        return BiasCheckResult(findings=[])

    findings: list[BiasFinding] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern, category, risk_level, suggestion in _RULES:
        for m in pattern.finditer(normalized):
            span = m.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            findings.append(
                BiasFinding(
                    category=category,
                    risk_level=risk_level,
                    matched_phrase=m.group(0).strip(),
                    suggestion=suggestion,
                )
            )

    return BiasCheckResult(findings=findings)
