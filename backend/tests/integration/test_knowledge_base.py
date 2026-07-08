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
    KB_AUDIENCE_APPLICANT_FACING,
    KB_AUDIENCE_INTERNAL,
    KB_SCOPE_JOB,
    KB_SCOPE_PARTNER,
    KB_SCOPE_PLATFORM,
)
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import GUEST

from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin

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
# Audience + department isolation (security)                                   #
# --------------------------------------------------------------------------- #


async def _add_active_application(db_session, *, user_id, org_id) -> None:
    """Insert a minimal active application row (FK-off SQLite test harness)."""
    from app.modules.recruitment.domain.models import Application

    db_session.add(
        Application(
            id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            applicant_id=user_id,
            org_id=org_id,
            status="submitted",
        )
    )
    await db_session.flush()


async def test_internal_partner_kb_isolated_from_other_org(db_session) -> None:
    """Org B (even as admin) can never read Org A's INTERNAL knowledge base."""
    _ua, org_a, admin_a = await make_org_with_admin(
        db_session, org_type="partner", display_name="Org A"
    )
    _ub, _org_b, admin_b = await make_org_with_admin(
        db_session, org_type="partner", display_name="Org B"
    )

    kb = await kb_service.create_kb(
        db_session,
        principal=admin_a,
        name="Internal Playbook",
        scope=KB_SCOPE_PARTNER,
        org_id=org_a.id,
        audience=KB_AUDIENCE_INTERNAL,
    )

    ids_for_b = await kb_service.get_kb_ids_for_query(db_session, principal=admin_b)
    assert uuid.UUID(kb["id"]) not in ids_for_b
    ids_for_a = await kb_service.get_kb_ids_for_query(db_session, principal=admin_a)
    assert uuid.UUID(kb["id"]) in ids_for_a


async def test_internal_kb_hidden_from_applicant_but_applicant_facing_visible(
    db_session,
) -> None:
    """A student applicant reads APPLICANT_FACING KBs but never INTERNAL ones."""
    student_user, student = await make_student(db_session)
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    await _add_active_application(db_session, user_id=student_user.id, org_id=org.id)

    internal_kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Internal Comp Bands",
        scope=KB_SCOPE_PARTNER,
        org_id=org.id,
        audience=KB_AUDIENCE_INTERNAL,
    )
    public_kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Applicant FAQ",
        scope=KB_SCOPE_PARTNER,
        org_id=org.id,
        audience=KB_AUDIENCE_APPLICANT_FACING,
    )

    ids = await kb_service.get_kb_ids_for_query(db_session, principal=student)
    assert uuid.UUID(public_kb["id"]) in ids, "applicant must read applicant_facing KB"
    assert uuid.UUID(internal_kb["id"]) not in ids, "applicant must NOT read internal KB"


async def test_department_scoped_internal_kb_isolation(db_session) -> None:
    """A member of dept X reads dept-X + whole-org KBs, never a dept-Y KB."""
    from app.modules.organization.domain.models import (
        Department,
        MembershipDepartment,
    )

    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    dept_x = Department(id=uuid.uuid4(), org_id=org.id, name="Engineering")
    dept_y = Department(id=uuid.uuid4(), org_id=org.id, name="Finance")
    db_session.add_all([dept_x, dept_y])
    await db_session.flush()

    # A plain member with only knowledge_base:read, assigned to department X.
    _mu, membership, member = await add_member(
        db_session, org=org, permissions=[("knowledge_base", "read")]
    )
    db_session.add(
        MembershipDepartment(membership_id=membership.id, department_id=dept_x.id)
    )
    await db_session.commit()

    kb_x = await kb_service.create_kb(
        db_session, principal=admin, name="Eng Handbook",
        scope=KB_SCOPE_PARTNER, org_id=org.id,
        audience=KB_AUDIENCE_INTERNAL, department_id=dept_x.id,
    )
    kb_y = await kb_service.create_kb(
        db_session, principal=admin, name="Finance Handbook",
        scope=KB_SCOPE_PARTNER, org_id=org.id,
        audience=KB_AUDIENCE_INTERNAL, department_id=dept_y.id,
    )
    kb_all = await kb_service.create_kb(
        db_session, principal=admin, name="Org Handbook",
        scope=KB_SCOPE_PARTNER, org_id=org.id, audience=KB_AUDIENCE_INTERNAL,
    )

    ids = await kb_service.get_kb_ids_for_query(db_session, principal=member)
    assert uuid.UUID(kb_x["id"]) in ids, "dept-X member reads dept-X KB"
    assert uuid.UUID(kb_all["id"]) in ids, "dept-X member reads whole-org KB"
    assert uuid.UUID(kb_y["id"]) not in ids, "dept-X member must NOT read dept-Y KB"


# --------------------------------------------------------------------------- #
# Admin gate (RBAC at service layer)                                          #
# --------------------------------------------------------------------------- #


async def test_non_privileged_member_cannot_create_kb(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(db_session, org_type="partner")
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("jobs", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await kb_service.create_kb(
            db_session, principal=member, name="Sneaky KB",
            scope=KB_SCOPE_PARTNER, org_id=org.id,
        )


async def test_non_privileged_member_cannot_upload_document(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session, principal=admin, name="Org KB",
        scope=KB_SCOPE_PARTNER, org_id=org.id,
    )
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("jobs", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await kb_service.upload_document(
            db_session, principal=member, kb_id=uuid.UUID(kb["id"]),
            title="secret.txt", file_path="kb/x/secret.txt",
            mime_type="text/plain", file_size_bytes=10,
        )


async def test_member_with_manage_can_upload(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session, principal=admin, name="Org KB",
        scope=KB_SCOPE_PARTNER, org_id=org.id,
    )
    _mu, _m, manager = await add_member(
        db_session, org=org, permissions=[("knowledge_base", "manage")]
    )
    doc = await kb_service.upload_document(
        db_session, principal=manager, kb_id=uuid.UUID(kb["id"]),
        title="policy.txt", file_path="kb/x/policy.txt",
        mime_type="text/plain", file_size_bytes=12,
    )
    assert doc["status"] == "pending"


# --------------------------------------------------------------------------- #
# Storage fix + async ingestion + energy metering                             #
# --------------------------------------------------------------------------- #


async def test_uploaded_bytes_ingest_to_done_with_chunks_and_meter(db_session) -> None:
    """The storage fix: bytes saved via save_bytes are loaded by ingestion, the
    document reaches DONE with chunks, and the embedding pass debits AI energy."""
    from app.ai.energy.constants import unit_cost
    from app.ai.observability.billable_usage import FEATURE_EMBEDDINGS
    from app.ai.observability.models import AiBillableUsage
    from app.modules.documents.infrastructure.storage import set_storage
    from app.modules.knowledge_base.application.ingest_task import run_ingest
    from app.modules.knowledge_base.domain.models import (
        DOC_STATUS_DONE,
        KnowledgeBaseDocument,
    )
    from app.shared.storage import save_bytes
    from sqlalchemy import select

    from tests.documents_utils import InMemoryStorage

    set_storage(InMemoryStorage())
    try:
        _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
        kb = await kb_service.create_kb(
            db_session, principal=admin, name="Internal Docs",
            scope=KB_SCOPE_PARTNER, org_id=org.id, audience=KB_AUDIENCE_INTERNAL,
        )
        kb_id = uuid.UUID(kb["id"])

        body = (
            b"Company Leave Policy\n\n"
            b"Employees may request annual leave through the HR portal. "
            b"Managers approve requests within three business days. "
            b"Remote work is available two days per week for engineering roles.\n"
        )
        key = save_bytes(folder=f"kb/{kb_id}", filename="leave_policy.txt", data=body)
        # Storage key is internal — never the client-supplied path.
        assert key.startswith(f"kb/{kb_id}/") and key.endswith(".txt")

        doc = KnowledgeBaseDocument(
            id=uuid.uuid4(), kb_id=kb_id, title="leave_policy.txt",
            file_path=key, mime_type="text/plain", file_size_bytes=len(body),
            status="pending",
        )
        db_session.add(doc)
        await db_session.flush()

        await run_ingest(str(doc.id), session=db_session)
        await db_session.commit()

        await db_session.refresh(doc)
        assert doc.status == DOC_STATUS_DONE
        assert doc.chunk_count > 0

        rows = (
            await db_session.execute(
                select(AiBillableUsage).where(
                    AiBillableUsage.feature_key == FEATURE_EMBEDDINGS,
                    AiBillableUsage.org_id == org.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].result_status == "success"
        assert rows[0].units_charged == unit_cost(FEATURE_EMBEDDINGS)

        # Idempotent: re-ingesting the same doc must not double-charge energy.
        await run_ingest(str(doc.id), session=db_session)
        await db_session.commit()
        rows2 = (
            await db_session.execute(
                select(AiBillableUsage).where(
                    AiBillableUsage.feature_key == FEATURE_EMBEDDINGS,
                    AiBillableUsage.org_id == org.id,
                )
            )
        ).scalars().all()
        assert len(rows2) == 1
    finally:
        set_storage(None)


async def test_ingest_blank_file_marks_failed_no_charge(db_session) -> None:
    """A blank/empty upload never fabricates a CV/doc and is charged nothing."""
    from app.ai.observability.billable_usage import FEATURE_EMBEDDINGS
    from app.ai.observability.models import AiBillableUsage
    from app.modules.documents.infrastructure.storage import set_storage
    from app.modules.knowledge_base.application.ingest_task import run_ingest
    from app.modules.knowledge_base.domain.models import (
        DOC_STATUS_FAILED,
        KnowledgeBaseDocument,
    )
    from app.shared.storage import save_bytes
    from sqlalchemy import select

    from tests.documents_utils import InMemoryStorage

    set_storage(InMemoryStorage())
    try:
        _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
        kb = await kb_service.create_kb(
            db_session, principal=admin, name="Docs",
            scope=KB_SCOPE_PARTNER, org_id=org.id,
        )
        kb_id = uuid.UUID(kb["id"])
        key = save_bytes(folder=f"kb/{kb_id}", filename="blank.txt", data=b"   \n  ")
        doc = KnowledgeBaseDocument(
            id=uuid.uuid4(), kb_id=kb_id, title="blank.txt", file_path=key,
            mime_type="text/plain", file_size_bytes=6, status="pending",
        )
        db_session.add(doc)
        await db_session.flush()

        with pytest.raises(ValueError):
            await run_ingest(str(doc.id), session=db_session)
        await db_session.commit()

        await db_session.refresh(doc)
        assert doc.status == DOC_STATUS_FAILED
        assert doc.chunk_count == 0
        charged = (
            await db_session.execute(
                select(AiBillableUsage).where(
                    AiBillableUsage.feature_key == FEATURE_EMBEDDINGS,
                    AiBillableUsage.org_id == org.id,
                    AiBillableUsage.units_charged > 0,
                )
            )
        ).scalars().all()
        assert charged == []
    finally:
        set_storage(None)


# --------------------------------------------------------------------------- #
# Audit trail — every KB write is audited (.claude/rules/backend.md            #
# non-negotiable). Storage keys / file contents must NEVER reach the payload.  #
# --------------------------------------------------------------------------- #


async def _audit_rows(db_session, *, action: str, resource_id: uuid.UUID) -> list:
    from app.shared.models import AuditLog
    from sqlalchemy import select

    return list(
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == action,
                    AuditLog.resource_id == resource_id,
                )
            )
        ).scalars().all()
    )


async def test_create_kb_writes_audit_record(db_session) -> None:
    """KB create emits a ``knowledge_base.create`` audit stamped with the actor,
    the actor's org, and safe scope/audience metadata."""
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Internal Playbook",
        scope=KB_SCOPE_PARTNER,
        org_id=org.id,
        audience=KB_AUDIENCE_INTERNAL,
    )

    rows = await _audit_rows(
        db_session, action="knowledge_base.create", resource_id=uuid.UUID(kb["id"])
    )
    assert len(rows) == 1
    entry = rows[0]
    assert entry.actor_id == admin.user_id
    assert entry.actor_org_id == org.id
    assert entry.resource_type == "knowledge_base"
    assert entry.after_snapshot["scope"] == "partner"
    assert entry.after_snapshot["audience"] == KB_AUDIENCE_INTERNAL
    assert entry.after_snapshot["org_id"] == str(org.id)


async def test_upload_document_writes_audit_without_storage_key(db_session) -> None:
    """Document upload emits a ``knowledge_base.document.upload`` audit with the
    filename + size, and NEVER the internal storage key (``file_path``)."""
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session,
        principal=admin,
        name="Docs KB",
        scope=KB_SCOPE_PARTNER,
        org_id=org.id,
        audience=KB_AUDIENCE_INTERNAL,
    )
    kb_id = uuid.UUID(kb["id"])
    # A recognisable internal storage key we then assert is absent from the audit.
    storage_key = f"kb/{kb_id}/SECRET-STORAGE-KEY-abc123.pdf"

    doc = await kb_service.upload_document(
        db_session,
        principal=admin,
        kb_id=kb_id,
        title="Handbook.pdf",
        file_path=storage_key,
        mime_type="application/pdf",
        file_size_bytes=2048,
        page_count=3,
    )

    rows = await _audit_rows(
        db_session,
        action="knowledge_base.document.upload",
        resource_id=uuid.UUID(doc["id"]),
    )
    assert len(rows) == 1
    entry = rows[0]
    assert entry.actor_id == admin.user_id
    assert entry.actor_org_id == org.id
    assert entry.resource_type == "knowledge_base_document"
    assert entry.after_snapshot["filename"] == "Handbook.pdf"
    assert entry.after_snapshot["kb_id"] == str(kb_id)
    assert entry.after_snapshot["kb_scope"] == "partner"
    assert entry.after_snapshot["file_size_bytes"] == 2048

    # The storage key must NOT leak into the audit payload under any field.
    import json as _json

    payload = _json.dumps(entry.after_snapshot)
    assert "file_path" not in entry.after_snapshot
    assert storage_key not in payload
    assert "SECRET-STORAGE-KEY" not in payload


async def test_delete_document_writes_audit_without_storage_key(db_session) -> None:
    """Document delete emits a ``knowledge_base.document.delete`` audit; the
    storage key never appears in the ``before`` snapshot."""
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session, principal=admin, name="Docs KB", scope=KB_SCOPE_PARTNER, org_id=org.id
    )
    kb_id = uuid.UUID(kb["id"])
    storage_key = f"kb/{kb_id}/CONFIDENTIAL-key-xyz.pdf"
    doc = await kb_service.upload_document(
        db_session,
        principal=admin,
        kb_id=kb_id,
        title="Policy.pdf",
        file_path=storage_key,
        mime_type="application/pdf",
        file_size_bytes=512,
    )
    doc_id = uuid.UUID(doc["id"])

    result = await kb_service.delete_document(
        db_session, principal=admin, document_id=doc_id
    )
    assert result["deleted"] is True

    rows = await _audit_rows(
        db_session, action="knowledge_base.document.delete", resource_id=doc_id
    )
    assert len(rows) == 1
    entry = rows[0]
    assert entry.actor_id == admin.user_id
    assert entry.actor_org_id == org.id
    assert entry.resource_type == "knowledge_base_document"
    assert entry.before_snapshot["filename"] == "Policy.pdf"
    assert entry.before_snapshot["kb_id"] == str(kb_id)

    import json as _json

    payload = _json.dumps(entry.before_snapshot)
    assert "file_path" not in entry.before_snapshot
    assert storage_key not in payload
    assert "CONFIDENTIAL-key" not in payload


async def test_delete_already_deleted_document_does_not_double_audit(db_session) -> None:
    """Idempotent re-delete of an already-removed document writes no new audit."""
    _u, org, admin = await make_org_with_admin(db_session, org_type="partner")
    kb = await kb_service.create_kb(
        db_session, principal=admin, name="Docs KB", scope=KB_SCOPE_PARTNER, org_id=org.id
    )
    kb_id = uuid.UUID(kb["id"])
    doc = await kb_service.upload_document(
        db_session,
        principal=admin,
        kb_id=kb_id,
        title="Once.pdf",
        file_path=f"kb/{kb_id}/once.pdf",
        mime_type="application/pdf",
        file_size_bytes=128,
    )
    doc_id = uuid.UUID(doc["id"])

    await kb_service.delete_document(db_session, principal=admin, document_id=doc_id)
    await kb_service.delete_document(db_session, principal=admin, document_id=doc_id)

    rows = await _audit_rows(
        db_session, action="knowledge_base.document.delete", resource_id=doc_id
    )
    assert len(rows) == 1
