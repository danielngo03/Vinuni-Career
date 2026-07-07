"""Documents-module application errors mapped to the shared API error envelope.

``details.reason`` carries a stable, user-safe machine token (never a raw DB/enum
code or internal parser detail) for clients that branch on it.
"""

from __future__ import annotations

from app.shared.exceptions import (
    ConflictError,
    QuotaExceededError,
    ValidationFailedError,
)


class CvQuotaReachedError(QuotaExceededError):
    """The owner's active CV library is at/over its tier limit.

    Maps to ``409 QUOTA_EXCEEDED`` (docs/API_CONTRACTS.md "CV Library And Quota").
    ``details`` carries the user-safe count/limit plus recovery ``actions`` so the
    UI can offer archive/delete/duplicate-into-draft/request-more/upgrade rather
    than silently failing (docs/BUSINESS_LOGIC.md §4B.4 / §5).
    """

    message = (
        "Bạn đã đạt giới hạn số CV đang hoạt động. "
        "Hãy lưu trữ hoặc xóa bớt một CV trước khi tạo CV mới."
    )

    def __init__(self, *, current: int, limit: int) -> None:
        super().__init__(
            self.message,
            details={
                "reason": "cv_quota_reached",
                "current": current,
                "limit": limit,
                "actions": [
                    "archive_existing",
                    "delete_draft",
                    "request_more_quota",
                    "upgrade",
                ],
            },
        )


class CvVersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent CV section edit."""

    message = "CV này đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu."

    def __init__(self, *, current_version: int) -> None:
        super().__init__(
            self.message,
            details={"reason": "version_conflict", "current_version": current_version},
        )


class InvalidCvFieldError(ValidationFailedError):
    """A CV field value is outside the allowed vocabulary."""

    message = "Dữ liệu CV không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(self.message, details={"reason": "invalid_field", "field": field})


class CvEmptyError(ValidationFailedError):
    """Finalize attempted on an empty CV (no header name, no real section content).

    Maps to ``422 VALIDATION_FAILED`` with ``details.reason = "cv_empty"`` so the
    builder can show inline guidance ("Add your name or at least one section") and
    block the finalize action instead of committing a blank library CV.
    """

    message = (
        "CV này chưa có nội dung. Hãy thêm tên hoặc ít nhất một mục có thông tin "
        "trước khi lưu vào thư viện."
    )

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "cv_empty"})


class CvNotInLibraryError(ConflictError):
    """Apply/snapshot attempted with a CV that is not committed to the library.

    A draft CV is not analyzed/matchable and cannot be submitted with an
    application (design spec 2026-07-05). Maps to ``409 CONFLICT`` with
    ``details.reason = "cv_not_in_library"`` so the apply picker can steer the
    student to finalize the CV first.
    """

    message = (
        "CV này chưa ở trong thư viện. Hãy lưu CV vào thư viện trước khi ứng tuyển."
    )

    def __init__(self, *, status: str) -> None:
        super().__init__(
            self.message,
            details={"reason": "cv_not_in_library", "status": status},
        )


class CreationModeNotAvailableError(ValidationFailedError):
    """The requested CV creation mode is not available in this slice (AI draft)."""

    message = "Chế độ tạo CV bằng AI sắp ra mắt. Hãy chọn một cách tạo CV khác."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "ai_mode_unavailable"})


class CvSourceRequiredError(ValidationFailedError):
    """A creation mode is missing its required source reference."""

    message = "Thiếu nguồn dữ liệu cần thiết để tạo CV theo cách này."

    def __init__(self, *, field: str) -> None:
        super().__init__(self.message, details={"reason": "source_required", "field": field})


class InvalidTaskTypeError(ValidationFailedError):
    """The requested AI task_type is not a supported CV AI task."""

    message = "Loại yêu cầu AI không hợp lệ."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_task_type"})


class AiSourceRequiredError(ValidationFailedError):
    """An AI task is missing a required input (target section or job)."""

    message = "Thiếu thông tin cần thiết cho yêu cầu AI này."

    def __init__(self, *, field: str) -> None:
        super().__init__(
            self.message, details={"reason": "ai_source_required", "field": field}
        )


class FactConfirmationRequiredError(ValidationFailedError):
    """Accept attempted on a suggestion that needs explicit fact confirmation."""

    message = (
        "Gợi ý này chứa thông tin cần bạn xác nhận tính chính xác trước khi áp dụng."
    )

    def __init__(self) -> None:
        super().__init__(
            self.message, details={"reason": "fact_confirmation_required"}
        )


class SuggestionNotPendingError(ConflictError):
    """The suggestion has already been resolved (accepted/rejected/expired)."""

    message = "Gợi ý này đã được xử lý trước đó."

    def __init__(self, *, status: str) -> None:
        super().__init__(
            self.message, details={"reason": "suggestion_not_pending", "status": status}
        )


class SuggestionNotApplicableError(ValidationFailedError):
    """The suggestion is advisory-only and cannot be applied to the CV."""

    message = "Gợi ý này chỉ mang tính tư vấn và không thể áp dụng trực tiếp."

    def __init__(self) -> None:
        super().__init__(
            self.message, details={"reason": "suggestion_not_applicable"}
        )


class ExportNotReadyError(ValidationFailedError):
    """A download was requested before the export finished rendering."""

    message = "Bản xuất CV chưa sẵn sàng để tải. Vui lòng thử lại sau giây lát."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "export_not_ready"})


class InvalidCropRectError(ValidationFailedError):
    """A photo crop rectangle is missing, malformed, or out of the [0,1] bounds."""

    message = "Vùng cắt ảnh không hợp lệ. Vui lòng chọn lại vùng cắt."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_crop_rect"})


class InvalidPhotoFileError(ValidationFailedError):
    """The uploaded photo is missing, oversized, or not a supported image type."""

    message = "Ảnh không hợp lệ. Vui lòng chọn tệp JPG, PNG hoặc WEBP dưới giới hạn cho phép."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "invalid_photo_file"})


class FactConfirmationFieldsRequiredError(ValidationFailedError):
    """Ingestion needs-review fields must be individually confirmed/edited or the
    student must pass a blanket ``fact_confirmation`` before import."""

    message = (
        "Vui lòng xác nhận hoặc chỉnh sửa các trường cần kiểm tra trước khi nhập."
    )

    def __init__(self, *, fields: list[str]) -> None:
        super().__init__(
            self.message,
            details={"reason": "fact_confirmation_required", "fields": fields},
        )


class UploadRejectedError(ValidationFailedError):
    """An upload failed a hard pre-storage gate (size/type/security).

    Carries the user-safe ``quality_code`` and friendly message produced by the
    deterministic validator (``app.ai.extraction.cv_validation``).
    """

    def __init__(self, *, quality_code: str, message: str, next_actions: list[str]) -> None:
        super().__init__(
            message,
            details={"reason": "upload_rejected", "quality_code": quality_code,
                     "next_actions": next_actions},
        )
