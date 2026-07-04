"""Billing application errors, mapped to the API error envelope.

All carry a stable, user-safe code from the ``docs/API_CONTRACTS.md`` families;
internal details and raw enum codes never reach ``message``.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class IllegalSubscriptionTransitionError(ConflictError):
    """A subscription lifecycle event is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại."

    def __init__(self, *, event: str) -> None:
        super().__init__(details={"reason": "illegal_transition", "event": event})


class SubscriptionVersionConflictError(ConflictError):
    """Optimistic-concurrency mismatch on a subscription update/transition."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(details={"reason": "version_conflict"})


class SubscriptionExistsError(ConflictError):
    """The principal already has a pending/active subscription (one in-flight)."""

    message = "Bạn đã có một gói đăng ký đang chờ hoặc đang hiệu lực."

    def __init__(self) -> None:
        super().__init__(details={"reason": "subscription_exists"})


class PlanAudienceMismatchError(ValidationFailedError):
    """The chosen plan's audience does not match the requesting principal kind."""

    message = "Gói dịch vụ này không áp dụng cho loại tài khoản của bạn."

    def __init__(self) -> None:
        super().__init__(details={"reason": "plan_audience_mismatch"})


class InvalidPlanError(ValidationFailedError):
    """The chosen plan is unknown or not available for subscription."""

    message = "Gói dịch vụ không hợp lệ. Vui lòng chọn lại."

    def __init__(self) -> None:
        super().__init__(details={"reason": "invalid_plan", "field": "plan_id"})


class PaymentReferenceRequiredError(ValidationFailedError):
    """``mark_paid`` attempted without a bank-transfer reference."""

    message = "Cần nhập mã tham chiếu chuyển khoản để ghi nhận thanh toán."

    def __init__(self) -> None:
        super().__init__(details={"reason": "reference_required"})
