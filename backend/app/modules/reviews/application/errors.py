"""Reviews module errors — user-safe, mapped to standard envelopes (ADR-0013)."""

from __future__ import annotations

from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)


class ReviewNotEligibleError(PermissionDeniedError):
    message = "Bạn cần có tương tác tuyển dụng với doanh nghiệp này để viết đánh giá."

    def __init__(self) -> None:
        super().__init__(details={"reason": "not_eligible"})


class ReviewAlreadyExistsError(ConflictError):
    message = "Bạn đã đánh giá doanh nghiệp này. Hãy chỉnh sửa đánh giá hiện có."

    def __init__(self) -> None:
        super().__init__(details={"reason": "review_exists"})


class ReviewSelfNotAllowedError(PermissionDeniedError):
    message = "Bạn không thể đánh giá tổ chức của chính mình."

    def __init__(self) -> None:
        super().__init__(details={"reason": "self_review"})


class InsufficientReviewContentError(ValidationFailedError):
    message = "Nội dung đánh giá quá ngắn. Vui lòng viết chi tiết hơn."

    def __init__(self) -> None:
        super().__init__(details={"reason": "insufficient_content"})


class InvalidReviewFieldError(ValidationFailedError):
    def __init__(self, field: str) -> None:
        super().__init__(details={"reason": "invalid_field", "field": field})


class ReviewStateConflictError(ConflictError):
    message = "Đánh giá đã thay đổi trạng thái. Vui lòng tải lại."

    def __init__(self) -> None:
        super().__init__(details={"reason": "state_conflict"})


class RemovalReasonInvalidError(ValidationFailedError):
    message = "Lý do gỡ bỏ không hợp lệ. Ý kiến tiêu cực trung thực không thể bị gỡ."

    def __init__(self) -> None:
        super().__init__(details={"reason": "removal_reason_invalid"})
