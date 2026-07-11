"""Company profile + university approval workflow (owner decision 2026-07-10).

Covers the sensitive-vs-immediate write split, the university approve/reject
queue, tenant isolation (cross-org 404), RBAC (partner submit vs university
approve), file safety (signed URLs, no storage-key leak), and concurrency
(single open request; stale double-apply guarded).
"""

from __future__ import annotations

import json

import pytest
from app.modules.documents.infrastructure import storage
from app.modules.organization.application import company_profile_service as svc
from app.modules.organization.application.errors import (
    ChangeRequestNotPendingError,
    InvalidCompanyDocumentError,
    NoProfileChangesError,
)
from app.modules.organization.domain.models import CompanyProfileChangeRequest, Organization
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 64


class _MemoryStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def load(self, key: str) -> bytes:
        try:
            return self._data[key]
        except KeyError as exc:
            raise storage.StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture(autouse=True)
def _memory_storage():
    backend = _MemoryStorage()
    storage.set_storage(backend)
    yield backend
    storage.set_storage(None)


async def _audit_count(db_session, action: str) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _university_reviewer(db_session):
    _u, uni_org, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    return uni_admin, uni_org


async def _get_org(db_session, org_id) -> Organization:
    return (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()


async def _pending_rows(db_session, org_id) -> list[CompanyProfileChangeRequest]:
    return list(
        (
            await db_session.execute(
                select(CompanyProfileChangeRequest).where(
                    CompanyProfileChangeRequest.org_id == org_id,
                    CompanyProfileChangeRequest.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# Cosmetic fields apply immediately                                           #
# --------------------------------------------------------------------------- #


async def test_cosmetic_update_applies_immediately(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    result = await svc.update_company_profile(
        db_session,
        principal=admin,
        org_id=org.id,
        payload={"description": "A great place to work here.", "website_url": "https://acme.io"},
        ctx=CTX,
    )
    assert result["requires_approval"] is False
    assert set(result["applied"]) == {"description", "website_url"}
    assert result["pending_change_request"] is None

    fresh = await _get_org(db_session, org.id)
    assert fresh.description == "A great place to work here."
    assert fresh.website_url == "https://acme.io"
    assert await _audit_count(db_session, "organization.profile_updated") == 1


async def test_display_name_applies_immediately(db_session) -> None:
    # Public display name matches the legacy immediate surface (not approval-gated).
    _u, org, admin = await make_org_with_admin(db_session, display_name="Old Name")
    result = await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"display_name": "New Name"}, ctx=CTX
    )
    assert result["requires_approval"] is False
    assert result["applied"] == ["display_name"]
    fresh = await _get_org(db_session, org.id)
    assert fresh.display_name == "New Name"


async def test_no_recognized_fields_raises(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(NoProfileChangesError):
        await svc.update_company_profile(
            db_session, principal=admin, org_id=org.id, payload={"unknown": "x"}, ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Sensitive fields => pending request, live profile unchanged                 #
# --------------------------------------------------------------------------- #


async def test_sensitive_update_creates_pending_and_live_unchanged(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    result = await svc.update_company_profile(
        db_session,
        principal=admin,
        org_id=org.id,
        payload={"legal_name": "Acme Legal LLC", "tax_code": "0101234567"},
        ctx=CTX,
    )
    assert result["requires_approval"] is True
    assert result["applied"] == []
    req = result["pending_change_request"]
    assert req["status"] == "pending"
    changed = {c["field"] for c in req["changes"]}
    assert changed == {"legal_name", "tax_code"}

    # Live profile must NOT have changed yet.
    fresh = await _get_org(db_session, org.id)
    assert fresh.legal_name is None
    assert fresh.tax_code is None
    assert await _audit_count(db_session, "organization.change_requested") == 1


async def test_mixed_update_applies_cosmetic_and_pends_sensitive(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    result = await svc.update_company_profile(
        db_session,
        principal=admin,
        org_id=org.id,
        payload={"description": "New about text long enough.", "tax_code": "0109999999"},
        ctx=CTX,
    )
    assert result["applied"] == ["description"]
    assert result["requires_approval"] is True
    fresh = await _get_org(db_session, org.id)
    assert fresh.description == "New about text long enough."
    assert fresh.tax_code is None  # still pending


async def test_second_sensitive_edit_merges_into_single_pending(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"legal_name": "First LLC"}, ctx=CTX
    )
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"tax_code": "0102003004"}, ctx=CTX
    )
    pendings = await _pending_rows(db_session, org.id)
    assert len(pendings) == 1  # merged, not a second competing diff
    assert set(pendings[0].proposed_changes.keys()) == {"legal_name", "tax_code"}


# --------------------------------------------------------------------------- #
# File attach => pending, signed URL, no storage-key leak                     #
# --------------------------------------------------------------------------- #


async def test_document_attach_creates_pending_with_signed_url(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    req = await svc.attach_company_document(
        db_session,
        principal=admin,
        org_id=org.id,
        filename="license.pdf",
        data=PDF_BYTES,
        content_type="application/pdf",
        kind="business_license",
        ctx=CTX,
    )
    assert req["status"] == "pending"
    assert len(req["documents"]) == 1
    doc = req["documents"][0]
    assert doc["kind"] == "business_license"
    assert "/organizations/company-documents/" in doc["url"]

    # storage_key must NEVER appear anywhere in the serialized response.
    assert "storage_key" not in json.dumps(req)

    # Live profile has no verification documents until approval.
    fresh = await _get_org(db_session, org.id)
    assert fresh.verification_documents == []
    assert await _audit_count(db_session, "organization.document_attached") == 1


async def test_document_rejects_unsupported_type(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(InvalidCompanyDocumentError):
        await svc.attach_company_document(
            db_session,
            principal=admin,
            org_id=org.id,
            filename="evil.exe",
            data=b"MZ\x00\x00",
            content_type="application/octet-stream",
            kind="other",
            ctx=CTX,
        )


async def test_serve_company_document_returns_bytes(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    req = await svc.attach_company_document(
        db_session,
        principal=admin,
        org_id=org.id,
        filename="license.pdf",
        data=PDF_BYTES,
        content_type="application/pdf",
        kind="legal_document",
        ctx=CTX,
    )
    url = req["documents"][0]["url"]
    token = url.rsplit("/", 1)[-1]
    served = await svc.serve_company_document(db_session, token=token)
    assert served.content == PDF_BYTES
    assert served.media_type == "application/pdf"


async def test_serve_rejects_bad_token(db_session) -> None:
    with pytest.raises(ResourceNotFoundError):
        await svc.serve_company_document(db_session, token="not-a-valid-token")


# --------------------------------------------------------------------------- #
# University approve / reject                                                 #
# --------------------------------------------------------------------------- #


async def test_university_approve_applies_changes_and_files_and_audits(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session,
        principal=admin,
        org_id=org.id,
        payload={"legal_name": "Acme Legal LLC", "tax_code": "0101234567"},
        ctx=CTX,
    )
    await svc.attach_company_document(
        db_session,
        principal=admin,
        org_id=org.id,
        filename="license.pdf",
        data=PDF_BYTES,
        content_type="application/pdf",
        kind="business_license",
        ctx=CTX,
    )
    pending = (await _pending_rows(db_session, org.id))[0]

    uni_admin, _uni = await _university_reviewer(db_session)
    out = await svc.approve_change_request(
        db_session, principal=uni_admin, req_id=pending.id, note="Verified.", ctx=CTX
    )
    assert out["status"] == "approved"

    fresh = await _get_org(db_session, org.id)
    assert fresh.legal_name == "Acme Legal LLC"
    assert fresh.tax_code == "0101234567"
    assert len(fresh.verification_documents) == 1
    assert await _audit_count(db_session, "organization.change_request_approved") == 1
    # No open pending request remains.
    assert await _pending_rows(db_session, org.id) == []


async def test_university_reject_leaves_live_unchanged_with_reason(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"legal_name": "Sketchy Inc"}, ctx=CTX
    )
    pending = (await _pending_rows(db_session, org.id))[0]
    uni_admin, _uni = await _university_reviewer(db_session)
    out = await svc.reject_change_request(
        db_session,
        principal=uni_admin,
        req_id=pending.id,
        reason="Legal name does not match tax registry.",
        ctx=CTX,
    )
    assert out["status"] == "rejected"
    assert out["review_note"] == "Legal name does not match tax registry."
    fresh = await _get_org(db_session, org.id)
    assert fresh.legal_name is None
    assert await _audit_count(db_session, "organization.change_request_rejected") == 1


async def test_approval_queue_lists_pending(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"legal_name": "Acme LLC"}, ctx=CTX
    )
    uni_admin, _uni = await _university_reviewer(db_session)
    queue = await svc.list_approval_queue(db_session, principal=uni_admin, status="pending")
    assert len(queue) == 1
    assert queue[0]["company_name"] == "Acme"


# --------------------------------------------------------------------------- #
# Concurrency / idempotency guards                                            #
# --------------------------------------------------------------------------- #


async def test_double_approve_is_idempotent(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"tax_code": "0105005005"}, ctx=CTX
    )
    pending = (await _pending_rows(db_session, org.id))[0]
    uni_admin, _uni = await _university_reviewer(db_session)
    await svc.approve_change_request(db_session, principal=uni_admin, req_id=pending.id, ctx=CTX)
    # Second approve does not double-apply or error.
    out = await svc.approve_change_request(
        db_session, principal=uni_admin, req_id=pending.id, ctx=CTX
    )
    assert out["status"] == "approved"
    assert await _audit_count(db_session, "organization.change_request_approved") == 1


async def test_reject_after_approve_conflicts(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"tax_code": "0106006006"}, ctx=CTX
    )
    pending = (await _pending_rows(db_session, org.id))[0]
    uni_admin, _uni = await _university_reviewer(db_session)
    await svc.approve_change_request(db_session, principal=uni_admin, req_id=pending.id, ctx=CTX)
    with pytest.raises(ChangeRequestNotPendingError):
        await svc.reject_change_request(
            db_session, principal=uni_admin, req_id=pending.id, reason="too late", ctx=CTX
        )


async def test_new_request_allowed_after_previous_decided(db_session) -> None:
    # Confirms the one-pending-per-org index is PARTIAL (only bites `pending`):
    # a decided request must not block a fresh submission.
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"tax_code": "0107007007"}, ctx=CTX
    )
    first = (await _pending_rows(db_session, org.id))[0]
    uni_admin, _uni = await _university_reviewer(db_session)
    await svc.reject_change_request(
        db_session, principal=uni_admin, req_id=first.id, reason="Please resubmit.", ctx=CTX
    )
    # A brand-new sensitive edit opens a fresh pending request (no IntegrityError).
    result = await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"tax_code": "0108008008"}, ctx=CTX
    )
    assert result["requires_approval"] is True
    assert len(await _pending_rows(db_session, org.id)) == 1


async def test_withdraw_pending_leaves_live_unchanged(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"legal_name": "Draft LLC"}, ctx=CTX
    )
    pending = (await _pending_rows(db_session, org.id))[0]
    out = await svc.withdraw_change_request(
        db_session, principal=admin, org_id=org.id, req_id=pending.id, ctx=CTX
    )
    assert out["status"] == "withdrawn"
    assert await _pending_rows(db_session, org.id) == []
    fresh = await _get_org(db_session, org.id)
    assert fresh.legal_name is None


# --------------------------------------------------------------------------- #
# Tenant isolation + RBAC                                                     #
# --------------------------------------------------------------------------- #


async def test_cross_org_profile_read_is_404(db_session) -> None:
    _ua, _org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _ub, org_b, _admin_b = await make_org_with_admin(db_session, display_name="B")
    with pytest.raises(ResourceNotFoundError):
        await svc.get_company_profile(db_session, principal=admin_a, org_id=org_b.id)


async def test_cross_org_profile_update_is_404(db_session) -> None:
    _ua, _org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _ub, org_b, _admin_b = await make_org_with_admin(db_session, display_name="B")
    with pytest.raises(ResourceNotFoundError):
        await svc.update_company_profile(
            db_session, principal=admin_a, org_id=org_b.id, payload={"tax_code": "1"}, ctx=CTX
        )


async def test_member_without_update_cannot_edit(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(db_session, org=org, permissions=[("jobs", "read")])
    with pytest.raises(PermissionDeniedError):
        await svc.update_company_profile(
            db_session,
            principal=member,
            org_id=org.id,
            payload={"description": "x long enough"},
            ctx=CTX,
        )


async def test_partner_cannot_approve_change_request(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session)
    await svc.update_company_profile(
        db_session, principal=admin, org_id=org.id, payload={"legal_name": "X LLC"}, ctx=CTX
    )
    pending = (await _pending_rows(db_session, org.id))[0]
    # The partner admin holds *:* but is NOT a university actor -> denied.
    with pytest.raises(PermissionDeniedError):
        await svc.approve_change_request(
            db_session, principal=admin, req_id=pending.id, ctx=CTX
        )


async def test_university_cannot_edit_partner_profile_via_put(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session)
    uni_admin, _uni = await _university_reviewer(db_session)
    # Cross-tenant (university org != partner org) -> hidden as 404, not 403.
    with pytest.raises(ResourceNotFoundError):
        await svc.update_company_profile(
            db_session, principal=uni_admin, org_id=org.id, payload={"tax_code": "9"}, ctx=CTX
        )
