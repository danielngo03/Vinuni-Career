"""Integration tests for the Knowledge Base module (RAG ingestion + retrieval).

Covers: KB create/list, scope-gated query access (platform/partner/job),
document upload/list/get lifecycle, not-found handling, and empty-state
behaviour for search/context assembly.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.knowledge_base.application import kb_service
from app.modules.knowledge_base.domain.models import (
    KB_SCOPE_JOB,
    KB_SCOPE_PARTNER,
    KB_SCOPE_PLATFORM,
    KB_SCOPE_UNIVERSITY,
)
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import GUEST, Principal

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


def _superadmin() -> Principal:
    """A platform superadmin principal (exempt; reads every scope)."""
    return Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        is_superadmin=True,
        permissions=frozenset({"*"}),
    )


# --------------------------------------------------------------------------- #
# create_kb / list_kbs                                                        #
# --------------------------------------------------------------------------- #


async def test_create_platform_kb_visible_to_any_authenticated_user(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    _, student = await make_student(db_session)

    kb = await kb_service.create_kb(
        db_session, principal=uni, name="Career Handbook", scope=KB_SCOPE_PLATFORM
    )
    assert kb["scope"] == "platform"
    assert kb["is_active"] is True

    kbs = await kb_service.list_kbs(db_session, principal=student)
    ids = {k["id"] for k in kbs}
    assert kb["id"] in ids


async def test_guest_cannot_see_any_kb(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    await kb_service.create_kb(
        db_session, principal=uni, name="Public KB", scope=KB_SCOPE_PLATFORM
    )

    kbs = await kb_service.list_kbs(db_session, principal=GUEST)
    assert kbs == []


async def test_partner_kb_visible_to_org_member_not_to_unrelated_student(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    _, unrelated_student = await make_student(db_session)

    kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Partner Onboarding",
        scope=KB_SCOPE_PARTNER,
        org_id=org.id,
    )

    kbs_for_admin = await kb_service.list_kbs(db_session, principal=admin)
    assert kb["id"] in {k["id"] for k in kbs_for_admin}

    kbs_for_student = await kb_service.list_kbs(db_session, principal=unrelated_student)
    assert kb["id"] not in {k["id"] for k in kbs_for_student}

    ids_for_student = await kb_service.get_kb_ids_for_query(db_session, principal=unrelated_student)
    assert uuid.UUID(kb["id"]) not in ids_for_student


async def test_list_kbs_empty_when_none_exist(db_session) -> None:
    _, student = await make_student(db_session)
    kbs = await kb_service.list_kbs(db_session, principal=student)
    assert kbs == []


# --------------------------------------------------------------------------- #
# document lifecycle                                                          #
# --------------------------------------------------------------------------- #


async def test_upload_list_and_get_document_happy_path(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    kb = await kb_service.create_kb(
        db_session, principal=uni, name="Docs KB", scope=KB_SCOPE_PLATFORM
    )
    kb_id = uuid.UUID(kb["id"])

    doc = await kb_service.upload_document(
        db_session,
        principal=uni,
        kb_id=kb_id,
        title="Handbook.pdf",
        file_path=f"kb/{kb_id}/handbook.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    assert doc["status"] == "pending"
    assert doc["title"] == "Handbook.pdf"

    docs = await kb_service.list_documents(db_session, kb_id=kb_id, principal=uni)
    assert any(d["id"] == doc["id"] for d in docs)

    fetched = await kb_service.get_document(
        db_session, document_id=uuid.UUID(doc["id"]), principal=uni
    )
    assert fetched["id"] == doc["id"]


async def test_upload_document_unknown_kb_raises_value_error(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(ValueError):
        await kb_service.upload_document(
            db_session,
            principal=uni,
            kb_id=uuid.uuid4(),
            title="Ghost.pdf",
            file_path="kb/ghost/ghost.pdf",
        )


async def test_get_document_not_found_raises_value_error(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    with pytest.raises(ValueError):
        await kb_service.get_document(db_session, document_id=uuid.uuid4(), principal=uni)


async def test_list_documents_empty_for_new_kb(db_session) -> None:
    _u, _org, uni = await make_org_with_admin(db_session, org_type="university")
    kb = await kb_service.create_kb(
        db_session, principal=uni, name="Empty KB", scope=KB_SCOPE_PLATFORM
    )
    docs = await kb_service.list_documents(db_session, kb_id=uuid.UUID(kb["id"]), principal=uni)
    assert docs == []


# --------------------------------------------------------------------------- #
# search / RAG context assembly                                               #
# --------------------------------------------------------------------------- #


async def test_search_chunks_empty_when_no_kb_ids(db_session) -> None:
    chunks = await kb_service.search_chunks(db_session, query="anything", kb_ids=[])
    assert chunks == []


# NOTE: search_chunks() with non-empty kb_ids issues raw Postgres SQL (ILIKE /
# ANY(:kb_ids)) that is not portable to the SQLite test harness used by this
# suite (see docs/LOCAL_DEV_STACK.md test DB notes). We only exercise the
# empty-kb_ids fast path here; a genuine cross-dialect portability gap should
# be flagged to backend-developer rather than worked around in tests.


def test_assemble_rag_context_empty_for_no_chunks() -> None:
    assert kb_service.assemble_rag_context([]) == ""


def test_assemble_rag_context_formats_single_chunk() -> None:
    context = kb_service.assemble_rag_context(
        [
            {
                "document_title": "Handbook",
                "section_heading": "Leave Policy",
                "content": "Students may request leave via the portal.",
            }
        ]
    )
    assert "Handbook" in context
    assert "Leave Policy" in context
    assert "Students may request leave" in context


async def test_job_scope_kb_not_visible_without_active_application(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    _, student = await make_student(db_session)

    kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Job-specific KB",
        scope=KB_SCOPE_JOB,
        org_id=org.id,
        job_id=uuid.uuid4(),
    )

    kbs_for_student = await kb_service.list_kbs(db_session, principal=student)
    assert kb["id"] not in {k["id"] for k in kbs_for_student}


# --------------------------------------------------------------------------- #
# University KB scope (WS3.3) — visibility + create RBAC + scope preference     #
# --------------------------------------------------------------------------- #


async def test_university_kb_visible_to_owning_staff_and_superadmin(db_session) -> None:
    _u, uni_org, uni = await make_org_with_admin(db_session, org_type="university")

    kb = await kb_service.create_kb(
        db_session,
        principal=uni,
        name="Employer Guidelines",
        scope=KB_SCOPE_UNIVERSITY,
        org_id=uni_org.id,
    )
    assert kb["scope"] == "university"
    kb_uuid = uuid.UUID(kb["id"])

    ids_for_staff = await kb_service.get_kb_ids_for_query(db_session, principal=uni)
    assert kb_uuid in ids_for_staff
    assert kb["id"] in {k["id"] for k in await kb_service.list_kbs(db_session, principal=uni)}

    ids_for_sa = await kb_service.get_kb_ids_for_query(db_session, principal=_superadmin())
    assert kb_uuid in ids_for_sa


async def test_university_kb_not_visible_to_student_partner_or_guest(db_session) -> None:
    _u, uni_org, uni = await make_org_with_admin(db_session, org_type="university")
    _pu, _porg, partner = await make_org_with_admin(db_session, org_type="partner")
    _, student = await make_student(db_session)

    kb = await kb_service.create_kb(
        db_session,
        principal=uni,
        name="Moderation Playbook",
        scope=KB_SCOPE_UNIVERSITY,
        org_id=uni_org.id,
    )
    kb_uuid = uuid.UUID(kb["id"])

    for principal in (student, partner, GUEST):
        ids = await kb_service.get_kb_ids_for_query(db_session, principal=principal)
        assert kb_uuid not in ids
        kbs = await kb_service.list_kbs(db_session, principal=principal)
        assert kb["id"] not in {k["id"] for k in kbs}


async def test_university_kb_not_visible_to_a_different_university_org(db_session) -> None:
    # Defense in depth: org_id must match — another university org's staffer
    # (never the owning org) cannot read this org's institutional KB.
    _u, uni_org, uni = await make_org_with_admin(db_session, org_type="university")
    _u2, _uni2_org, other_uni = await make_org_with_admin(
        db_session, org_type="university", display_name="Other University"
    )

    kb = await kb_service.create_kb(
        db_session, principal=uni, name="Policies", scope=KB_SCOPE_UNIVERSITY, org_id=uni_org.id
    )
    ids = await kb_service.get_kb_ids_for_query(db_session, principal=other_uni)
    assert uuid.UUID(kb["id"]) not in ids


async def test_create_university_kb_denied_for_student_and_partner(db_session) -> None:
    _u, uni_org, _uni = await make_org_with_admin(db_session, org_type="university")
    _, student = await make_student(db_session)
    _pu, _porg, partner = await make_org_with_admin(db_session, org_type="partner")

    # Student (no org) cannot create a university KB.
    with pytest.raises(PermissionDeniedError):
        await kb_service.create_kb(
            db_session, principal=student, name="X", scope=KB_SCOPE_UNIVERSITY, org_id=uni_org.id
        )
    # Partner acting from its own org cannot create a KB owned by the university org.
    with pytest.raises(PermissionDeniedError):
        await kb_service.create_kb(
            db_session, principal=partner, name="X", scope=KB_SCOPE_UNIVERSITY, org_id=uni_org.id
        )
    # Partner cannot mint a "university" KB for its own (partner) org either.
    with pytest.raises(PermissionDeniedError):
        await kb_service.create_kb(
            db_session, principal=partner, name="X", scope=KB_SCOPE_UNIVERSITY, org_id=partner.org_id
        )


async def test_create_university_kb_allowed_for_superadmin(db_session) -> None:
    _u, uni_org, _uni = await make_org_with_admin(db_session, org_type="university")
    kb = await kb_service.create_kb(
        db_session,
        principal=_superadmin(),
        name="Superadmin Institutional KB",
        scope=KB_SCOPE_UNIVERSITY,
        org_id=uni_org.id,
    )
    assert kb["scope"] == "university"


async def test_university_query_scopes_prefer_university_and_platform(db_session) -> None:
    _u, uni_org, uni = await make_org_with_admin(db_session, org_type="university")
    _pu, porg, partner = await make_org_with_admin(db_session, org_type="partner")

    uni_kb = await kb_service.create_kb(
        db_session, principal=uni, name="Uni", scope=KB_SCOPE_UNIVERSITY, org_id=uni_org.id
    )
    plat_kb = await kb_service.create_kb(
        db_session, principal=uni, name="Plat", scope=KB_SCOPE_PLATFORM
    )
    partner_kb = await kb_service.create_kb(
        db_session, principal=partner, name="Partner", scope=KB_SCOPE_PARTNER, org_id=porg.id
    )

    # A university staffer under the university scope filter gets institutional +
    # platform knowledge (never partner/job).
    scoped_uni = await kb_service.get_kb_ids_for_query(
        db_session, principal=uni, scopes=kb_service.UNIVERSITY_QUERY_SCOPES
    )
    assert uuid.UUID(uni_kb["id"]) in scoped_uni
    assert uuid.UUID(plat_kb["id"]) in scoped_uni

    # A partner admin CAN read the platform + their own partner KB by default,
    # and never the university KB.
    default_partner = await kb_service.get_kb_ids_for_query(db_session, principal=partner)
    assert uuid.UUID(partner_kb["id"]) in default_partner
    assert uuid.UUID(plat_kb["id"]) in default_partner
    assert uuid.UUID(uni_kb["id"]) not in default_partner

    # Applying the university scope filter DROPS the (readable) partner KB purely
    # by scope, keeps platform, and still refuses the university KB for a partner.
    scoped_partner = await kb_service.get_kb_ids_for_query(
        db_session, principal=partner, scopes=kb_service.UNIVERSITY_QUERY_SCOPES
    )
    assert uuid.UUID(partner_kb["id"]) not in scoped_partner
    assert uuid.UUID(uni_kb["id"]) not in scoped_partner
    assert uuid.UUID(plat_kb["id"]) in scoped_partner


async def test_search_university_knowledge_no_kb_returns_safe_empty(db_session) -> None:
    from app.modules.ai_assistant.application.tools import university

    _u, _uni_org, uni = await make_org_with_admin(db_session, org_type="university")
    # No university/platform KB exists → the tool short-circuits before retrieval.
    result = await university.search_university_knowledge(
        db_session, uni, {"query": "leave policy"}
    )
    assert result["ok"] is True
    assert result["found"] is False
    assert result["chunks"] == []
