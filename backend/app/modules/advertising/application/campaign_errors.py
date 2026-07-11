"""Ad-campaign application errors, mapped to the API error envelope.

All carry a stable, user-safe code from the ``docs/API_CONTRACTS.md`` families;
internal details and raw enum codes never reach ``message``.
"""

from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class IllegalCampaignTransitionError(ConflictError):
    """A campaign lifecycle event is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại của chiến dịch."

    def __init__(self, *, event: str) -> None:
        super().__init__(details={"reason": "illegal_transition", "event": event})


class CampaignVersionConflictError(ConflictError):
    """Optimistic-concurrency mismatch on a campaign update/transition."""

    message = "Nội dung đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self) -> None:
        super().__init__(details={"reason": "version_conflict"})


class CampaignNotEditableError(ConflictError):
    """Edit/delete attempted on a campaign that is not draft/rejected."""

    message = "Chỉ có thể chỉnh sửa chiến dịch ở trạng thái nháp hoặc bị từ chối."

    def __init__(self) -> None:
        super().__init__(details={"reason": "not_editable"})


class CampaignDisclosureRequiredError(ValidationFailedError):
    """Submit attempted without confirming the non-removable paid disclosure."""

    message = "Bạn cần xác nhận nhãn công khai 'Được tài trợ' trước khi gửi duyệt."

    def __init__(self) -> None:
        super().__init__(details={"reason": "disclosure_required"})


class ActiveCampaignLimitError(ConflictError):
    """The org's concurrent in-flight campaign cap would be exceeded."""

    message = "Bạn đã đạt số lượng chiến dịch quảng cáo tối đa đang chạy."

    def __init__(self, *, limit: int) -> None:
        super().__init__(details={"reason": "active_campaign_limit", "limit": limit})


class InvalidCampaignFieldError(ValidationFailedError):
    """A campaign field failed a vocabulary/business validation."""

    message = "Dữ liệu chiến dịch quảng cáo không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(details={"field": field})


class ForbiddenTargetingError(ValidationFailedError):
    """Targeting used a forbidden (GPS / sensitive category) dimension."""

    message = (
        "Nhắm mục tiêu không được dùng vị trí chính xác (GPS) hoặc thuộc tính nhạy cảm."
    )

    def __init__(self, *, dimension: str) -> None:
        super().__init__(details={"reason": "forbidden_targeting", "dimension": dimension})


class UnknownTargetingError(ValidationFailedError):
    """Targeting used an unrecognized (non-coarse) dimension key."""

    message = "Nhắm mục tiêu chỉ hỗ trợ vị trí, ngành học và định hướng nghề nghiệp thô."

    def __init__(self, *, dimension: str) -> None:
        super().__init__(details={"reason": "unknown_targeting", "dimension": dimension})


class PaidDisclosureImmutableError(ConflictError):
    """Attempt to relabel PAID campaign inventory as curated/strategic/featured."""

    message = "Không thể đổi nhãn của chiến dịch trả phí thành nội dung tuyển chọn."

    def __init__(self) -> None:
        super().__init__(details={"reason": "paid_disclosure_immutable"})
