"""Opportunities-module application errors.

All map to the shared API error envelope. ``details.reason`` carries a stable,
user-safe machine token (never a raw DB/enum code) for clients that branch on it.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class IllegalJobTransitionError(ConflictError):
    """Requested lifecycle transition is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại của tin tuyển dụng."

    def __init__(self, *, event: str) -> None:
        super().__init__(
            self.message,
            details={"reason": "illegal_transition", "event": event},
        )


class JobNotEditableError(ConflictError):
    """The job is in a state/field that cannot be edited right now.

    ``reason`` defaults to the generic ``not_editable`` (wrong status, e.g.
    closed/pending_review), but a caller may pass a more specific reason such
    as ``screening_locked_after_publish`` (B-552 amendment policy: screening
    questions are frozen once a job goes live because existing applications'
    ``screening_answers`` reference the question set by id/order).
    """

    message = "Tin tuyển dụng này không thể chỉnh sửa ở trạng thái hiện tại."

    def __init__(self, *, reason: str = "not_editable") -> None:
        super().__init__(self.message, details={"reason": reason})


class JobQualityCheckFailedError(ValidationFailedError):
    """The JD quality-check rubric found blocking issues; submit is refused.

    ``details.issues`` carries the full structured issue list (blocking +
    advisory) so the client can render every finding, not just the first
    blocking one.
    """

    message = (
        "Tin tuyển dụng chưa đạt yêu cầu chất lượng tối thiểu. Vui lòng "
        "khắc phục các vấn đề được liệt kê trước khi gửi duyệt."
    )

    def __init__(self, *, issues: list[dict]) -> None:
        super().__init__(
            self.message,
            details={"reason": "jd_quality_check_failed", "issues": issues},
        )


class JobVersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent edit."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "version_conflict"})


class InvalidJobFieldError(ValidationFailedError):
    """A job field value is outside the allowed vocabulary."""

    message = "Dữ liệu tin tuyển dụng không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(self.message, details={"reason": "invalid_field", "field": field})


class JobAlreadyClaimedError(ConflictError):
    """Another moderator already claimed this job for review."""

    message = "Tin tuyển dụng này đang được người kiểm duyệt khác xử lý."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "already_claimed"})


class InvalidModerationReasonError(ValidationFailedError):
    """An unrecognized structured reason code, or ``other`` without a note."""

    message = "Vui lòng chọn lý do hợp lệ (hoặc nhập lý do cụ thể cho 'Lý do khác')."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_reason_code"})


class InvalidIndustryFilterError(ValidationFailedError):
    """Canonical deepest-scope industry filter (`GET /jobs`) is malformed.

    ``details.reason`` is one of:
    - ``multiple_scope``: more than one of industry_group_id/industry_id/
      specialization_id was provided (only one deepest scope at a time).
    - ``not_found``: the referenced Industry id does not exist or is inactive.
    - ``level_mismatch``: the referenced Industry exists but its `level` does
      not match the query param slot (e.g. a level-2 id passed as
      `industry_group_id`).
    """

    message = "Bộ lọc ngành nghề không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, reason: str, param: str | None = None) -> None:
        details: dict = {"reason": reason}
        if param is not None:
            details["param"] = param
        super().__init__(self.message, details=details)
