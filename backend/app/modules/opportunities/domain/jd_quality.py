"""Deterministic JD quality-check rubric (B-552).

Runs a fixed set of rule-based checks against a job posting before it may be
submitted for moderation. This is intentionally **not** an AI call — the
AI bias-check (``application.jd_ai_service.check_bias``) is a separate,
advisory feature and stays untouched.

Each finding is a :class:`QualityIssue` with a stable ``field`` + ``issue``
machine-readable reason code, a ``severity`` (``BLOCKING`` blocks submit;
``ADVISORY`` is a warning surfaced to the partner but never blocks), and a
vi/en message pair (never expose a bare enum code to the end user).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.opportunities.domain.models import Job

BLOCKING = "blocking"
ADVISORY = "advisory"

# Whole-string (normalized) placeholder/test content markers. Deliberately
# exact-match (plus a "lorem ipsum" substring check) rather than substring
# matching on common words like "test" — a real JD legitimately mentioning
# "testing" or containing the word "sample" must not be flagged.
_PLACEHOLDER_TOKENS: frozenset[str] = frozenset(
    {
        "test",
        "tests",
        "testing",
        "asdf",
        "asdfasdf",
        "xxx",
        "xxxx",
        "xx",
        "n/a",
        "na",
        "tbd",
        "todo",
        "sample",
        "sample job",
        "sample text",
        "placeholder",
        "chua co",
        "chưa có",
        "chưa cập nhật",
        "update later",
        "de sau",
        "để sau",
        "chưa rõ",
        "chua ro",
    }
)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _contains_placeholder(text: str | None) -> bool:
    norm = _norm(text)
    if not norm:
        return False
    if norm in _PLACEHOLDER_TOKENS:
        return True
    return "lorem ipsum" in norm


_BULLET_RE = re.compile(r"^\s*([-*•‣▪]|\d+[.)])\s+")


def _count_bullets(text: str | None) -> int:
    """Best-effort bullet/line count for a free-text requirements block."""

    if not text:
        return 0
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0
    marked = [ln for ln in lines if _BULLET_RE.match(ln)]
    # If the author used explicit bullet markers, count only those; otherwise
    # fall back to one requirement per non-empty line (common free-text style).
    return len(marked) if marked else len(lines)


@dataclass(slots=True)
class QualityIssue:
    field: str
    issue: str
    severity: str
    message_vi: str
    message_en: str

    def as_dict(self, *, locale: str = "vi") -> dict:
        return {
            "field": self.field,
            "issue": self.issue,
            "severity": self.severity,
            "message": self.message_vi if locale == "vi" else self.message_en,
        }


def has_blocking(issues: list[QualityIssue]) -> bool:
    return any(i.severity == BLOCKING for i in issues)


def _has_city(job: Job) -> bool:
    if job.location_city:
        return True
    for loc in job.locations or []:
        if isinstance(loc, dict) and loc.get("city"):
            return True
    return False


def evaluate(job: Job) -> list[QualityIssue]:
    """Evaluate a job's structured content against the JD quality rubric.

    Deterministic and side-effect free — callers decide what to do with the
    result (block submit on any ``BLOCKING`` issue; surface ``ADVISORY``
    issues as non-blocking warnings).
    """

    issues: list[QualityIssue] = []
    # --- Title --------------------------------------------------------- #
    # NOTE: the schema already enforces `min_length=3`; a short-but-real title
    # (e.g. "PM", "QA Lead", "Eng") is common and must not be treated as a
    # quality defect on its own — only advisory, and only placeholder/test
    # content actually blocks submit.
    title = (job.title or "").strip()
    if _contains_placeholder(title):
        issues.append(
            QualityIssue(
                "title",
                "title_placeholder",
                BLOCKING,
                "Tiêu đề có vẻ là nội dung tạm/thử nghiệm. Vui lòng cập nhật tiêu đề thật.",
                "The title looks like placeholder/test content. Please use a real title.",
            )
        )
    elif len(title) < 5:
        issues.append(
            QualityIssue(
                "title",
                "title_too_short",
                ADVISORY,
                "Tiêu đề khá ngắn — hãy cân nhắc đặt tiêu đề rõ ràng, cụ thể hơn.",
                "The title is quite short — consider a clearer, more specific title.",
            )
        )
    elif len(title) > 150:
        issues.append(
            QualityIssue(
                "title",
                "title_too_long",
                ADVISORY,
                "Tiêu đề khá dài — ứng viên thường phản hồi tốt hơn với tiêu đề ngắn gọn.",
                "The title is quite long — candidates usually respond better to concise titles.",
            )
        )

    # --- Description ----------------------------------------------------- #
    description = (job.description or "").strip()
    if len(description) < 20 or _contains_placeholder(description):
        issues.append(
            QualityIssue(
                "description",
                "description_too_short",
                BLOCKING,
                "Mô tả công việc quá ngắn hoặc là nội dung tạm. Vui lòng viết mô tả đầy đủ.",
                "The job description is too short or looks like placeholder "
                "content. Please write a full description.",
            )
        )
    elif len(description) < 200:
        issues.append(
            QualityIssue(
                "description",
                "description_thin",
                ADVISORY,
                "Mô tả công việc khá ngắn — hãy bổ sung chi tiết về nhiệm vụ "
                "và môi trường làm việc.",
                "The description is quite thin — consider adding more detail "
                "about duties and work environment.",
            )
        )

    # --- Requirements / responsibilities bullets ------------------------- #
    requirements = (job.requirements or "").strip()
    if requirements and _contains_placeholder(requirements):
        issues.append(
            QualityIssue(
                "requirements",
                "requirements_placeholder",
                BLOCKING,
                "Yêu cầu công việc có vẻ là nội dung tạm. Vui lòng cập nhật nội dung thật.",
                "The requirements look like placeholder content. Please add the real requirements.",
            )
        )
    elif not requirements:
        issues.append(
            QualityIssue(
                "requirements",
                "requirements_missing",
                ADVISORY,
                "Chưa có yêu cầu/trách nhiệm công việc — tin đăng có tỷ lệ "
                "ứng tuyển tốt hơn khi liệt kê rõ ràng.",
                "No requirements/responsibilities listed — postings convert "
                "better with a clear bullet list.",
            )
        )
    elif _count_bullets(requirements) < 3:
        issues.append(
            QualityIssue(
                "requirements",
                "requirements_few_bullets",
                ADVISORY,
                "Nên liệt kê ít nhất 3 gạch đầu dòng yêu cầu/trách nhiệm để ứng viên dễ hiểu.",
                "Consider listing at least 3 requirement/responsibility bullets for clarity.",
            )
        )

    # --- Salary ------------------------------------------------------------ #
    if job.salary_is_disclosed and job.salary_min is None and job.salary_max is None:
        issues.append(
            QualityIssue(
                "salary",
                "salary_disclosed_without_values",
                BLOCKING,
                "Bạn đã bật hiển thị mức lương nhưng chưa nhập khoảng lương.",
                "Salary disclosure is on but no salary range was entered.",
            )
        )
    elif not job.salary_is_disclosed:
        issues.append(
            QualityIssue(
                "salary",
                "salary_not_disclosed",
                ADVISORY,
                "Tin tuyển dụng công khai mức lương thường thu hút nhiều ứng viên chất lượng hơn.",
                "Jobs that disclose salary tend to attract more qualified candidates.",
            )
        )

    # --- Location ------------------------------------------------------------ #
    if job.location_type in {"onsite", "hybrid"} and not _has_city(job):
        issues.append(
            QualityIssue(
                "location_city",
                "location_city_missing",
                BLOCKING,
                "Công việc tại văn phòng/linh hoạt cần có thông tin thành phố làm việc.",
                "On-site/hybrid jobs need a work city.",
            )
        )

    # --- Experience ------------------------------------------------------------ #
    if job.experience_min_years is None and job.experience_max_years is None:
        issues.append(
            QualityIssue(
                "experience",
                "experience_not_set",
                ADVISORY,
                "Chưa đặt yêu cầu kinh nghiệm — hãy chọn 'Không yêu cầu' hoặc "
                "số năm cụ thể để ứng viên dễ tự đánh giá.",
                "No experience requirement set — pick 'not required' or a "
                "specific range to help candidates self-assess.",
            )
        )

    return issues
