from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class InvalidGraphError(ValidationFailedError):
    message = "Sơ đồ quy trình không hợp lệ."

    def __init__(self, errors: list[str]) -> None:
        super().__init__(self.message, details={"reason": "invalid_graph", "errors": errors})


class FlowNotEditableError(ConflictError):
    message = "Chỉ có thể chỉnh sửa quy trình ở trạng thái nháp."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_editable"})


class FlowNotActivatableError(ConflictError):
    message = "Chỉ có thể kích hoạt quy trình ở trạng thái nháp hoặc tạm dừng."

    def __init__(self, *, from_status: str) -> None:
        super().__init__(self.message, details={"reason": "not_activatable", "status": from_status})


class MissingActivationCapabilitiesError(ValidationFailedError):
    message = "Bạn không có đủ quyền để kích hoạt quy trình này."

    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            self.message,
            details={"reason": "missing_capabilities", "missing_capabilities": missing},
        )
