"""Response shapes for the company-profile + approval-workflow surface.

Two safety invariants hold everywhere here:

- Raw storage keys never leave the backend. Every attached/verification document
  is projected as a short-lived, HMAC-signed delivery URL (resolved server-side
  by ``company_profile_service.serve_company_document``).
- Field names in a diff are internal but safe; each carries a localized label so
  the UI never renders a raw column code to an end user.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.config import get_settings
from app.modules.documents.application import documents_storage_facade as storage_facade
from app.modules.organization.api.public_presenters import public_logo_url
from app.modules.organization.domain.models import CompanyProfileChangeRequest, Organization

# Signed-token resource kinds for the two document-holding surfaces.
DOC_KIND_CHANGE_REQUEST = "company_change_doc"
DOC_KIND_VERIFICATION = "company_verification_doc"

_FIELD_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "display_name": "Tên hiển thị",
        "legal_name": "Tên pháp lý",
        "tax_code": "Mã số thuế",
        "registration_number": "Số đăng ký kinh doanh",
        "description": "Giới thiệu",
        "website_url": "Website",
        "industry": "Ngành nghề",
        "company_size": "Quy mô",
        "founded_year": "Năm thành lập",
        "headquarters_city": "Thành phố trụ sở",
        "headquarters_country": "Quốc gia trụ sở",
    },
    "en": {
        "display_name": "Display name",
        "legal_name": "Legal name",
        "tax_code": "Tax code",
        "registration_number": "Business registration number",
        "description": "About",
        "website_url": "Website",
        "industry": "Industry",
        "company_size": "Company size",
        "founded_year": "Founded year",
        "headquarters_city": "HQ city",
        "headquarters_country": "HQ country",
    },
}

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "pending": "Chờ trường duyệt",
        "approved": "Đã duyệt",
        "rejected": "Bị từ chối",
        "withdrawn": "Đã thu hồi",
    },
    "en": {
        "pending": "Awaiting university review",
        "approved": "Approved",
        "rejected": "Rejected",
        "withdrawn": "Withdrawn",
    },
}


def field_label(field: str, *, locale: str = "vi") -> str:
    return _FIELD_LABELS.get(locale, _FIELD_LABELS["vi"]).get(field, field)


def status_label(status: str, *, locale: str = "vi") -> str:
    return _STATUS_LABELS.get(locale, _STATUS_LABELS["vi"]).get(status, status)


def signed_document_url(
    *,
    kind: str,
    org_id: uuid.UUID,
    file_id: str,
    req_id: uuid.UUID | None = None,
) -> str:
    """Short-lived signed delivery URL for a company document (never a key)."""

    token = storage_facade.make_signed_token(
        {
            "kind": kind,
            "org_id": str(org_id),
            "req_id": str(req_id) if req_id else None,
            "file_id": file_id,
        }
    )
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/organizations/company-documents/{token}"


def _document_view(
    file_ref: dict[str, Any],
    *,
    kind: str,
    org_id: uuid.UUID,
    req_id: uuid.UUID | None,
    locale: str = "vi",
) -> dict[str, Any]:
    """Project a stored file ref to a safe view. ``storage_key`` is dropped."""

    return {
        "id": file_ref.get("id"),
        "kind": file_ref.get("kind"),
        "kind_label": _DOC_KIND_LABELS.get(locale, _DOC_KIND_LABELS["vi"]).get(
            file_ref.get("kind", ""), file_ref.get("kind")
        ),
        "filename": file_ref.get("filename"),
        "content_type": file_ref.get("content_type"),
        "size": file_ref.get("size"),
        "uploaded_at": file_ref.get("uploaded_at"),
        "url": signed_document_url(
            kind=kind, org_id=org_id, file_id=str(file_ref.get("id")), req_id=req_id
        ),
    }


_DOC_KIND_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "business_license": "Giấy phép kinh doanh",
        "tax_certificate": "Chứng nhận đăng ký thuế",
        "legal_document": "Tài liệu pháp lý",
        "other": "Tài liệu khác",
    },
    "en": {
        "business_license": "Business license",
        "tax_certificate": "Tax registration certificate",
        "legal_document": "Legal document",
        "other": "Other document",
    },
}


def _proposed_changes_view(
    proposed_changes: dict[str, Any], *, locale: str = "vi"
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for field, diff in sorted((proposed_changes or {}).items()):
        entry: dict[str, Any] = {"field": field, "label": field_label(field, locale=locale)}
        if isinstance(diff, dict):
            entry["from"] = diff.get("from")
            entry["to"] = diff.get("to")
        else:  # tolerate a bare value shape
            entry["from"] = None
            entry["to"] = diff
        out.append(entry)
    return out


def change_request_summary(
    req: CompanyProfileChangeRequest,
    *,
    company_name: str | None = None,
    locale: str = "vi",
) -> dict[str, Any]:
    return {
        "id": str(req.id),
        "org_id": str(req.org_id),
        "company_name": company_name,
        "submitted_by": str(req.submitted_by) if req.submitted_by else None,
        "status": req.status,
        "status_label": status_label(req.status, locale=locale),
        "changes": _proposed_changes_view(req.proposed_changes, locale=locale),
        "documents": [
            _document_view(
                f,
                kind=DOC_KIND_CHANGE_REQUEST,
                org_id=req.org_id,
                req_id=req.id,
                locale=locale,
            )
            for f in (req.attached_files or [])
        ],
        "reviewer_id": str(req.reviewer_id) if req.reviewer_id else None,
        "review_note": req.review_note,
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "version": req.version,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }


def company_profile_detail(
    org: Organization,
    *,
    pending_request: CompanyProfileChangeRequest | None = None,
    locale: str = "vi",
) -> dict[str, Any]:
    """Full authenticated company profile for the partner-admin surface."""

    return {
        "id": str(org.id),
        "slug": org.slug,
        "org_type": org.org_type,
        "logo_url": public_logo_url(org),
        # Public identity + cosmetic fields.
        "display_name": org.display_name,
        "description": org.description,
        "website_url": org.website_url,
        "industry": org.industry,
        "company_size": org.company_size,
        "founded_year": org.founded_year,
        "headquarters_city": org.headquarters_city,
        "headquarters_country": org.headquarters_country,
        # Sensitive legal identity (approval-gated).
        "legal_name": org.legal_name,
        "tax_code": org.tax_code,
        "registration_number": org.registration_number,
        "is_verified": org.is_verified,
        "verification_documents": [
            _document_view(
                f,
                kind=DOC_KIND_VERIFICATION,
                org_id=org.id,
                req_id=None,
                locale=locale,
            )
            for f in (org.verification_documents or [])
        ],
        "version": org.version,
        "pending_change_request": (
            change_request_summary(pending_request, locale=locale)
            if pending_request is not None
            else None
        ),
    }
