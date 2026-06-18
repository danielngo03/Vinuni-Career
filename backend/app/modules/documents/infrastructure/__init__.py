"""
Documents — infrastructure layer.

Implements DocumentRepository (SQLAlchemy) and StoragePort adapters.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.documents.application import DocumentRepository, StoragePort
from app.modules.documents.domain import Document, DocumentCategory, ScanStatus
from app.platform.database.models.outbox import DocumentRecord
from app.platform.storage import get_storage
from app.shared.errors import AppError, ErrorCode


class SQLDocumentRepository(DocumentRepository):
    """SQLAlchemy-backed DocumentRepository."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, document_id: str) -> Document:
        row = self._db.get(DocumentRecord, document_id)
        if not row or row.is_deleted:
            raise AppError(
                code=ErrorCode.NOT_FOUND,
                message="Document not found",
                status_code=404,
            )
        return self._to_domain(row)

    def save(self, doc: Document) -> None:
        row = self._db.get(DocumentRecord, doc.id)
        if row is None:
            row = DocumentRecord(
                id=doc.id,
                owner_id=doc.owner_id,
                org_id=doc.org_id,
                category=doc.category,
                file_name=doc.file_name,
                content_type=doc.content_type,
                storage_key=doc.storage_key,
                size_bytes=doc.size_bytes,
            )
            self._db.add(row)
        # Update mutable fields
        row.scan_status = doc.scan_status
        row.checksum_sha256 = doc.checksum_sha256
        row.uploaded_at = doc.uploaded_at
        row.scanned_at = doc.scanned_at
        row.scan_engine = doc.scan_engine
        row.scan_threats = doc.scan_threats
        row.doc_metadata = doc.metadata
        self._db.flush()

    def list_by_owner(self, owner_id: str, **filters: object) -> list[Document]:
        from sqlalchemy import select

        stmt = select(DocumentRecord).where(
            DocumentRecord.owner_id == owner_id,
            DocumentRecord.is_deleted.is_(False),
        )
        if category := filters.get("category"):
            stmt = stmt.where(DocumentRecord.category == category)
        if scan_status := filters.get("scan_status"):
            stmt = stmt.where(DocumentRecord.scan_status == scan_status)
        rows = self._db.scalars(stmt).all()
        return [self._to_domain(r) for r in rows]

    @staticmethod
    def _to_domain(row: DocumentRecord) -> Document:
        return Document(
            id=row.id,
            owner_id=row.owner_id,
            org_id=row.org_id,
            category=DocumentCategory(row.category),
            file_name=row.file_name,
            content_type=row.content_type,
            storage_key=row.storage_key,
            size_bytes=row.size_bytes,
            scan_status=ScanStatus(row.scan_status),
            checksum_sha256=row.checksum_sha256,
            uploaded_at=row.uploaded_at,
            scanned_at=row.scanned_at,
            scan_engine=row.scan_engine,
            scan_threats=row.scan_threats or [],
            metadata=row.doc_metadata or {},
            created_at=row.created_at,
        )


class StoragePortAdapter(StoragePort):
    """Adapts the existing infra storage backend to the documents StoragePort."""

    def presigned_upload(self, key: str, content_type: str, ttl_seconds: int) -> dict:
        """Return a provider-specific upload URL."""
        storage = get_storage()
        return storage.presigned_upload(key, content_type, ttl_seconds)

    def presigned_download(self, key: str, ttl_seconds: int) -> str:
        storage = get_storage()
        return storage.signed_url(key, ttl_seconds)
