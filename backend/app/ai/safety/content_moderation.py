"""Deterministic, rule-based content-policy scanner for user-visible content.

AI_PRODUCT_SPEC.md §3 lists ``content_moderation`` (permission_class:
``human_review``) for job/ad/review/event content. Like
``app.ai.safety.bias_detection``, this v1 is a fully deterministic, offline,
zero-cost pattern scanner — no LLM call ("prefer deterministic/local parsing
... before spending real model calls").

ADVISORY ONLY (§1, §9.3): findings never auto-remove or auto-reject content.
``policy_violation`` triggers escalation to the ``human_review_queue`` table
(migration ``0052_human_review_queue``) where a university moderator makes the
final decision. Bilingual (Vietnamese + English).

Scope of this MVP — the categories with clear-cut lexical signals and
well-understood recruitment-scam patterns in the Vietnamese market:
- ``fee_collection``: charging candidates money to apply / deposits / training
  fees before hiring (classic recruitment scam; likely-illegal → high risk).
- ``pyramid_scheme``: multi-level/network marketing recruitment framing.
- ``unrealistic_earnings``: "no experience, huge guaranteed income" bait.
- ``off_platform_contact``: pressure to move to unmonitored channels before
  any legitimate application step (medium — legitimate employers sometimes
  list Zalo, so this alone is never high risk).
- ``adult_content``: sexually suggestive job requirements.

It intentionally does NOT attempt semantic scam detection (paraphrased bait
without trigger phrases) — that needs a labeled corpus and a real
precision/recall eval, tracked as a follow-up, not a v1 regex pass.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

CATEGORY_FEE = "fee_collection"
CATEGORY_PYRAMID = "pyramid_scheme"
CATEGORY_EARNINGS = "unrealistic_earnings"
CATEGORY_OFF_PLATFORM = "off_platform_contact"
CATEGORY_ADULT = "adult_content"

RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"


@dataclass(slots=True)
class ContentFinding:
    category: str
    risk_level: str
    matched_phrase: str
    explanation: str


@dataclass(slots=True)
class ContentCheckResult:
    findings: list[ContentFinding] = field(default_factory=list)

    @property
    def policy_violation(self) -> bool:
        """True when any HIGH-risk finding exists (§9.3 escalation trigger)."""
        return any(f.risk_level == RISK_HIGH for f in self.findings)

    @property
    def flagged(self) -> bool:
        return bool(self.findings)

    def as_dict(self) -> dict:
        return {
            "flagged": self.flagged,
            "policy_violation": self.policy_violation,
            "findings": [
                {
                    "category": f.category,
                    "risk_level": f.risk_level,
                    "matched_phrase": f.matched_phrase,
                    "explanation": f.explanation,
                }
                for f in self.findings
            ],
        }


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFKC", text)


_RULES: list[tuple[re.Pattern, str, str, str]] = [
    # --- Fee collection / recruitment scam ---
    (
        re.compile(
            r"\b(?:nộp|đóng|thu)\s+(?:phí|tiền)\s+"
            r"(?:hồ\s*sơ|giữ\s*chỗ|đào\s*tạo|đồng\s*phục|ứng\s*tuyển)\b",
            re.IGNORECASE,
        ),
        CATEGORY_FEE,
        RISK_HIGH,
        "Thu phí của ứng viên trước khi tuyển dụng là dấu hiệu lừa đảo tuyển "
        "dụng phổ biến và bị cấm trên nền tảng.",
    ),
    (
        re.compile(r"\bđặt\s+cọc\b", re.IGNORECASE),
        CATEGORY_FEE,
        RISK_HIGH,
        "Yêu cầu ứng viên đặt cọc tiền là dấu hiệu lừa đảo tuyển dụng.",
    ),
    (
        re.compile(
            r"\b(?:application|registration|training|placement)\s+fee\s+"
            r"(?:required|must\s+be\s+paid|of)\b",
            re.IGNORECASE,
        ),
        CATEGORY_FEE,
        RISK_HIGH,
        "Charging candidates a fee before hiring is a classic recruitment "
        "scam signal and is prohibited on the platform.",
    ),
    (
        re.compile(r"\bpay\s+a?\s*deposit\b", re.IGNORECASE),
        CATEGORY_FEE,
        RISK_HIGH,
        "Requiring a monetary deposit from candidates is a recruitment scam "
        "signal.",
    ),
    # --- Pyramid / MLM ---
    (
        re.compile(r"\b(?:kinh\s+doanh\s+)?đa\s+cấp\b", re.IGNORECASE),
        CATEGORY_PYRAMID,
        RISK_HIGH,
        "Nội dung liên quan mô hình đa cấp cần được kiểm duyệt viên xem xét "
        "trước khi hiển thị cho sinh viên.",
    ),
    (
        re.compile(
            r"\b(?:tuyển\s+)?(?:cộng\s+tác\s+viên\s+)?"
            r"(?:xây\s+dựng|phát\s+triển)\s+(?:hệ\s+thống|tuyến\s+dưới)\b",
            re.IGNORECASE,
        ),
        CATEGORY_PYRAMID,
        RISK_MEDIUM,
        "Mô tả 'xây dựng hệ thống/tuyến dưới' là dấu hiệu tuyển dụng đa cấp; "
        "cần người kiểm duyệt xác nhận bản chất công việc.",
    ),
    (
        re.compile(
            r"\b(?:multi[\s-]?level|network)\s+marketing\b|\bMLM\b",
            re.IGNORECASE,
        ),
        CATEGORY_PYRAMID,
        RISK_HIGH,
        "Multi-level-marketing recruitment must be human-reviewed before it "
        "is shown to students.",
    ),
    (
        re.compile(r"\brecruit\s+your\s+own\s+downline\b", re.IGNORECASE),
        CATEGORY_PYRAMID,
        RISK_HIGH,
        "Recruiting a 'downline' is a defining pyramid-scheme signal.",
    ),
    # --- Unrealistic earnings bait ---
    (
        re.compile(
            r"\bthu\s+nhập\s+(?:khủng|siêu\s+cao|không\s+giới\s+hạn)\b",
            re.IGNORECASE,
        ),
        CATEGORY_EARNINGS,
        RISK_MEDIUM,
        "Hứa hẹn 'thu nhập khủng/không giới hạn' là mồi nhử phổ biến của tin "
        "tuyển dụng lừa đảo; hãy nêu mức lương cụ thể, thực tế.",
    ),
    (
        re.compile(
            r"\b(?:việc\s+nhẹ\s+lương\s+cao|không\s+cần\s+(?:kinh\s+nghiệm|"
            r"bằng\s+cấp)[^.\n]{0,40}(?:lương|thu\s+nhập)\s*(?:cao|khủng))\b",
            re.IGNORECASE,
        ),
        CATEGORY_EARNINGS,
        RISK_HIGH,
        "'Việc nhẹ lương cao' không cần kinh nghiệm là mẫu câu đặc trưng của "
        "tin tuyển dụng lừa đảo.",
    ),
    (
        re.compile(
            r"\b(?:guaranteed|earn)\s+(?:up\s+to\s+)?\$?\d[\d.,]*\s*"
            r"(?:per|a|/)\s*(?:day|week)\b[^.\n]{0,60}\bno\s+experience\b",
            re.IGNORECASE,
        ),
        CATEGORY_EARNINGS,
        RISK_HIGH,
        "Guaranteed high daily/weekly income with no experience required is "
        "a hallmark of job-posting scams.",
    ),
    # --- Off-platform contact pressure ---
    (
        re.compile(
            r"\b(?:liên\s+hệ|nhắn\s+tin|kết\s+bạn)\s+(?:qua\s+)?"
            r"(?:zalo|telegram|whatsapp)\s+(?:trước|để\s+nhận\s+việc|"
            r"để\s+được\s+nhận)\b",
            re.IGNORECASE,
        ),
        CATEGORY_OFF_PLATFORM,
        RISK_MEDIUM,
        "Yêu cầu liên hệ kênh ngoài nền tảng trước khi ứng tuyển chính thức "
        "làm mất khả năng bảo vệ ứng viên; quy trình ứng tuyển nên diễn ra "
        "trên nền tảng.",
    ),
    (
        re.compile(
            r"\b(?:contact|message|dm)\s+(?:us\s+)?(?:on|via)\s+"
            r"(?:telegram|whatsapp|zalo)\s+(?:first|to\s+get\s+the\s+job)\b",
            re.IGNORECASE,
        ),
        CATEGORY_OFF_PLATFORM,
        RISK_MEDIUM,
        "Pressure to move to unmonitored channels before a legitimate "
        "application step is a common scam pattern.",
    ),
    # --- Adult content ---
    (
        re.compile(
            r"\b(?:nhạy\s+cảm|khiêu\s+dâm|sugar\s+(?:baby|daddy))\b",
            re.IGNORECASE,
        ),
        CATEGORY_ADULT,
        RISK_HIGH,
        "Nội dung người lớn/nhạy cảm không được phép trên nền tảng hướng tới "
        "sinh viên.",
    ),
    (
        re.compile(r"\badult\s+(?:content|entertainment|services)\b", re.IGNORECASE),
        CATEGORY_ADULT,
        RISK_HIGH,
        "Adult content is not allowed on a student-facing platform.",
    ),
]


def check_content(text: str) -> ContentCheckResult:
    """Scan ``text`` (job/ad/review/event content) for policy-violation signals.

    Deterministic and offline — safe to run on every save with zero cost.
    Overlapping matches from different rules are all reported; the human
    moderator decides what to act on.
    """
    normalized = _normalize(text)
    if not normalized.strip():
        return ContentCheckResult(findings=[])

    findings: list[ContentFinding] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern, category, risk_level, explanation in _RULES:
        for m in pattern.finditer(normalized):
            span = m.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            findings.append(
                ContentFinding(
                    category=category,
                    risk_level=risk_level,
                    matched_phrase=m.group(0).strip(),
                    explanation=explanation,
                )
            )

    return ContentCheckResult(findings=findings)
