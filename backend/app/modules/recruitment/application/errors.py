"""Recruitment-module application errors mapped to the shared error envelope.

``details.reason`` carries a stable, user-safe machine token (never a raw DB/enum
code) for clients that branch on it.
"""

from __future__ import annotations

import uuid

from app.shared.exceptions import ConflictError, ValidationFailedError


class DuplicateApplicationError(ConflictError):
    """The applicant already has an active application to this job.

    Carries the existing application's ``application_id`` + ``status`` (in
    addition to the stable ``duplicate_application`` reason code) so the client
    can deep-link the student straight to their existing application instead of
    just showing a generic "already applied" toast (``docs/API_CONTRACTS.md``).
    """

    message = "Bạn đã ứng tuyển vị trí này rồi."

    def __init__(
        self, *, application_id: uuid.UUID | None = None, status: str | None = None
    ) -> None:
        details: dict = {"reason": "duplicate_application"}
        if application_id is not None:
            details["application_id"] = str(application_id)
        if status is not None:
            details["status"] = status
        super().__init__(self.message, details=details)


class ApplicationNotWithdrawableError(ConflictError):
    """The application cannot be withdrawn from its current status."""

    message = "Không thể rút hồ sơ ứng tuyển ở trạng thái hiện tại."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "not_withdrawable"})


class IllegalApplicationTransitionError(ConflictError):
    """Requested decision transition is not legal from the current status."""

    message = "Không thể thực hiện thao tác này ở trạng thái hiện tại của hồ sơ."

    def __init__(self, *, event: str) -> None:
        super().__init__(
            self.message,
            details={"reason": "illegal_transition", "event": event},
        )


class ApplicationVersionConflictError(ConflictError):
    """Stale optimistic-locking version on a concurrent decision."""

    message = "Hồ sơ đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi thao tác."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "version_conflict"})


class RollbackLimitReachedError(ConflictError):
    """The application has used its allotted rollbacks (4th needs admin approval).

    ``docs/BUSINESS_LOGIC.md`` §3.5 / ADR-0004 §2: V1 simply blocks the 4th
    rollback with a coded marker; the university-admin approval workflow is
    deferred to a later slice.
    """

    message = "Hồ sơ đã đạt số lần chuyển về tối đa. Cần phê duyệt của quản trị viên để tiếp tục."

    def __init__(self) -> None:
        super().__init__(
            self.message,
            details={"reason": "rollback_limit", "requires": "university_admin_approval"},
        )


class ScorecardRequiredError(ConflictError):
    """The current stage requires a submitted scorecard before /advance (ADR-0005 §3).

    Distinct from the generic ``illegal_transition`` so the kanban can render a
    precise "complete a scorecard to advance" blocked state (PRD §7.1). Carries the
    current and required submitted counts (``{submitted, required}``) — never any
    scorecard content (it stays partner-internal).
    """

    message = "Cần hoàn tất phiếu đánh giá trước khi chuyển ứng viên sang vòng tiếp theo."

    def __init__(self, *, submitted: int, required: int) -> None:
        super().__init__(
            self.message,
            details={
                "reason": "scorecard_required",
                "submitted": submitted,
                "required": required,
            },
        )


class ScoreBelowThresholdError(ConflictError):
    """The stage's average evaluator score is below ``stage.score_threshold`` (ADR-0006).

    Raised by ``/advance`` on a ``score_threshold`` stage once ALL assigned
    interviewers have submitted but the mean ``overall_score`` is below the
    configured threshold. Distinct from ``scorecard_required`` so the kanban renders
    a precise "average score too low" blocked state. Carries the rounded average and
    the threshold (``{avg_overall, threshold}``) — never any scorecard content.
    """

    message = "Điểm đánh giá trung bình chưa đạt ngưỡng yêu cầu để chuyển vòng."

    def __init__(self, *, avg_overall: float | None, threshold: float | None) -> None:
        super().__init__(
            self.message,
            details={
                "reason": "score_below_threshold",
                "avg_overall": avg_overall,
                "threshold": threshold,
            },
        )


class InterviewExistsError(ConflictError):
    """An OPEN (scheduled) interview already exists for this (application, stage).

    ADR-0006 §1/§6: at most one open interview per ``(application, stage)``. Cancel
    or complete the existing interview before scheduling another for the stage.
    """

    message = "Đã có một buổi phỏng vấn đang mở cho vòng này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "interview_exists"})


class InterviewNotActionableError(ConflictError):
    """The interview cannot transition (e.g. completing a cancelled interview)."""

    message = "Không thể thực hiện thao tác này với buổi phỏng vấn ở trạng thái hiện tại."

    def __init__(self, *, reason: str = "interview_not_actionable") -> None:
        super().__init__(self.message, details={"reason": reason})


class OfferExistsError(ConflictError):
    """A LIVE offer already exists for this application (ADR-0007 §1).

    At most one offer in ``{draft, pending_approval, approved, sent}`` may exist per
    application. Rescind or let the existing offer reach a terminal state before
    creating another.
    """

    message = "Đã có một thư mời đang xử lý cho ứng viên này."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "offer_exists"})


class OfferNotEditableError(ConflictError):
    """The offer can be edited only while it is a ``draft`` (ADR-0007 §1).

    Content is frozen at submit; from ``pending_approval`` onward only status
    transitions mutate the row.
    """

    message = "Chỉ có thể chỉnh sửa thư mời khi còn ở trạng thái bản nháp."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "offer_not_editable"})


class OfferNotApprovedError(ConflictError):
    """Sending requires the offer to be ``approved`` first (ADR-0007 §2).

    The approval gate is structural: ``send`` requires ``status='approved'``. Submit
    the offer for approval and have an approver approve it before sending.
    """

    message = "Thư mời cần được phê duyệt nội bộ trước khi gửi cho ứng viên."

    def __init__(self) -> None:
        super().__init__(self.message, details={"reason": "offer_not_approved"})


class OfferNotActionableError(ConflictError):
    """The offer cannot be responded to in its current state (ADR-0007 §3).

    The candidate may respond only to a ``sent`` offer that has not expired; a
    rescinded / expired / already-answered offer raises this distinct ``409`` so the
    student UI renders a precise "this offer is no longer open" state.
    """

    message = "Không thể phản hồi thư mời ở trạng thái hiện tại."

    def __init__(self, *, reason: str = "offer_not_actionable") -> None:
        super().__init__(self.message, details={"reason": reason})


class InvalidApplicationFieldError(ValidationFailedError):
    """An application field value is invalid (e.g. reveal reason too short)."""

    message = "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại."

    def __init__(self, *, field: str) -> None:
        super().__init__(self.message, details={"reason": "invalid_field", "field": field})
