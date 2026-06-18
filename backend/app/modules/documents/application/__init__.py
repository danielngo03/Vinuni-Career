"""
Documents — application layer.

Commands, queries, and use cases. No FastAPI, no ORM.
Use cases call DocumentRepository and StoragePort.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.modules.documents.domain import Document, DocumentCategory, ScanStatus
from app.shared.ids import new_id
from app.shared.outbox import DocumentUploaded, OutboxWriter

# ---------------------------------------------------------------------------
# Commands & Queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreateUploadSessionCommand:
    owner_id: str
    org_id: str
    category: str
    file_name: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class CompleteUploadCommand:
    document_id: str
    actor_id: str
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class TriggerScanCommand:
    document_id: str


@dataclass(frozen=True)
class RecordScanResultCommand:
    document_id: str
    scan_result: str   # "CLEAN" | "INFECTED" | "SCAN_ERROR"
    scan_engine: str | None = None
    threats: list[str] | None = None


@dataclass(frozen=True)
class SoftDeleteDocumentCommand:
    document_id: str
    actor_id: str


@dataclass(frozen=True)
class GetDocumentQuery:
    document_id: str
    actor_id: str
    actor_org_id: str
    is_admin: bool = False


@dataclass(frozen=True)
class ListDocumentsQuery:
    owner_id: str
    category: str | None = None
    scan_status: str | None = None


# ---------------------------------------------------------------------------
# Presigned URL response
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UploadSession:
    document_id: str
    upload_url: str        # presigned PUT URL (or local stub URL)
    upload_method: str     # "PUT" (S3) or "POST" (form upload for local)
    expires_in_seconds: int
    fields: dict           # only non-empty for multipart form POST (S3 path)


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------

ALLOWED_CONTENT_TYPES: dict[str, set[str]] = {
    DocumentCategory.CV: {"application/pdf"},
    DocumentCategory.TRANSCRIPT: {"application/pdf"},
    DocumentCategory.COMPANY_LOGO: {"image/png", "image/jpeg", "image/webp"},
    DocumentCategory.BUSINESS_LICENSE: {"application/pdf", "image/png", "image/jpeg"},
    DocumentCategory.CERTIFICATE: {"application/pdf", "image/png", "image/jpeg"},
    DocumentCategory.ID_CARD: {"image/png", "image/jpeg"},
    DocumentCategory.OTHER: {
        "application/pdf", "image/png", "image/jpeg", "image/webp"
    },
}

MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def create_upload_session(
    cmd: CreateUploadSessionCommand,
    repository: DocumentRepository,
    storage: StoragePort,
    outbox: OutboxWriter,
) -> UploadSession:
    from app.shared.errors import AppError, ErrorCode

    try:
        category = DocumentCategory(cmd.category)
    except ValueError as exc:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"Unknown document category: {cmd.category}",
            status_code=400,
        ) from exc

    allowed = ALLOWED_CONTENT_TYPES.get(category, set())
    if cmd.content_type not in allowed:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"Content type {cmd.content_type!r} is not allowed for {category}",
            status_code=400,
        )
    if cmd.size_bytes > MAX_SIZE_BYTES:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"File size exceeds the {MAX_SIZE_BYTES // (1024*1024)} MB limit",
            status_code=400,
        )

    clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", cmd.file_name or category)
    doc_id = new_id()
    storage_key = f"documents/{cmd.org_id}/{category}/{doc_id}/{clean_name}"

    doc = Document(
        id=doc_id,
        owner_id=cmd.owner_id,
        org_id=cmd.org_id,
        category=category,
        file_name=cmd.file_name,
        content_type=cmd.content_type,
        storage_key=storage_key,
        size_bytes=cmd.size_bytes,
        scan_status=ScanStatus.PENDING_UPLOAD,
        checksum_sha256=None,
        uploaded_at=None,
        scanned_at=None,
        scan_engine=None,
        scan_threats=[],
        metadata={},
    )
    repository.save(doc)

    presigned = storage.presigned_upload(storage_key, cmd.content_type, ttl_seconds=900)
    return UploadSession(
        document_id=doc_id,
        upload_url=presigned["url"],
        upload_method=presigned.get("method", "PUT"),
        expires_in_seconds=900,
        fields=presigned.get("fields", {}),
    )


def complete_upload(
    cmd: CompleteUploadCommand,
    repository: DocumentRepository,
    outbox: OutboxWriter,
) -> Document:
    doc = repository.get(cmd.document_id)
    if not doc.can_delete(cmd.actor_id):
        from app.shared.errors import AppError, ErrorCode

        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Only the document owner can complete an upload",
            status_code=403,
        )
    doc.transition_scan(ScanStatus.UPLOADED)
    if cmd.checksum_sha256:
        doc.checksum_sha256 = cmd.checksum_sha256
    repository.save(doc)
    outbox.emit(
        DocumentUploaded(
            aggregate_id=doc.id,
            owner_id=doc.owner_id,
            category=doc.category,
            storage_key=doc.storage_key,
        )
    )
    return doc


def record_scan_result(
    cmd: RecordScanResultCommand,
    repository: DocumentRepository,
) -> Document:
    doc = repository.get(cmd.document_id)
    new_status = ScanStatus(cmd.scan_result)
    doc.transition_scan(
        new_status,
        scan_engine=cmd.scan_engine,
        threats=cmd.threats or [],
    )
    repository.save(doc)
    return doc


def start_scan(
    document_id: str,
    repository: DocumentRepository,
) -> Document:
    doc = repository.get(document_id)
    doc.transition_scan(ScanStatus.SCANNING)
    repository.save(doc)
    return doc


def get_document_download_url(
    query: GetDocumentQuery,
    repository: DocumentRepository,
    storage: StoragePort,
) -> str:
    from app.shared.errors import AppError, ErrorCode

    doc = repository.get(query.document_id)
    if not doc.can_read(query.actor_id, query.actor_org_id, query.is_admin):
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="You do not have access to this document",
            status_code=403,
        )
    if not doc.is_accessible():
        raise AppError(
            code=ErrorCode.CONFLICT,
            message=f"Document is not accessible (status: {doc.scan_status})",
            status_code=409,
        )
    return storage.presigned_download(doc.storage_key, ttl_seconds=900)


# ---------------------------------------------------------------------------
# Ports (interfaces — implemented in infrastructure layer)
# ---------------------------------------------------------------------------

class DocumentRepository(Protocol):
    def get(self, document_id: str) -> Document: ...
    def save(self, doc: Document) -> None: ...
    def list_by_owner(self, owner_id: str, **filters: object) -> list[Document]: ...


class StoragePort(Protocol):
    def presigned_upload(self, key: str, content_type: str, ttl_seconds: int) -> dict: ...
    def presigned_download(self, key: str, ttl_seconds: int) -> str: ...
