"""
Documents module — FastAPI router.

Endpoints:
  POST /documents/upload-session  → create upload session, return presigned URL
  POST /documents/{id}/complete   → mark uploaded, trigger scan
  GET  /documents/{id}/download   → return signed download URL (CLEAN only)
  GET  /documents/{id}            → document metadata
  GET  /documents/                → list caller's documents
  POST /documents/{id}/scan-result → internal scan webhook (service-to-service)
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_active_identity
from app.modules.documents.application import (
    CompleteUploadCommand,
    CreateUploadSessionCommand,
    GetDocumentQuery,
    RecordScanResultCommand,
    UploadSession,
    complete_upload,
    create_upload_session,
    get_document_download_url,
    record_scan_result,
    start_scan,
)
from app.modules.documents.domain import Document
from app.modules.documents.infrastructure import SQLDocumentRepository, StoragePortAdapter
from app.platform.database.models import User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.config import settings
from app.shared.errors import AppError, ErrorCode
from app.shared.outbox import OutboxWriter

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CreateUploadSessionRequest(BaseModel):
    category: str = Field(..., description="document category, e.g. 'cv', 'business-license'")
    file_name: str = Field(..., max_length=500)
    content_type: str = Field(..., max_length=120)
    size_bytes: int = Field(..., gt=0, le=20 * 1024 * 1024)


class UploadSessionResponse(BaseModel):
    document_id: str
    upload_url: str
    upload_method: str
    expires_in_seconds: int
    fields: dict


class CompleteUploadRequest(BaseModel):
    checksum_sha256: str | None = None


class ScanResultRequest(BaseModel):
    scan_result: str   # "CLEAN" | "INFECTED" | "SCAN_ERROR"
    scan_engine: str | None = None
    threats: list[str] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    id: str
    owner_id: str
    org_id: str
    category: str
    file_name: str
    content_type: str
    size_bytes: int
    scan_status: str
    uploaded_at: str | None
    scanned_at: str | None


class DownloadUrlResponse(BaseModel):
    url: str
    expires_in_seconds: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload-session", response_model=UploadSessionResponse, status_code=201)
def create_upload_session_endpoint(
    body: CreateUploadSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    identity: UserOrgRole = Depends(get_active_identity),
) -> UploadSessionResponse:
    repo = SQLDocumentRepository(db)
    storage = StoragePortAdapter()
    outbox = OutboxWriter(db)
    session: UploadSession = create_upload_session(
        CreateUploadSessionCommand(
            owner_id=current_user.id,
            org_id=identity.org_id,
            category=body.category,
            file_name=body.file_name,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        ),
        repository=repo,
        storage=storage,
        outbox=outbox,
    )
    db.commit()
    return UploadSessionResponse(
        document_id=session.document_id,
        upload_url=session.upload_url,
        upload_method=session.upload_method,
        expires_in_seconds=session.expires_in_seconds,
        fields=session.fields,
    )


@router.post("/{document_id}/complete", response_model=DocumentResponse)
def complete_upload_endpoint(
    document_id: str,
    body: CompleteUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    repo = SQLDocumentRepository(db)
    outbox = OutboxWriter(db)
    doc = complete_upload(
        CompleteUploadCommand(
            document_id=document_id,
            actor_id=current_user.id,
            checksum_sha256=body.checksum_sha256,
        ),
        repository=repo,
        outbox=outbox,
    )
    db.commit()
    return _doc_response(doc)


@router.get("/{document_id}/download", response_model=DownloadUrlResponse)
def download_url_endpoint(
    document_id: str,
    identity_id: str | None = Header(default=None, alias="X-Identity-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DownloadUrlResponse:
    # Resolve org_id from identity header if present
    org_id = ""
    is_admin = False
    if identity_id:
        from app.platform.database.models import UserOrgRole
        identity = db.get(UserOrgRole, identity_id)
        if identity and identity.user_id == current_user.id:
            org_id = identity.org_id
            is_admin = identity.role.name not in {"student", "company_hr"}

    repo = SQLDocumentRepository(db)
    storage = StoragePortAdapter()
    url = get_document_download_url(
        GetDocumentQuery(
            document_id=document_id,
            actor_id=current_user.id,
            actor_org_id=org_id,
            is_admin=is_admin,
        ),
        repository=repo,
        storage=storage,
    )
    return DownloadUrlResponse(url=url, expires_in_seconds=900)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document_endpoint(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    repo = SQLDocumentRepository(db)
    doc = repo.get(document_id)
    if doc.owner_id != current_user.id:
        from app.shared.errors import AppError, ErrorCode
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Access denied",
            status_code=403,
        )
    return _doc_response(doc)


@router.get("/", response_model=list[DocumentResponse])
def list_documents_endpoint(
    category: str | None = None,
    scan_status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    repo = SQLDocumentRepository(db)
    docs = repo.list_by_owner(current_user.id, category=category, scan_status=scan_status)
    return [_doc_response(d) for d in docs]


@router.post("/{document_id}/scan-result", include_in_schema=False)
def scan_result_endpoint(
    document_id: str,
    body: ScanResultRequest,
    service_token: str | None = Header(
        default=None,
        alias="X-Internal-Service-Token",
    ),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Internal endpoint for scan worker callbacks."""
    if not settings.internal_service_token:
        raise AppError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message="Internal service authentication is not configured",
            status_code=503,
        )
    if not service_token or not hmac.compare_digest(
        service_token,
        settings.internal_service_token,
    ):
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Invalid internal service token",
            status_code=401,
        )
    repo = SQLDocumentRepository(db)
    current = repo.get(document_id)
    if current.scan_status.value == "UPLOADED":
        start_scan(document_id, repository=repo)
    doc = record_scan_result(
        RecordScanResultCommand(
            document_id=document_id,
            scan_result=body.scan_result,
            scan_engine=body.scan_engine,
            threats=body.threats,
        ),
        repository=repo,
    )
    db.commit()
    return _doc_response(doc)


def _doc_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        owner_id=doc.owner_id,
        org_id=doc.org_id,
        category=doc.category,
        file_name=doc.file_name,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        scan_status=doc.scan_status,
        uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        scanned_at=doc.scanned_at.isoformat() if doc.scanned_at else None,
    )
