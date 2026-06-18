"""
Documents — domain layer.

Entities, value objects, state machine, ACL policies.
No ORM, no HTTP, no storage SDK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DocumentCategory(StrEnum):
    COMPANY_LOGO = "company-logo"
    BUSINESS_LICENSE = "business-license"
    CV = "cv"
    TRANSCRIPT = "transcript"
    CERTIFICATE = "certificate"
    ID_CARD = "id-card"
    OTHER = "other"


class ScanStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    SCANNING = "SCANNING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    SCAN_ERROR = "SCAN_ERROR"
    EXPIRED = "EXPIRED"


TERMINAL_SCAN_STATES = {ScanStatus.CLEAN, ScanStatus.INFECTED, ScanStatus.SCAN_ERROR}
VALID_SCAN_TRANSITIONS: dict[ScanStatus, set[ScanStatus]] = {
    ScanStatus.PENDING_UPLOAD: {ScanStatus.UPLOADED},
    ScanStatus.UPLOADED: {ScanStatus.SCANNING},
    ScanStatus.SCANNING: {ScanStatus.CLEAN, ScanStatus.INFECTED, ScanStatus.SCAN_ERROR},
    ScanStatus.SCAN_ERROR: {ScanStatus.SCANNING},  # allow retry
    ScanStatus.CLEAN: {ScanStatus.EXPIRED},
    ScanStatus.INFECTED: set(),
    ScanStatus.EXPIRED: set(),
}


@dataclass
class Document:
    """Aggregate root for an uploaded document."""

    id: str
    owner_id: str
    org_id: str               # university org id the document belongs to
    category: DocumentCategory
    file_name: str
    content_type: str
    storage_key: str
    size_bytes: int
    scan_status: ScanStatus
    checksum_sha256: str | None
    uploaded_at: datetime | None
    scanned_at: datetime | None
    scan_engine: str | None
    scan_threats: list[str]
    metadata: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # -- ACL helpers --

    def can_read(self, actor_id: str, actor_org_id: str, is_admin: bool) -> bool:
        """True if actor is owner OR university admin for same org."""
        if actor_id == self.owner_id:
            return True
        return is_admin and actor_org_id == self.org_id

    def can_delete(self, actor_id: str) -> bool:
        return actor_id == self.owner_id

    def is_accessible(self) -> bool:
        """Only CLEAN docs produce accessible download URLs."""
        return self.scan_status == ScanStatus.CLEAN

    # -- State machine --

    def transition_scan(self, new_status: ScanStatus, **kwargs: Any) -> None:
        allowed = VALID_SCAN_TRANSITIONS.get(self.scan_status, set())
        if new_status not in allowed:
            from app.shared.errors import AppError, ErrorCode
            raise AppError(
                code=ErrorCode.CONFLICT,
                message=f"Cannot transition document from {self.scan_status} to {new_status}",
                status_code=409,
            )
        self.scan_status = new_status
        if new_status == ScanStatus.UPLOADED:
            self.uploaded_at = datetime.now(UTC)
        elif new_status in TERMINAL_SCAN_STATES:
            self.scanned_at = datetime.now(UTC)
            self.scan_engine = kwargs.get("scan_engine")
            self.scan_threats = kwargs.get("threats", [])
