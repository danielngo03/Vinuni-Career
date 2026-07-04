from __future__ import annotations

from app.shared.exceptions import ConflictError, ValidationFailedError


class InvalidRoutingGraphError(ValidationFailedError):
    message = "Sơ đồ định tuyến AI không hợp lệ."

    def __init__(self, errors: list[str]) -> None:
        super().__init__(
            self.message, details={"reason": "invalid_routing_graph", "errors": errors}
        )


class RoutingGraphNotEditableError(ConflictError):
    message = "Chỉ có thể chỉnh sửa sơ đồ định tuyến ở trạng thái nháp."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_editable"})
