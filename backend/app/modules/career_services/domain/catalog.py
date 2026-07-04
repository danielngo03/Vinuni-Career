"""Career-services vocabulary, statuses, and bilingual labels.

Pure domain constants — no I/O. Every raw status/enum code shipped to a client is
paired with a friendly vi/en label (``.claude/rules/backend.md``: "No raw enum
codes in end-user responses").
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Cohort                                                                       #
# --------------------------------------------------------------------------- #

COHORT_ACTIVE = "active"
COHORT_ARCHIVED = "archived"
COHORT_STATUSES = frozenset({COHORT_ACTIVE, COHORT_ARCHIVED})

_COHORT_STATUS_LABELS = {
    COHORT_ACTIVE: ("Đang hoạt động", "Active"),
    COHORT_ARCHIVED: ("Đã lưu trữ", "Archived"),
}

# --------------------------------------------------------------------------- #
# At-risk flag                                                                 #
# --------------------------------------------------------------------------- #

RISK_REASON_ACADEMIC = "academic_performance"
RISK_REASON_ATTENDANCE = "low_engagement"
RISK_REASON_NO_APPLICATIONS = "no_applications_submitted"
RISK_REASON_MISSED_APPOINTMENTS = "missed_appointments"
RISK_REASON_GRADUATING_UNPLACED = "graduating_unplaced"
RISK_REASON_OTHER = "other"

RISK_REASONS = frozenset(
    {
        RISK_REASON_ACADEMIC,
        RISK_REASON_ATTENDANCE,
        RISK_REASON_NO_APPLICATIONS,
        RISK_REASON_MISSED_APPOINTMENTS,
        RISK_REASON_GRADUATING_UNPLACED,
        RISK_REASON_OTHER,
    }
)

_RISK_REASON_LABELS = {
    RISK_REASON_ACADEMIC: ("Kết quả học tập", "Academic performance"),
    RISK_REASON_ATTENDANCE: ("Ít tương tác", "Low engagement"),
    RISK_REASON_NO_APPLICATIONS: (
        "Chưa nộp đơn ứng tuyển",
        "No applications submitted",
    ),
    RISK_REASON_MISSED_APPOINTMENTS: ("Bỏ lỡ lịch hẹn", "Missed appointments"),
    RISK_REASON_GRADUATING_UNPLACED: (
        "Sắp tốt nghiệp, chưa có việc",
        "Graduating, not yet placed",
    ),
    RISK_REASON_OTHER: ("Khác", "Other"),
}

RISK_SEVERITY_LOW = "low"
RISK_SEVERITY_MEDIUM = "medium"
RISK_SEVERITY_HIGH = "high"
RISK_SEVERITIES = frozenset({RISK_SEVERITY_LOW, RISK_SEVERITY_MEDIUM, RISK_SEVERITY_HIGH})

_RISK_SEVERITY_LABELS = {
    RISK_SEVERITY_LOW: ("Thấp", "Low"),
    RISK_SEVERITY_MEDIUM: ("Trung bình", "Medium"),
    RISK_SEVERITY_HIGH: ("Cao", "High"),
}

RISK_OPEN = "open"
RISK_IN_PROGRESS = "in_progress"
RISK_RESOLVED = "resolved"
RISK_DISMISSED = "dismissed"
RISK_STATUSES = frozenset({RISK_OPEN, RISK_IN_PROGRESS, RISK_RESOLVED, RISK_DISMISSED})
RISK_OPEN_STATUSES = frozenset({RISK_OPEN, RISK_IN_PROGRESS})

_RISK_STATUS_LABELS = {
    RISK_OPEN: ("Đang mở", "Open"),
    RISK_IN_PROGRESS: ("Đang xử lý", "In progress"),
    RISK_RESOLVED: ("Đã giải quyết", "Resolved"),
    RISK_DISMISSED: ("Đã bỏ qua", "Dismissed"),
}

# --------------------------------------------------------------------------- #
# CV review queue                                                             #
# --------------------------------------------------------------------------- #

CV_REVIEW_QUEUED = "queued"
CV_REVIEW_IN_REVIEW = "in_review"
CV_REVIEW_CHANGES_REQUESTED = "changes_requested"
CV_REVIEW_APPROVED = "approved"
CV_REVIEW_CLOSED = "closed"
CV_REVIEW_STATUSES = frozenset(
    {
        CV_REVIEW_QUEUED,
        CV_REVIEW_IN_REVIEW,
        CV_REVIEW_CHANGES_REQUESTED,
        CV_REVIEW_APPROVED,
        CV_REVIEW_CLOSED,
    }
)
CV_REVIEW_OPEN_STATUSES = frozenset(
    {CV_REVIEW_QUEUED, CV_REVIEW_IN_REVIEW, CV_REVIEW_CHANGES_REQUESTED}
)

_CV_REVIEW_STATUS_LABELS = {
    CV_REVIEW_QUEUED: ("Đang chờ duyệt", "Queued"),
    CV_REVIEW_IN_REVIEW: ("Đang xem xét", "In review"),
    CV_REVIEW_CHANGES_REQUESTED: ("Yêu cầu chỉnh sửa", "Changes requested"),
    CV_REVIEW_APPROVED: ("Đã duyệt", "Approved"),
    CV_REVIEW_CLOSED: ("Đã đóng", "Closed"),
}

CV_REVIEW_PRIORITY_LOW = "low"
CV_REVIEW_PRIORITY_NORMAL = "normal"
CV_REVIEW_PRIORITY_HIGH = "high"
CV_REVIEW_PRIORITY_URGENT = "urgent"
CV_REVIEW_PRIORITIES = frozenset(
    {
        CV_REVIEW_PRIORITY_LOW,
        CV_REVIEW_PRIORITY_NORMAL,
        CV_REVIEW_PRIORITY_HIGH,
        CV_REVIEW_PRIORITY_URGENT,
    }
)

_CV_REVIEW_PRIORITY_LABELS = {
    CV_REVIEW_PRIORITY_LOW: ("Thấp", "Low"),
    CV_REVIEW_PRIORITY_NORMAL: ("Bình thường", "Normal"),
    CV_REVIEW_PRIORITY_HIGH: ("Cao", "High"),
    CV_REVIEW_PRIORITY_URGENT: ("Khẩn cấp", "Urgent"),
}

# --------------------------------------------------------------------------- #
# Appointments                                                                 #
# --------------------------------------------------------------------------- #

APPT_REQUESTED = "requested"
APPT_CONFIRMED = "confirmed"
APPT_COMPLETED = "completed"
APPT_CANCELLED = "cancelled"
APPT_NO_SHOW = "no_show"
APPT_STATUSES = frozenset(
    {APPT_REQUESTED, APPT_CONFIRMED, APPT_COMPLETED, APPT_CANCELLED, APPT_NO_SHOW}
)
# Statuses that hold a counselor's calendar slot (used for the double-booking guard).
APPT_ACTIVE_STATUSES = frozenset({APPT_REQUESTED, APPT_CONFIRMED})

_APPT_STATUS_LABELS = {
    APPT_REQUESTED: ("Đã yêu cầu", "Requested"),
    APPT_CONFIRMED: ("Đã xác nhận", "Confirmed"),
    APPT_COMPLETED: ("Đã hoàn tất", "Completed"),
    APPT_CANCELLED: ("Đã hủy", "Cancelled"),
    APPT_NO_SHOW: ("Vắng mặt", "No-show"),
}

APPT_MODE_IN_PERSON = "in_person"
APPT_MODE_VIDEO = "video"
APPT_MODE_PHONE = "phone"
APPT_MODES = frozenset({APPT_MODE_IN_PERSON, APPT_MODE_VIDEO, APPT_MODE_PHONE})

_APPT_MODE_LABELS = {
    APPT_MODE_IN_PERSON: ("Trực tiếp", "In person"),
    APPT_MODE_VIDEO: ("Video call", "Video call"),
    APPT_MODE_PHONE: ("Điện thoại", "Phone"),
}

# --------------------------------------------------------------------------- #
# Employer relationship notes                                                 #
# --------------------------------------------------------------------------- #

NOTE_CATEGORY_GENERAL = "general"
NOTE_CATEGORY_PARTNERSHIP = "partnership"
NOTE_CATEGORY_HIRING_EVENT = "hiring_event"
NOTE_CATEGORY_FEEDBACK = "feedback"
NOTE_CATEGORY_ESCALATION = "escalation"
NOTE_CATEGORIES = frozenset(
    {
        NOTE_CATEGORY_GENERAL,
        NOTE_CATEGORY_PARTNERSHIP,
        NOTE_CATEGORY_HIRING_EVENT,
        NOTE_CATEGORY_FEEDBACK,
        NOTE_CATEGORY_ESCALATION,
    }
)

_NOTE_CATEGORY_LABELS = {
    NOTE_CATEGORY_GENERAL: ("Chung", "General"),
    NOTE_CATEGORY_PARTNERSHIP: ("Hợp tác", "Partnership"),
    NOTE_CATEGORY_HIRING_EVENT: ("Sự kiện tuyển dụng", "Hiring event"),
    NOTE_CATEGORY_FEEDBACK: ("Phản hồi", "Feedback"),
    NOTE_CATEGORY_ESCALATION: ("Cần lưu ý", "Escalation"),
}

NOTE_VISIBILITY_COUNSELOR_ONLY = "counselor_only"
NOTE_VISIBILITY_DEPARTMENT = "department"
NOTE_VISIBILITY_ALL_STAFF = "all_staff"
NOTE_VISIBILITIES = frozenset(
    {
        NOTE_VISIBILITY_COUNSELOR_ONLY,
        NOTE_VISIBILITY_DEPARTMENT,
        NOTE_VISIBILITY_ALL_STAFF,
    }
)

_NOTE_VISIBILITY_LABELS = {
    NOTE_VISIBILITY_COUNSELOR_ONLY: ("Chỉ mình tôi", "Only me"),
    NOTE_VISIBILITY_DEPARTMENT: ("Trong phòng ban", "Department"),
    NOTE_VISIBILITY_ALL_STAFF: ("Toàn bộ nhân viên", "All staff"),
}

# --------------------------------------------------------------------------- #
# Intervention records                                                         #
# --------------------------------------------------------------------------- #

INTERVENTION_ADVISING_SESSION = "advising_session"
INTERVENTION_REFERRAL = "referral"
INTERVENTION_WORKSHOP_RECOMMENDATION = "workshop_recommendation"
INTERVENTION_AT_RISK_OUTREACH = "at_risk_outreach"
INTERVENTION_CV_REVIEW_FOLLOWUP = "cv_review_followup"
INTERVENTION_EMPLOYER_REFERRAL = "employer_referral"
INTERVENTION_OTHER = "other"
INTERVENTION_TYPES = frozenset(
    {
        INTERVENTION_ADVISING_SESSION,
        INTERVENTION_REFERRAL,
        INTERVENTION_WORKSHOP_RECOMMENDATION,
        INTERVENTION_AT_RISK_OUTREACH,
        INTERVENTION_CV_REVIEW_FOLLOWUP,
        INTERVENTION_EMPLOYER_REFERRAL,
        INTERVENTION_OTHER,
    }
)

_INTERVENTION_TYPE_LABELS = {
    INTERVENTION_ADVISING_SESSION: ("Buổi tư vấn", "Advising session"),
    INTERVENTION_REFERRAL: ("Giới thiệu", "Referral"),
    INTERVENTION_WORKSHOP_RECOMMENDATION: (
        "Đề xuất hội thảo",
        "Workshop recommendation",
    ),
    INTERVENTION_AT_RISK_OUTREACH: ("Liên hệ sinh viên có rủi ro", "At-risk outreach"),
    INTERVENTION_CV_REVIEW_FOLLOWUP: ("Theo dõi sau duyệt CV", "CV review follow-up"),
    INTERVENTION_EMPLOYER_REFERRAL: ("Giới thiệu nhà tuyển dụng", "Employer referral"),
    INTERVENTION_OTHER: ("Khác", "Other"),
}

INTERVENTION_OUTCOME_PENDING = "no_outcome_yet"
INTERVENTION_OUTCOME_IMPROVED = "improved"
INTERVENTION_OUTCOME_NO_CHANGE = "no_change"
INTERVENTION_OUTCOME_ESCALATED = "escalated"
INTERVENTION_OUTCOME_RESOLVED = "resolved"
INTERVENTION_OUTCOMES = frozenset(
    {
        INTERVENTION_OUTCOME_PENDING,
        INTERVENTION_OUTCOME_IMPROVED,
        INTERVENTION_OUTCOME_NO_CHANGE,
        INTERVENTION_OUTCOME_ESCALATED,
        INTERVENTION_OUTCOME_RESOLVED,
    }
)

_INTERVENTION_OUTCOME_LABELS = {
    INTERVENTION_OUTCOME_PENDING: ("Chưa có kết quả", "No outcome yet"),
    INTERVENTION_OUTCOME_IMPROVED: ("Cải thiện", "Improved"),
    INTERVENTION_OUTCOME_NO_CHANGE: ("Không thay đổi", "No change"),
    INTERVENTION_OUTCOME_ESCALATED: ("Đã chuyển cấp", "Escalated"),
    INTERVENTION_OUTCOME_RESOLVED: ("Đã giải quyết", "Resolved"),
}


def _label(table: dict[str, tuple[str, str]], code: str, *, locale: str) -> str:
    vi, en = table.get(code, (code, code))
    return vi if locale == "vi" else en


def cohort_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_COHORT_STATUS_LABELS, code, locale=locale)


def risk_reason_label(code: str, *, locale: str = "vi") -> str:
    return _label(_RISK_REASON_LABELS, code, locale=locale)


def risk_severity_label(code: str, *, locale: str = "vi") -> str:
    return _label(_RISK_SEVERITY_LABELS, code, locale=locale)


def risk_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_RISK_STATUS_LABELS, code, locale=locale)


def cv_review_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_CV_REVIEW_STATUS_LABELS, code, locale=locale)


def cv_review_priority_label(code: str, *, locale: str = "vi") -> str:
    return _label(_CV_REVIEW_PRIORITY_LABELS, code, locale=locale)


def appointment_status_label(code: str, *, locale: str = "vi") -> str:
    return _label(_APPT_STATUS_LABELS, code, locale=locale)


def appointment_mode_label(code: str, *, locale: str = "vi") -> str:
    return _label(_APPT_MODE_LABELS, code, locale=locale)


def note_category_label(code: str, *, locale: str = "vi") -> str:
    return _label(_NOTE_CATEGORY_LABELS, code, locale=locale)


def note_visibility_label(code: str, *, locale: str = "vi") -> str:
    return _label(_NOTE_VISIBILITY_LABELS, code, locale=locale)


def intervention_type_label(code: str, *, locale: str = "vi") -> str:
    return _label(_INTERVENTION_TYPE_LABELS, code, locale=locale)


def intervention_outcome_label(code: str, *, locale: str = "vi") -> str:
    return _label(_INTERVENTION_OUTCOME_LABELS, code, locale=locale)
