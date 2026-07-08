"""Hardcoded institutional retention constants (``docs/DATA_MODEL.md`` §35).

V1 does **not** ship a DB-configurable ``retention_policies`` table. These are
code constants surfaced as read-only, localized text on ``/account/privacy``.

``docs/SECURITY_PRIVACY.md`` does not currently specify a numeric retention
period for application CV snapshots or audit logs; ``AUDIT_LOG_RETENTION_DAYS``
and ``APPLICATION_CV_SNAPSHOT_RETENTION_DAYS`` below are this implementation's
proposed defaults (2 years), flagged for `system-architect`/security review as
a documentation gap rather than a silent invention.
"""

from __future__ import annotations

from dataclasses import dataclass

# Proposed defaults (not yet ratified in docs/SECURITY_PRIVACY.md — flagged).
AUDIT_LOG_RETENTION_DAYS = 730
APPLICATION_CV_SNAPSHOT_RETENTION_DAYS = 730


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    key: str
    retention_days: int
    label_vi: str
    label_en: str


POLICIES: tuple[RetentionPolicy, ...] = (
    RetentionPolicy(
        key="application_cv_snapshots",
        retention_days=APPLICATION_CV_SNAPSHOT_RETENTION_DAYS,
        label_vi=(
            "Bản lưu CV nộp hồ sơ được giữ tối đa 24 tháng kể từ ngày tạo, "
            "sau đó được ẩn danh hóa tự động."
        ),
        label_en=(
            "Application CV snapshots are retained for up to 24 months from "
            "creation, then automatically anonymized."
        ),
    ),
    RetentionPolicy(
        key="audit_logs",
        retention_days=AUDIT_LOG_RETENTION_DAYS,
        label_vi="Nhật ký kiểm toán được lưu trữ tối đa 24 tháng.",
        label_en="Audit logs are retained for up to 24 months.",
    ),
)


def as_dict(*, locale: str = "vi") -> list[dict[str, object]]:
    """Read-only presenter for ``GET /account/privacy/retention``."""

    label_attr = "label_vi" if locale == "vi" else "label_en"
    return [
        {
            "key": p.key,
            "retention_days": p.retention_days,
            "label": getattr(p, label_attr),
        }
        for p in POLICIES
    ]
