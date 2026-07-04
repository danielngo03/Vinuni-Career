"""Advertising application errors, mapped to the API error envelope.

All carry a stable, user-safe code from the ``docs/API_CONTRACTS.md`` families;
internal details and raw enum codes never reach ``message``.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class IllegalPlacementTransitionError(ConflictError):
    """An advertising lifecycle event is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại."

    def __init__(self, *, event: str) -> None:
        super().__init__(details={"reason": "illegal_transition", "event": event})


class PlacementVersionConflictError(ConflictError):
    """Optimistic-concurrency mismatch on a placement update/transition."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(details={"reason": "version_conflict"})


class PlacementNotEditableError(ConflictError):
    """Edit/delete attempted on a placement that is not draft/rejected."""

    message = "Chỉ có thể chỉnh sửa yêu cầu ở trạng thái nháp hoặc bị từ chối."

    def __init__(self) -> None:
        super().__init__(details={"reason": "not_editable"})


class DisclosureRequiredError(ValidationFailedError):
    """Submit attempted without confirming the non-removable sponsored label."""

    message = (
        "Bạn cần xác nhận nhãn công khai tài trợ/nổi bật trước khi gửi yêu cầu."
    )

    def __init__(self) -> None:
        super().__init__(details={"reason": "disclosure_required"})


class ActivePlacementLimitError(ConflictError):
    """The org's concurrent in-flight placement cap would be exceeded."""

    message = "Bạn đã đạt số lượng chiến dịch quảng cáo đang chạy tối đa."

    def __init__(self, *, limit: int) -> None:
        super().__init__(details={"reason": "active_placement_limit", "limit": limit})


class PlacementExistsError(ConflictError):
    """Another live placement already covers this target."""

    message = "Mục tiêu này đã có một yêu cầu quảng cáo đang hoạt động."

    def __init__(self) -> None:
        super().__init__(details={"reason": "placement_exists"})


class InvalidPlacementFieldError(ValidationFailedError):
    """A placement field failed a vocabulary/business validation."""

    message = "Dữ liệu yêu cầu quảng cáo không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(details={"field": field})


class InvalidCreativeFieldError(ValidationFailedError):
    """A creative field (slot/focal/disclosure) failed validation."""

    message = "Dữ liệu banner quảng cáo không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(details={"field": field})


class PlacementAlreadyClaimedError(ConflictError):
    """Another moderator already claimed this placement for review."""

    message = "Yêu cầu quảng cáo này đang được người kiểm duyệt khác xử lý."

    def __init__(self) -> None:
        super().__init__(details={"reason": "already_claimed"})


class InvalidModerationReasonError(ValidationFailedError):
    """An unrecognized structured reason code, or ``other`` without a note."""

    message = "Vui lòng chọn lý do hợp lệ (hoặc nhập lý do cụ thể cho 'Lý do khác')."

    def __init__(self) -> None:
        super().__init__(details={"reason": "invalid_reason_code"})


class PaidDisclosureImmutableError(ConflictError):
    """Attempt to relabel PAID inventory as curated/strategic/featured.

    Paid placements must keep the non-removable paid disclosure — they can never
    be downgraded to an editorial/partnership class that hides the paid nature.
    """

    message = "Không thể đổi nhãn của nội dung trả phí thành nội dung tuyển chọn."

    def __init__(self) -> None:
        super().__init__(details={"reason": "paid_disclosure_immutable"})
