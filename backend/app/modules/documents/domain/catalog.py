"""Documents / CV Studio vocabulary, defaults, labels, and template seeds.

Pure domain constants and helpers — no I/O. Friendly vi/en labels are paired with
every raw enum code so the API never ships a raw code alone
(``.claude/rules/backend.md``: "No raw enum codes in end-user responses").
"""

from __future__ import annotations

from app.modules.documents.domain import themes

# --------------------------------------------------------------------------- #
# CV creation modes (``docs/API_CONTRACTS.md`` Create CV)                       #
# --------------------------------------------------------------------------- #

# The ONLY supported CV creation paths (owner cleanup 2026-07-05):
#   - blank_template     : create from a (free) template — the direct create path.
#   - duplicate_existing : duplicate an existing CV.
#   - uploaded_import    : the ingestion -> import path (create_cv_from_sections);
#                          NOT selectable via the generic create_cv dispatcher.
# AI is an in-builder ASSIST (suggestion / ai-edit-command), never a creation mode.
CREATION_BLANK = "blank_template"
CREATION_UPLOADED_IMPORT = "uploaded_import"
CREATION_DUPLICATE = "duplicate_existing"

# The full set of supported creation modes.
ALL_CREATION_MODES = frozenset(
    {
        CREATION_BLANK,
        CREATION_UPLOADED_IMPORT,
        CREATION_DUPLICATE,
    }
)

# source_type stored on cv_profiles (``docs/DATA_MODEL.md`` §7).
SOURCE_TYPE_FOR_MODE = {
    CREATION_BLANK: "blank_template",
    CREATION_UPLOADED_IMPORT: "uploaded_import",
    CREATION_DUPLICATE: "duplicate_existing",
}

# --------------------------------------------------------------------------- #
# CV section types                                                             #
# --------------------------------------------------------------------------- #

SECTION_TYPES = frozenset(
    {
        "header",
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
        "custom",
    }
)

# The header/contact section holds the person's name + contact facts so a CV can
# render a real header. Its ``content_json`` is neither ``entries`` nor ``items``:
#   {"name","headline","email","phone","location","links":[{"label","url"}]}
HEADER_SECTION_TYPE = "header"

# Default blank-template section skeleton (ASCII titles; content empty). The
# header is always first so a CV can show the owner's name + contact.
DEFAULT_SECTIONS: list[dict] = [
    {"section_type": "header", "title": "Header", "sort_order": 5},
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

# In-builder CV AI tasks. The profile-sourced tasks (``draft_cv_from_profile`` /
# ``fill_cv_template_from_sources``) were removed with the identity-only profile
# cleanup (owner decision 2026-07-06): the profile no longer holds CV-usable career
# content, so those tasks had nothing to draft/fill from. Every remaining task
# grounds on the CV itself, an uploaded-CV extraction, a source CV, or pasted notes.
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
    # Legacy tasks kept in the label map only so any stored suggestion row from
    # the retired profile-sourced tasks still renders a sensible label (never a
    # raw code); they are no longer in ``AI_TASK_TYPES`` and cannot be requested.
    "draft_cv_from_profile": ("CV đã tạo bằng AI", "AI-drafted CV"),
    "fill_cv_template_from_sources": ("CV đã điền bằng AI", "AI-filled CV"),
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
    # A CV promoted into the library ("Lưu vào thư viện CV" / upload import) is
    # analyzed, matching-ready, and usable for apply / job-fit — the label reflects
    # that it is READY TO APPLY, not merely "ready" (design spec §7).
    CV_READY: ("Sẵn sàng ứng tuyển", "Ready"),
    CV_ARCHIVED: ("Đã lưu trữ", "Archived"),
}

# Supported source types get a specific label. Legacy strings (``profile_import`` /
# ``notes_import`` / ``ai_draft``) may still exist on old ``cv_profiles`` rows, so we
# keep robust generic labels for them — ``source_label`` must never KeyError/raise on
# a stored value from a retired creation mode.
_SOURCE_LABELS = {
    "builder": ("Tự tạo", "Builder"),
    "blank_template": ("Tạo từ mẫu", "From template"),
    "uploaded_import": ("Nhập từ CV tải lên", "Imported from upload"),
    "duplicate_existing": ("Bản sao", "Duplicated"),
    # Retired creation modes — kept only so legacy rows render a sensible label.
    "profile_import": ("CV đã tạo", "Created CV"),
    "notes_import": ("CV đã tạo", "Created CV"),
    "ai_draft": ("CV đã tạo", "Created CV"),
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

INGESTION_TERMINAL_STATUSES = frozenset({INGEST_NEEDS_REVIEW, INGEST_READY, INGEST_FAILED})

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
    """Friendly source label. Robust for legacy/unknown source_type strings that
    may already exist in the DB (retired ``profile_import`` / ``notes_import`` /
    ``ai_draft`` modes): a value not in the table returns a sensible generic label
    instead of raising or leaking the raw code."""

    vi, en = _SOURCE_LABELS.get(code, ("CV đã tạo", "Created CV"))
    return vi if locale == "vi" else en


def parse_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_PARSE_STATUS_LABELS, code, locale=locale)


def export_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_EXPORT_STATUS_LABELS, code, locale=locale)


# --------------------------------------------------------------------------- #
# Seed templates (idempotent insert in migration 0005; upgraded in 0065)        #
# --------------------------------------------------------------------------- #
#
# Each template now carries a FULL visual theme in ``layout_schema`` (layout kind,
# palette, typography, photo policy, section styling, region assignment, and
# default order). The theme is the single source of visual truth consumed by the
# frontend ``<CvDocument/>`` renderer and the PDF renderer alike
# (``domain.themes`` / design spec §3, §5). Keys are stable — a new admin-published
# version bumps ``version`` without renaming.

# name_vi / name_en / category metadata for each built-in theme key. All templates
# are free (the premium concept was removed in the 2026-07-05 owner cleanup). The
# visual theme itself lives in ``domain.themes.BUILTIN_THEMES``.
_TEMPLATE_META: list[dict] = [
    {
        "key": "classic_ats",
        "name_vi": "Cổ điển ATS",
        "name_en": "Classic ATS",
        "category": "classic",
    },
    {
        "key": "modern_navy",
        "name_vi": "Hiện đại Navy",
        "name_en": "Modern Navy",
        "category": "professional",
    },
    {
        "key": "modern_teal",
        "name_vi": "Hiện đại Teal",
        "name_en": "Modern Teal",
        "category": "tech",
    },
    {
        "key": "minimal_mono",
        "name_vi": "Tối giản",
        "name_en": "Minimal",
        "category": "minimal",
    },
    {
        "key": "bold_header",
        "name_vi": "Tiêu đề nổi bật",
        "name_en": "Bold Header",
        "category": "professional",
    },
    {
        "key": "elegant_serif",
        "name_vi": "Thanh lịch Serif",
        "name_en": "Elegant Serif",
        "category": "business",
    },
    {
        "key": "creative_twotone",
        "name_vi": "Sáng tạo 2 tông",
        "name_en": "Creative Two-Tone",
        "category": "creative",
    },
    {
        "key": "tech_chips",
        "name_vi": "Kỹ thuật Chips",
        "name_en": "Tech Chips",
        "category": "tech",
    },
]

TEMPLATE_SEEDS: list[dict] = [
    {**meta, "layout_schema": themes.theme_for(meta["key"])} for meta in _TEMPLATE_META
]
