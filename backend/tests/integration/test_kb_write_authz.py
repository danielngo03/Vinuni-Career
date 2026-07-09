"""KB write-authorization tests — the RAG-poisoning gate.

``knowledge_base_query`` surfaces KB documents to users as authoritative
answers, so WRITE access must be far narrower than READ. Before this gate any
authenticated user with an org could inject documents into the platform KB (seen
by everyone) or another org's KB (cross-tenant AI-content injection). These
tests pin the fail-closed rules:

- Platform KB: only platform/university staff (or superadmin) may write.
- Partner/job KB: only a member of the OWNING org may write.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.knowledge_base.application import kb_service
from app.modules.knowledge_base.domain.models import KB_SCOPE_PARTNER, KB_SCOPE_PLATFORM
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import GUEST

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


async def _make_platform_kb(db_session, uni) -> uuid.UUID:
    kb = await kb_service.create_kb(
        db_session, principal=uni, name="Handbook", scope=KB_SCOPE_PLATFORM
    )
    return uuid.UUID(kb["id"])


# --------------------------------------------------------------------------- #
# Platform KB                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_student_cannot_upload_to_platform_kb(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    kb_id = await _make_platform_kb(db_session, uni)
    _user, student = await make_student(db_session)

    with pytest.raises(PermissionDeniedError):
        await kb_service.upload_document(
            db_session,
            principal=student,
            kb_id=kb_id,
            title="poison.pdf",
            file_path="kb/x/poison.pdf",
        )


@pytest.mark.asyncio
async def test_partner_cannot_upload_to_platform_kb(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    kb_id = await _make_platform_kb(db_session, uni)
    # A partner org admin has *:* over their OWN org, but the platform KB is
    # global — a partner must never inject content all users then see.
    _pu, _porg, partner = await make_org_with_admin(db_session, org_type="partner")

    with pytest.raises(PermissionDeniedError):
        await kb_service.upload_document(
            db_session,
            principal=partner,
            kb_id=kb_id,
            title="ad.pdf",
            file_path="kb/x/ad.pdf",
        )


@pytest.mark.asyncio
async def test_university_staff_can_upload_to_platform_kb(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    kb_id = await _make_platform_kb(db_session, uni)

    doc = await kb_service.upload_document(
        db_session,
        principal=uni,
        kb_id=kb_id,
        title="policy.pdf",
        file_path="kb/x/policy.pdf",
    )
    assert doc["id"]


# --------------------------------------------------------------------------- #
# Partner (org-scoped) KB                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_partner_cannot_upload_to_another_orgs_kb(db_session) -> None:
    _ua, org_a, admin_a = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session,
        principal=admin_a,
        name="Org A KB",
        scope=KB_SCOPE_PARTNER,
        org_id=org_a.id,
    )
    kb_id = uuid.UUID(kb["id"])

    # A different org's admin must be refused (tenant isolation).
    _ub, _org_b, admin_b = await make_org_with_admin(db_session, org_type="partner")
    with pytest.raises(PermissionDeniedError):
        await kb_service.upload_document(
            db_session,
            principal=admin_b,
            kb_id=kb_id,
            title="cross.pdf",
            file_path="kb/x/cross.pdf",
        )


@pytest.mark.asyncio
async def test_org_owner_can_upload_to_own_kb(db_session) -> None:
    _ua, org_a, admin_a = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session,
        principal=admin_a,
        name="Org A KB",
        scope=KB_SCOPE_PARTNER,
        org_id=org_a.id,
    )
    kb_id = uuid.UUID(kb["id"])

    doc = await kb_service.upload_document(
        db_session,
        principal=admin_a,
        kb_id=kb_id,
        title="onboarding.pdf",
        file_path="kb/x/onboarding.pdf",
    )
    assert doc["id"]


# --------------------------------------------------------------------------- #
# create_kb is gated too                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_student_cannot_create_platform_kb(db_session) -> None:
    _user, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await kb_service.create_kb(
            db_session, principal=student, name="rogue", scope=KB_SCOPE_PLATFORM
        )


@pytest.mark.asyncio
async def test_guest_cannot_create_kb(db_session) -> None:
    with pytest.raises(AuthRequiredError):
        await kb_service.create_kb(
            db_session, principal=GUEST, name="rogue", scope=KB_SCOPE_PLATFORM
        )
