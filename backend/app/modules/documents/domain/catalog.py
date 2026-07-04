"""Documents / CV Studio vocabulary, defaults, labels, and template seeds.

Pure domain constants and helpers — no I/O. Friendly vi/en labels are paired with
every raw enum code so the API never ships a raw code alone
(``.claude/rules/backend.md``: "No raw enum codes in end-user responses").
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# CV creation modes (``docs/API_CONTRACTS.md`` Create CV)                       #
# --------------------------------------------------------------------------- #

CREATION_BLANK = "blank_template"
CREATION_PROFILE_IMPORT = "profile_import"
CREATION_NOTES_IMPORT = "notes_import"  # deterministic CV-first seed from pasted notes
CREATION_UPLOADED_IMPORT = "uploaded_import"
CREATION_DUPLICATE = "duplicate_existing"
CREATION_AI_DRAFT = "ai_assisted_draft"  # deferred to the ai-engineer slice

# Non-AI creation modes implemented in this slice.
NON_AI_CREATION_MODES = frozenset(
    {
        CREATION_BLANK,
        CREATION_PROFILE_IMPORT,
        CREATION_NOTES_IMPORT,
        CREATION_UPLOADED_IMPORT,
        CREATION_DUPLICATE,
    }
)
ALL_CREATION_MODES = NON_AI_CREATION_MODES | {CREATION_AI_DRAFT}

# source_type stored on cv_profiles (``docs/DATA_MODEL.md`` §7).
SOURCE_TYPE_FOR_MODE = {
    CREATION_BLANK: "blank_template",
    CREATION_PROFILE_IMPORT: "profile_import",
    CREATION_NOTES_IMPORT: "notes_import",
    CREATION_UPLOADED_IMPORT: "uploaded_import",
    CREATION_DUPLICATE: "duplicate_existing",
    CREATION_AI_DRAFT: "ai_draft",
}

# --------------------------------------------------------------------------- #
# CV section types                                                             #
# --------------------------------------------------------------------------- #

SECTION_TYPES = frozenset(
    {
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
        "custom",
    }
)

# Default blank-template section skeleton (ASCII titles; content empty).
DEFAULT_SECTIONS: list[dict] = [
    {"section_type": "summary", "title": "Summary", "sort_order": 10},
    {"section_type": "education", "title": "Education", "sort_order": 20},
    {"section_type": "experience", "title": "Experience", "sort_order": 30},
    {"section_type": "projects", "title": "Projects", "sort_order": 40},
    {"section_type": "skills", "title": "Skills", "sort_order": 50},
    {"section_type": "certifications", "title": "Certifications", "sort_order": 60},
]

# --------------------------------------------------------------------------- #
# AI CV suggestion task types (``docs/API_CONTRACTS.md`` AI Suggestion Request) #
# --------------------------------------------------------------------------- #

TASK_DRAFT_FROM_PROFILE = "draft_cv_from_profile"
TASK_FILL_FROM_SOURCES = "fill_cv_template_from_sources"
TASK_GENERATE_BULLETS = "generate_cv_bullets"
TASK_REWRITE_SECTION = "rewrite_cv_section"
TASK_OPTIMIZE_FOR_JOB = "optimize_cv_for_job"
TASK_ATS_KEYWORDS = "ats_keyword_suggestions"
TASK_FABRICATION_CHECK = "cv_fabrication_check"

# Natural-language CV edit command (``docs/CV_STUDIO_SPEC.md`` "Natural-Language AI
# Editing"). Dispatched through a dedicated service function (not the generic
# ``request_suggestion`` task-type validator) but stored/accepted/rejected through
# the SAME ``cv_ai_suggestions`` pipeline, so it needs a label like every task_type.
TASK_AI_EDIT_COMMAND = "ai_edit_command"

AI_TASK_TYPES = frozenset(
    {
        TASK_DRAFT_FROM_PROFILE,
        TASK_FILL_FROM_SOURCES,
        TASK_GENERATE_BULLETS,
        TASK_REWRITE_SECTION,
        TASK_OPTIMIZE_FOR_JOB,
        TASK_ATS_KEYWORDS,
        TASK_FABRICATION_CHECK,
    }
)

# Tasks that require a ``target_section_id`` (operate on one section).
SECTION_TARGETED_TASKS = frozenset({TASK_GENERATE_BULLETS, TASK_REWRITE_SECTION})

# Tasks that require a ``job_id``.
JOB_TARGETED_TASKS = frozenset({TASK_OPTIMIZE_FOR_JOB, TASK_ATS_KEYWORDS})

# Read-only / advisory tasks: produce advice only, accepting applies no content.
ADVISORY_TASKS = frozenset({TASK_ATS_KEYWORDS, TASK_FABRICATION_CHECK})

# Credits charged per task on successful generation (no ledger enforcement yet;
# recorded on the row per ``docs/CV_STUDIO_SPEC.md`` §5 "consume credits only when
# generation succeeds"). Advisory tasks are free.
TASK_CREDIT_COST = {
    TASK_DRAFT_FROM_PROFILE: 2,
    TASK_FILL_FROM_SOURCES: 2,
    TASK_GENERATE_BULLETS: 1,
    TASK_REWRITE_SECTION: 1,
    TASK_OPTIMIZE_FOR_JOB: 2,
    TASK_ATS_KEYWORDS: 0,
    TASK_FABRICATION_CHECK: 0,
}

# AI suggestion lifecycle statuses.
SUGGESTION_PENDING = "pending"
SUGGESTION_ACCEPTED = "accepted"
SUGGESTION_REJECTED = "rejected"
SUGGESTION_EXPIRED = "expired"
SUGGESTION_STATUSES = frozenset(
    {SUGGESTION_PENDING, SUGGESTION_ACCEPTED, SUGGESTION_REJECTED, SUGGESTION_EXPIRED}
)

_SUGGESTION_STATUS_LABELS = {
    SUGGESTION_PENDING: ("Đang chờ duyệt", "Pending review"),
    SUGGESTION_ACCEPTED: ("Đã áp dụng", "Applied"),
    SUGGESTION_REJECTED: ("Đã từ chối", "Rejected"),
    SUGGESTION_EXPIRED: ("Đã hết hạn", "Expired"),
}

_TASK_LABELS = {
    TASK_DRAFT_FROM_PROFILE: ("Soạn CV từ hồ sơ", "Draft CV from profile"),
    TASK_FILL_FROM_SOURCES: ("Điền CV từ nguồn", "Fill CV from sources"),
    TASK_GENERATE_BULLETS: ("Tạo gạch đầu dòng", "Generate bullet points"),
    TASK_REWRITE_SECTION: ("Viết lại mục", "Rewrite section"),
    TASK_OPTIMIZE_FOR_JOB: ("Tối ưu theo tin tuyển dụng", "Optimize for job"),
    TASK_ATS_KEYWORDS: ("Gợi ý từ khóa ATS", "ATS keyword suggestions"),
    TASK_FABRICATION_CHECK: ("Kiểm tra tính xác thực", "Fabrication check"),
    TASK_AI_EDIT_COMMAND: ("Chỉnh sửa CV bằng AI", "AI CV edit"),
}


def suggestion_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_SUGGESTION_STATUS_LABELS, code, locale=locale)


def task_label(code: str, *, locale: str = "vi") -> str:
    return _label(_TASK_LABELS, code, locale=locale)


# --------------------------------------------------------------------------- #
# Lifecycle statuses                                                           #
# --------------------------------------------------------------------------- #

CV_DRAFT = "draft"
CV_READY = "ready"
CV_ARCHIVED = "archived"
CV_STATUSES = frozenset({CV_DRAFT, CV_READY, CV_ARCHIVED})

_STATUS_LABELS = {
    CV_DRAFT: ("Bản nháp", "Draft"),
    CV_READY: ("Sẵn sàng", "Ready"),
    CV_ARCHIVED: ("Đã lưu trữ", "Archived"),
}

_SOURCE_LABELS = {
    "builder": ("Tự tạo", "Builder"),
    "blank_template": ("Tạo từ mẫu", "From template"),
    "profile_import": ("Nhập từ hồ sơ", "Imported from profile"),
    "notes_import": ("Tạo từ ghi chú", "From raw notes"),
    "uploaded_import": ("Nhập từ CV tải lên", "Imported from upload"),
    "duplicate_existing": ("Bản sao", "Duplicated"),
    "ai_draft": ("Bản nháp AI", "AI draft"),
}

# parse-run + export statuses surfaced to users; raw code never alone.
_PARSE_STATUS_LABELS = {
    "queued": ("Đang chờ xử lý", "Queued"),
    "running": ("Đang xử lý", "Processing"),
    "review_required": ("Cần kiểm tra", "Review required"),
    "completed": ("Hoàn tất", "Completed"),
    "failed": ("Không xử lý được", "Failed"),
}

_EXPORT_STATUS_LABELS = {
    "queued": ("Đang chờ", "Queued"),
    "running": ("Đang tạo", "Rendering"),
    "ready": ("Sẵn sàng tải", "Ready"),
    "failed": ("Tạo thất bại", "Failed"),
}

# --------------------------------------------------------------------------- #
# CV ingestion friendly status vocabulary                                      #
# (docs/CV_INGESTION_EXTRACTION_SPEC.md §2/§5 — user-safe states only)          #
# --------------------------------------------------------------------------- #

INGEST_QUEUED = "queued"
INGEST_CHECKING = "checking"
INGEST_READING = "reading"
INGEST_IMPROVING_LAYOUT = "improving_layout"
INGEST_READING_SCANNED = "reading_scanned"
INGEST_PREPARING_REVIEW = "preparing_review"
INGEST_NEEDS_REVIEW = "needs_review"
INGEST_READY = "ready"
INGEST_FAILED = "failed"

INGESTION_STATUSES = frozenset(
    {
        INGEST_QUEUED,
        INGEST_CHECKING,
        INGEST_READING,
        INGEST_IMPROVING_LAYOUT,
        INGEST_READING_SCANNED,
        INGEST_PREPARING_REVIEW,
        INGEST_NEEDS_REVIEW,
        INGEST_READY,
        INGEST_FAILED,
    }
)

INGESTION_TERMINAL_STATUSES = frozenset(
    {INGEST_NEEDS_REVIEW, INGEST_READY, INGEST_FAILED}
)

_INGESTION_STATUS_LABELS = {
    INGEST_QUEUED: ("Đang chờ xử lý", "Queued"),
    INGEST_CHECKING: ("Đang kiểm tra tệp", "Checking file"),
    INGEST_READING: ("Đang đọc tài liệu", "Reading document"),
    INGEST_IMPROVING_LAYOUT: ("Đang cải thiện bố cục", "Improving layout"),
    INGEST_READING_SCANNED: ("Đang đọc trang scan", "Reading scanned pages"),
    INGEST_PREPARING_REVIEW: ("Đang chuẩn bị để kiểm tra", "Preparing review"),
    INGEST_NEEDS_REVIEW: ("Cần bạn kiểm tra", "Needs your review"),
    INGEST_READY: ("Sẵn sàng để nhập", "Ready to import"),
    INGEST_FAILED: ("Chưa xử lý được", "Could not process"),
}


def ingestion_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_INGESTION_STATUS_LABELS, code, locale=locale)


def _label(table: dict[str, tuple[str, str]], code: str, *, locale: str) -> str:
    vi, en = table.get(code, (code, code))
    return vi if locale == "vi" else en


def status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_STATUS_LABELS, code, locale=locale)


def source_label(code: str, *, locale: str = "vi") -> str:
    return _label(_SOURCE_LABELS, code, locale=locale)


def parse_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_PARSE_STATUS_LABELS, code, locale=locale)


def export_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_EXPORT_STATUS_LABELS, code, locale=locale)


# --------------------------------------------------------------------------- #
# Seed templates (idempotent insert in migration 0005)                         #
# --------------------------------------------------------------------------- #

# layout_schema captures section order + simple typography tokens. The renderer
# reads section order from the CV itself; this is metadata for the builder UI.
TEMPLATE_SEEDS: list[dict] = [
    {
        "key": "classic_one_page",
        "name_vi": "Cổ điển một trang",
        "name_en": "Classic One Page",
        "category": "classic",
        "is_premium": False,
        "layout_schema": {
            "section_order": [s["section_type"] for s in DEFAULT_SECTIONS],
            "typography": {"font": "sans", "base_pt": 11},
            "page": {"size": "A4", "max_pages": 1},
        },
    },
    {
        "key": "technical_modern",
        "name_vi": "Kỹ thuật hiện đại",
        "name_en": "Technical Modern",
        "category": "technical",
        "is_premium": False,
        "layout_schema": {
            "section_order": [
                "summary",
                "skills",
                "experience",
                "projects",
                "education",
                "certifications",
            ],
            "typography": {"font": "sans", "base_pt": 10},
            "page": {"size": "A4", "max_pages": 2},
        },
    },
    {
        "key": "data_analytics_research",
        "name_vi": "Dữ liệu & nghiên cứu",
        "name_en": "Data & Research",
        "category": "data",
        "is_premium": False,
        "layout_schema": {
            "section_order": [
                "summary",
                "skills",
                "projects",
                "experience",
                "education",
                "certifications",
            ],
            "typography": {"font": "sans", "base_pt": 10},
            "page": {"size": "A4", "max_pages": 2},
            "target_roles": [
                "Data Analyst",
                "Research Assistant",
                "Business Intelligence Intern",
            ],
            "strengths": ["metrics", "projects", "technical_skills"],
        },
    },
    {
        "key": "finance_consulting",
        "name_vi": "Tài chính & tư vấn",
        "name_en": "Finance & Consulting",
        "category": "business",
        "is_premium": False,
        "layout_schema": {
            "section_order": [
                "summary",
                "experience",
                "projects",
                "education",
                "skills",
                "awards",
            ],
            "typography": {"font": "serif", "base_pt": 10},
            "page": {"size": "A4", "max_pages": 1},
            "target_roles": [
                "Investment Analyst Intern",
                "Consulting Intern",
                "Business Analyst",
            ],
            "strengths": ["impact", "leadership", "case_projects"],
        },
    },
    {
        "key": "marketing_growth",
        "name_vi": "Marketing & tăng trưởng",
        "name_en": "Marketing & Growth",
        "category": "creative",
        "is_premium": False,
        "layout_schema": {
            "section_order": [
                "summary",
                "projects",
                "experience",
                "skills",
                "education",
                "awards",
            ],
            "typography": {"font": "sans", "base_pt": 11},
            "page": {"size": "A4", "max_pages": 2},
            "target_roles": [
                "Marketing Intern",
                "Growth Intern",
                "Content Strategist",
            ],
            "strengths": ["portfolio", "campaign_metrics", "communication"],
        },
    },
    {
        "key": "healthcare_impact",
        "name_vi": "Y tế & tác động xã hội",
        "name_en": "Healthcare & Impact",
        "category": "healthcare",
        "is_premium": False,
        "layout_schema": {
            "section_order": [
                "summary",
                "education",
                "experience",
                "projects",
                "certifications",
                "skills",
            ],
            "typography": {"font": "sans", "base_pt": 11},
            "page": {"size": "A4", "max_pages": 2},
            "target_roles": [
                "Clinical Research Intern",
                "Public Health Intern",
                "Social Impact Fellow",
            ],
            "strengths": ["service", "research", "certifications"],
        },
    },
    {
        "key": "business_premium",
        "name_vi": "Doanh nghiệp cao cấp",
        "name_en": "Business Premium",
        "category": "business",
        "is_premium": True,
        "layout_schema": {
            "section_order": [
                "summary",
                "experience",
                "education",
                "skills",
                "awards",
                "languages",
            ],
            "typography": {"font": "serif", "base_pt": 11},
            "page": {"size": "A4", "max_pages": 2},
        },
    },
]
