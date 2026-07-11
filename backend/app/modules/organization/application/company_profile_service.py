"""Company profile editing + the university approval workflow (owner 2026-07-10).

A partner admin can open their own company page and edit it, but the write path
is split by sensitivity (RBAC + audit + tenant isolation all enforced here, not
in the router):

- **Cosmetic fields** (public display name, description, website, industry,
  size, founded year, coarse HQ city/country) apply IMMEDIATELY to the live
  ``organizations`` row (display name stays immediate to match the legacy
  ``PATCH /organizations`` surface — one write path, no dual behavior).
- **Sensitive legal identity** (legal name, tax code, business registration
  number) and **ANY attached company file** do NOT touch
  the live profile. They accumulate on a single OPEN
  ``company_profile_change_requests`` row and wait for a university reviewer to
  approve (apply) or reject.

Concurrency: every sensitive mutation locks the org row and merges into the one
open pending request (a partial unique index is the backstop), so two competing
requests can never corrupt the live profile. Approve/reject/withdraw are
row-locked, version-checked, and idempotent — a stale double-apply is refused.

File safety: attached/verification documents are stored by an internal
``storage_key`` that is NEVER returned; callers receive a short-lived signed
delivery URL resolved by :func:`serve_company_document`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import documents_storage_facade as storage_facade
from app.modules.organization.api import company_profile_presenters as presenters
from app.modules.organization.application.errors import (
    ChangeRequestNotPendingError,
    InvalidCompanyDocumentError,
    NoProfileChangesError,
    NotUniversityActorError,
    VersionConflictError,
)
from app.modules.organization.domain.models import (
    CompanyProfileChangeRequest,
    Organization,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "organizations"

# --------------------------------------------------------------------------- #
# Sensitive-vs-immediate field split (single source of truth)                 #
# --------------------------------------------------------------------------- #

# Applied to the live profile immediately (audited, version-bumped). The public
# ``display_name`` stays immediate here to match the legacy ``PATCH
# /organizations`` surface — a single write path, no conflicting dual behavior.
COSMETIC_FIELDS: frozenset[str] = frozenset(
    {
        "display_name",
        "description",
        "website_url",
        "industry",
        "company_size",
        "founded_year",
        "headquarters_city",
        "headquarters_country",
    }
)

# Never applied until a university reviewer approves the change request. These
# are the LEGAL identity fields (owner 2026-07-10) plus any attached file.
SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "legal_name",
        "tax_code",
        "registration_number",
    }
)

_EDITABLE_FIELDS: frozenset[str] = COSMETIC_FIELDS | SENSITIVE_FIELDS
# Sensitive text fields may be trimmed/cleared to NULL. ``display_name`` is
# NOT NULL and handled separately (a blank attempt is dropped, never nulled).
_STRIP_FIELDS: frozenset[str] = SENSITIVE_FIELDS

# Company document (legal/verification file) constraints.
_ALLOWED_DOC_CONTENT_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp"}
)
_EXT_BY_CT: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_DOC_KINDS: frozenset[str] = frozenset(
    {"business_license", "tax_certificate", "legal_document", "other"}
)
_DOC_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass(slots=True)
class ServedDocument:
    content: bytes
    media_type: str
    filename: str


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _is_pg() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _safe_filename(name: str | None) -> str:
    base = (name or "document").rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()
    return (base or "document")[:200]


# --------------------------------------------------------------------------- #
# Tenant-isolated org loaders (cross-org -> 404, never 403)                    #
# --------------------------------------------------------------------------- #


async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(
                Organization.id == org_id, Organization.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if org is None:
        raise ResourceNotFoundError()
    return org


async def _load_org_for(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID, action: str
) -> Organization:
    """Load ``org_id`` enforcing tenant isolation THEN RBAC.

    A missing org or an org the principal does not belong to surfaces as ``404``
    (indistinguishable, no enumeration). A same-org principal lacking
    ``organizations:{action}`` surfaces as ``403``.
    """

    org = await _get_org(session, org_id)
    if not principal.is_superadmin and principal.org_id != org.id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, action, resource_org_id=org.id)
    return org


async def _lock_org_row(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Serialize concurrent change-request mutations for one org (Postgres)."""

    if _is_pg():
        await session.execute(
            select(Organization.id).where(Organization.id == org_id).with_for_update()
        )


async def _open_pending(
    session: AsyncSession, org_id: uuid.UUID, *, lock: bool = False
) -> CompanyProfileChangeRequest | None:
    stmt = select(CompanyProfileChangeRequest).where(
        CompanyProfileChangeRequest.org_id == org_id,
        CompanyProfileChangeRequest.status == "pending",
    )
    if lock and _is_pg():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_request_locked(
    session: AsyncSession, req_id: uuid.UUID
) -> CompanyProfileChangeRequest | None:
    stmt = select(CompanyProfileChangeRequest).where(CompanyProfileChangeRequest.id == req_id)
    if _is_pg():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Partner: read profile                                                       #
# --------------------------------------------------------------------------- #


async def get_company_profile(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID, locale: str = "vi"
) -> dict:
    org = await _load_org_for(session, principal=principal, org_id=org_id, action="read")
    pending = await _open_pending(session, org_id)
    return presenters.company_profile_detail(org, pending_request=pending, locale=locale)


# --------------------------------------------------------------------------- #
# Partner: update profile (cosmetic immediate / sensitive -> change request)  #
# --------------------------------------------------------------------------- #


async def update_company_profile(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    payload: dict[str, Any],
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org = await _load_org_for(session, principal=principal, org_id=org_id, action="update")

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != org.version:
        raise VersionConflictError()

    fields = {k: v for k, v in payload.items() if k in _EDITABLE_FIELDS}
    if not fields:
        raise NoProfileChangesError()

    # ``display_name`` is required (NOT NULL): drop a blank/null attempt.
    if "display_name" in fields:
        dn = fields["display_name"]
        if not isinstance(dn, str) or not dn.strip():
            fields.pop("display_name")
        else:
            fields["display_name"] = dn.strip()

    # Sensitive string fields may be trimmed and cleared to None.
    for key in _STRIP_FIELDS:
        if key in fields and isinstance(fields[key], str):
            fields[key] = fields[key].strip() or None

    if not fields:
        raise NoProfileChangesError()

    # Cosmetic changes apply immediately.
    applied: list[str] = []
    for field, value in fields.items():
        if field in COSMETIC_FIELDS and getattr(org, field) != value:
            setattr(org, field, value)
            applied.append(field)

    # Sensitive changes accumulate on the open pending request.
    sensitive_diff: dict[str, dict[str, Any]] = {}
    for field, value in fields.items():
        if field in SENSITIVE_FIELDS and getattr(org, field) != value:
            sensitive_diff[field] = {"from": getattr(org, field), "to": value}

    if not applied and not sensitive_diff:
        raise NoProfileChangesError()

    pending: CompanyProfileChangeRequest | None = None
    if sensitive_diff:
        await _lock_org_row(session, org_id)
        pending = await _open_pending(session, org_id, lock=True)
        if pending is None:
            pending = CompanyProfileChangeRequest(
                org_id=org_id,
                submitted_by=principal.user_id,
                proposed_changes=sensitive_diff,
                attached_files=[],
                status="pending",
            )
            session.add(pending)
        else:
            merged = dict(pending.proposed_changes or {})
            merged.update(sensitive_diff)
            pending.proposed_changes = merged
            pending.submitted_by = principal.user_id or pending.submitted_by
            pending.version += 1
            # Set explicitly so the server-side ``onupdate`` does not expire the
            # attribute (which would trigger a sync lazy-load in the presenter).
            pending.updated_at = datetime.now(tz=UTC)
        await session.flush()

    if applied:
        org.version += 1
        await write_audit(
            session,
            action="organization.profile_updated",
            resource_type="organization",
            resource_id=org.id,
            context=_audit_ctx(principal, ctx),
            after={"fields": sorted(applied)},
        )
    if pending is not None:
        await write_audit(
            session,
            action="organization.change_requested",
            resource_type="company_profile_change_request",
            resource_id=pending.id,
            context=_audit_ctx(principal, ctx),
            after={"request_id": str(pending.id), "fields": sorted(sensitive_diff.keys())},
        )

    await session.commit()
    return {
        "applied": sorted(applied),
        "requires_approval": pending is not None,
        "pending_change_request": (
            presenters.change_request_summary(pending, locale=locale) if pending else None
        ),
        "profile": presenters.company_profile_detail(org, pending_request=pending, locale=locale),
    }


# --------------------------------------------------------------------------- #
# Partner: attach a company document (always -> pending approval)             #
# --------------------------------------------------------------------------- #


async def attach_company_document(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    content_type: str | None,
    kind: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _load_org_for(session, principal=principal, org_id=org_id, action="update")

    if not data:
        raise InvalidCompanyDocumentError("empty_file")
    if len(data) > _DOC_MAX_BYTES:
        raise InvalidCompanyDocumentError("file_too_large")
    media = (content_type or "").split(";")[0].strip().lower()
    if media not in _ALLOWED_DOC_CONTENT_TYPES:
        raise InvalidCompanyDocumentError("unsupported_type")
    doc_kind = kind if kind in _DOC_KINDS else "other"

    file_id = uuid.uuid4()
    storage_key = f"org-documents/{org_id}/{file_id}.{_EXT_BY_CT[media]}"
    storage_facade.save(storage_key, data)

    file_ref: dict[str, Any] = {
        "id": str(file_id),
        "kind": doc_kind,
        "filename": _safe_filename(filename),
        "content_type": media,
        "size": len(data),
        "storage_key": storage_key,
        "uploaded_at": datetime.now(tz=UTC).isoformat(),
    }

    await _lock_org_row(session, org_id)
    pending = await _open_pending(session, org_id, lock=True)
    if pending is None:
        pending = CompanyProfileChangeRequest(
            org_id=org_id,
            submitted_by=principal.user_id,
            proposed_changes={},
            attached_files=[file_ref],
            status="pending",
        )
        session.add(pending)
    else:
        pending.attached_files = [*(pending.attached_files or []), file_ref]
        pending.submitted_by = principal.user_id or pending.submitted_by
        pending.version += 1
        pending.updated_at = datetime.now(tz=UTC)
    await session.flush()

    await write_audit(
        session,
        action="organization.document_attached",
        resource_type="company_profile_change_request",
        resource_id=pending.id,
        context=_audit_ctx(principal, ctx),
        after={"request_id": str(pending.id), "kind": doc_kind, "content_type": media},
    )
    await session.commit()
    return presenters.change_request_summary(pending, locale=locale)


# --------------------------------------------------------------------------- #
# Partner: list own change requests + withdraw                                #
# --------------------------------------------------------------------------- #


async def list_change_requests(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    status: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    await _load_org_for(session, principal=principal, org_id=org_id, action="read")
    stmt = select(CompanyProfileChangeRequest).where(
        CompanyProfileChangeRequest.org_id == org_id
    )
    if status is not None:
        stmt = stmt.where(CompanyProfileChangeRequest.status == status)
    stmt = stmt.order_by(CompanyProfileChangeRequest.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [presenters.change_request_summary(r, locale=locale) for r in rows]


async def withdraw_change_request(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    req_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _load_org_for(session, principal=principal, org_id=org_id, action="update")
    req = await _load_request_locked(session, req_id)
    if req is None or req.org_id != org_id:
        raise ResourceNotFoundError()
    if req.status != "pending":
        raise ChangeRequestNotPendingError()

    now = datetime.now(tz=UTC)
    req.status = "withdrawn"
    req.decided_at = now
    req.updated_at = now
    req.version += 1
    await session.flush()
    await write_audit(
        session,
        action="organization.change_request_withdrawn",
        resource_type="company_profile_change_request",
        resource_id=req.id,
        context=_audit_ctx(principal, ctx),
        after={"request_id": str(req.id)},
    )
    await session.commit()
    return presenters.change_request_summary(req, locale=locale)


# --------------------------------------------------------------------------- #
# University reviewer: queue + approve/reject                                 #
# --------------------------------------------------------------------------- #


async def _require_university_reviewer(session: AsyncSession, principal: Principal) -> None:
    """University oversight gate: ``partners:manage`` + acting org is university.

    Mirrors ``crm_service._require_university_manage``. A partner Admin holds
    ``*:*`` (which would match ``partners:manage``); the org-type check keeps the
    company-approval surface university-only. Superadmin bypasses.
    """

    permission_checker.require(principal, "partners", "manage")
    if principal.is_superadmin:
        return
    from app.modules.organization.application import org_reporting_facade

    if principal.org_id is None or not await org_reporting_facade.is_university_org(
        session, principal.org_id
    ):
        raise NotUniversityActorError()


async def list_approval_queue(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = "pending",
    locale: str = "vi",
) -> list[dict]:
    await _require_university_reviewer(session, principal)
    stmt = select(CompanyProfileChangeRequest, Organization.display_name).join(
        Organization, Organization.id == CompanyProfileChangeRequest.org_id
    )
    if status is not None:
        stmt = stmt.where(CompanyProfileChangeRequest.status == status)
    stmt = stmt.order_by(CompanyProfileChangeRequest.created_at.asc())
    rows = (await session.execute(stmt)).all()
    return [
        presenters.change_request_summary(req, company_name=name, locale=locale)
        for req, name in rows
    ]


async def get_approval(
    session: AsyncSession, *, principal: Principal, req_id: uuid.UUID, locale: str = "vi"
) -> dict:
    await _require_university_reviewer(session, principal)
    row = (
        await session.execute(
            select(CompanyProfileChangeRequest, Organization.display_name)
            .join(Organization, Organization.id == CompanyProfileChangeRequest.org_id)
            .where(CompanyProfileChangeRequest.id == req_id)
        )
    ).first()
    if row is None:
        raise ResourceNotFoundError()
    req, name = row
    return presenters.change_request_summary(req, company_name=name, locale=locale)


async def approve_change_request(
    session: AsyncSession,
    *,
    principal: Principal,
    req_id: uuid.UUID,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_reviewer(session, principal)
    req = await _load_request_locked(session, req_id)
    if req is None:
        raise ResourceNotFoundError()
    if version is not None and version != req.version:
        raise VersionConflictError()
    org = await _get_org(session, req.org_id)
    if req.status == "approved":  # idempotent
        return {
            "status": "approved",
            "request": presenters.change_request_summary(req, locale=locale),
            "profile": presenters.company_profile_detail(org, locale=locale),
        }
    if req.status != "pending":
        raise ChangeRequestNotPendingError()

    applied_fields: list[str] = []
    for field, diff in (req.proposed_changes or {}).items():
        if field not in SENSITIVE_FIELDS:
            continue
        new_value = diff.get("to") if isinstance(diff, dict) else diff
        setattr(org, field, new_value)
        applied_fields.append(field)

    doc_count = len(req.attached_files or [])
    if doc_count:
        approved_docs = [
            {**f, "approved_at": datetime.now(tz=UTC).isoformat()}
            for f in (req.attached_files or [])
        ]
        org.verification_documents = [*(org.verification_documents or []), *approved_docs]
    if applied_fields or doc_count:
        org.version += 1

    now = datetime.now(tz=UTC)
    req.status = "approved"
    req.reviewer_id = principal.user_id
    req.review_note = note
    req.decided_at = now
    req.updated_at = now
    req.version += 1
    await session.flush()

    await write_audit(
        session,
        action="organization.change_request_approved",
        resource_type="organization",
        resource_id=org.id,
        context=_audit_ctx(principal, ctx),
        after={
            "request_id": str(req.id),
            "fields": sorted(applied_fields),
            "documents": doc_count,
        },
    )
    await session.commit()
    return {
        "status": "approved",
        "request": presenters.change_request_summary(req, locale=locale),
        "profile": presenters.company_profile_detail(org, locale=locale),
    }


async def reject_change_request(
    session: AsyncSession,
    *,
    principal: Principal,
    req_id: uuid.UUID,
    reason: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_reviewer(session, principal)
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})
    req = await _load_request_locked(session, req_id)
    if req is None:
        raise ResourceNotFoundError()
    if version is not None and version != req.version:
        raise VersionConflictError()
    if req.status == "rejected":  # idempotent
        return presenters.change_request_summary(req, locale=locale)
    if req.status != "pending":
        raise ChangeRequestNotPendingError()

    now = datetime.now(tz=UTC)
    req.status = "rejected"
    req.reviewer_id = principal.user_id
    req.review_note = reason.strip()
    req.decided_at = now
    req.updated_at = now
    req.version += 1
    await session.flush()
    await write_audit(
        session,
        action="organization.change_request_rejected",
        resource_type="company_profile_change_request",
        resource_id=req.id,
        context=_audit_ctx(principal, ctx),
        after={"request_id": str(req.id), "org_id": str(req.org_id)},
    )
    await session.commit()
    return presenters.change_request_summary(req, locale=locale)


# --------------------------------------------------------------------------- #
# Signed company-document serving (bearer-token capability, like /cv-files)   #
# --------------------------------------------------------------------------- #


async def serve_company_document(session: AsyncSession, *, token: str) -> ServedDocument:
    """Resolve a signed company-document token to bytes, or ``404``.

    The token is the short-lived bearer capability minted only into RBAC-gated
    responses. It references a resource (kind + ids), never a storage key.
    """

    try:
        payload = storage_facade.verify_signed_token(token)
    except storage_facade.SignedTokenError as exc:
        raise ResourceNotFoundError() from exc

    kind = payload.get("kind")
    file_id = payload.get("file_id")
    if kind not in (
        presenters.DOC_KIND_CHANGE_REQUEST,
        presenters.DOC_KIND_VERIFICATION,
    ) or not file_id:
        raise ResourceNotFoundError()

    files: list[dict[str, Any]] = []
    try:
        if kind == presenters.DOC_KIND_CHANGE_REQUEST:
            req_id = uuid.UUID(str(payload.get("req_id")))
            req = (
                await session.execute(
                    select(CompanyProfileChangeRequest).where(
                        CompanyProfileChangeRequest.id == req_id
                    )
                )
            ).scalar_one_or_none()
            files = list(req.attached_files or []) if req else []
        else:
            org_id = uuid.UUID(str(payload.get("org_id")))
            org = (
                await session.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            files = list(org.verification_documents or []) if org else []
    except (ValueError, TypeError) as exc:
        raise ResourceNotFoundError() from exc

    match = next((f for f in files if str(f.get("id")) == str(file_id)), None)
    if match is None:
        raise ResourceNotFoundError()
    storage_key = match.get("storage_key")
    if not storage_key:
        raise ResourceNotFoundError()
    try:
        content = storage_facade.load(storage_key)
    except storage_facade.StorageError as exc:
        raise ResourceNotFoundError() from exc
    return ServedDocument(
        content=content,
        media_type=str(match.get("content_type") or "application/octet-stream"),
        filename=str(match.get("filename") or "document"),
    )
