"""Documents / CV Studio (non-AI) service tests.

Covers: template seed + list, upload happy + every negative quality_code, parse-run
owner-only (cross-owner 404), CV create from a template (blank_template) + rejection
of every removed/unknown creation_mode, section upsert optimistic-version conflict
(409), duplicate never mutates
the source, export -> PDF + signed-URL + signed-token validation (bad/expired token
rejected), application snapshot immutability + cross-owner 404 + partner watermark
seam, audit on writes, and no-leak assertions.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.extraction import cv_validation
from app.modules.documents.application import (
    _cv_core,
    _shared,
    cv_lifecycle_service,
    cv_service,
    download_service,
    export_service,
    snapshot_service,
    template_admin_service,
    template_seed,
    upload_service,
)
from app.modules.documents.application.errors import (
    CvEmptyError,
    CvNotInLibraryError,
    CvQuotaReachedError,
    CvVersionConflictError,
    InvalidCvFieldError,
)
from app.modules.documents.domain.models import (
    ApplicationCvSnapshot,
    CvProfile,
    CvSection,
    CvTemplate,
    CvTemplateVersion,
    SignedFileAccess,
)
from app.modules.documents.infrastructure import storage
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import (
    InMemoryStorage,
    cv_text_en,
    make_ready_cv,
    make_student,
    new_key,
)
from tests.org_utils import make_org_with_admin


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


@pytest.fixture(autouse=True)
def _reset_authorizer():
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _seed(db) -> None:
    await template_seed.ensure_default_templates(db)
    await db.commit()


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _first_template_id(db) -> uuid.UUID:
    templates = await cv_service.list_templates(db)
    return uuid.UUID(templates[0]["id"])


# --------------------------------------------------------------------------- #
# Templates                                                                   #
# --------------------------------------------------------------------------- #


async def test_template_seed_is_idempotent_and_listed(db_session) -> None:
    n1 = await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    n2 = await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    assert n1 == 8 and n2 == 0
    templates = await cv_service.list_templates(db_session)
    keys = {t["key"] for t in templates}
    assert {
        "classic_ats",
        "modern_navy",
        "modern_teal",
        "minimal_mono",
        "bold_header",
        "elegant_serif",
        "creative_twotone",
        "tech_chips",
    } == keys
    assert all("preview_url" in t for t in templates)
    assert all("layout_schema" in t for t in templates)
    # Every template now carries a full visual theme (the renderer's source of truth).
    for t in templates:
        theme = t["theme"]
        assert theme == t["layout_schema"]
        assert theme["layout"]["kind"] in {
            "single",
            "left-sidebar",
            "right-sidebar",
            "header-band",
            "two-column",
        }
        assert {
            "primary",
            "accent",
            "sidebarBg",
            "sidebarText",
            "text",
            "muted",
            "rule",
            "pageBg",
        } <= set(theme["palette"].keys())
        assert theme["order"][0] == "header"
        assert t["status"] == "published"
        assert t["version"] == 1
    # The 8 layouts are visually distinct (no two share the same layout kind +
    # sidebar background).
    signatures = {
        (t["theme"]["layout"]["kind"], t["theme"]["palette"]["sidebarBg"])
        for t in templates
    }
    assert len(signatures) == len(templates)


async def test_university_admin_can_manage_cv_templates(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    created = await template_admin_service.create_template(
        db_session,
        principal=admin,
        payload={
            "key": "policy_research",
            "name_vi": "Chính sách & nghiên cứu",
            "name_en": "Policy & Research",
            "category": "research",
            "layout_schema": {
                "section_order": ["summary", "education", "projects"],
                "target_roles": ["Policy Intern"],
                "strengths": ["research"],
            },
            "is_active": True,
        },
        ctx=CTX,
    )
    assert created["key"] == "policy_research"
    assert created["name_vi"] == "Chính sách & nghiên cứu"
    assert created["name_en"] == "Policy & Research"
    assert created["layout_schema"]["target_roles"] == ["Policy Intern"]
    # All templates are free — no premium concept in the response.
    assert "is_premium" not in created

    updated = await template_admin_service.update_template(
        db_session,
        principal=admin,
        template_id=uuid.UUID(created["id"]),
        payload={"is_active": False},
        ctx=CTX,
    )
    assert updated["is_active"] is False
    assert "is_premium" not in updated


async def test_partner_admin_cannot_manage_cv_templates(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await template_admin_service.list_templates_admin(
            db_session, principal=partner_admin
        )


async def test_seed_creates_template_version_rows(db_session) -> None:
    # Each seeded template ships with an immutable version-1 design snapshot.
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    templates = (
        await db_session.execute(select(CvTemplate))
    ).scalars().all()
    assert len(templates) == 8
    for t in templates:
        rows = (
            await db_session.execute(
                select(CvTemplateVersion).where(
                    CvTemplateVersion.template_id == t.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].version_number == 1
        assert rows[0].design_json == t.layout_schema


async def test_public_template_list_excludes_non_published(db_session) -> None:
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    # Archive one template directly; it must drop out of the public catalogue.
    tpl = (
        await db_session.execute(
            select(CvTemplate).where(CvTemplate.key == "modern_teal")
        )
    ).scalar_one()
    tpl.status = "archived"
    await db_session.commit()

    public = await cv_service.list_templates(db_session)
    keys = {t["key"] for t in public}
    assert "modern_teal" not in keys
    assert "classic_ats" in keys and len(public) == 7


async def test_admin_layout_change_publishes_new_version(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    from app.modules.documents.domain import themes as _themes

    created = await template_admin_service.create_template(
        db_session,
        principal=admin,
        payload={
            "key": "vinuni_signature",
            "name_vi": "Chữ ký VinUni",
            "name_en": "VinUni Signature",
            "category": "professional",
            "layout_schema": _themes.theme_for("classic_ats"),
            "is_active": True,
        },
        ctx=CTX,
    )
    tid = uuid.UUID(created["id"])
    assert created["version"] == 1
    v1_rows = (
        await db_session.execute(
            select(CvTemplateVersion).where(CvTemplateVersion.template_id == tid)
        )
    ).scalars().all()
    assert len(v1_rows) == 1

    # A design change bumps the version and snapshots a NEW immutable row; the
    # original version snapshot is left intact.
    updated = await template_admin_service.update_template(
        db_session,
        principal=admin,
        template_id=tid,
        payload={"layout_schema": _themes.theme_for("modern_navy")},
        ctx=CTX,
    )
    assert updated["version"] == 2
    rows = (
        await db_session.execute(
            select(CvTemplateVersion)
            .where(CvTemplateVersion.template_id == tid)
            .order_by(CvTemplateVersion.version_number)
        )
    ).scalars().all()
    assert [r.version_number for r in rows] == [1, 2]
    assert rows[0].design_json["layout"]["kind"] == "single"
    assert rows[1].design_json["layout"]["kind"] == "left-sidebar"


# --------------------------------------------------------------------------- #
# Upload happy + parse run                                                    #
# --------------------------------------------------------------------------- #


async def test_upload_happy_creates_review_run_with_fields(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    assert result["status"] == "review_required"
    assert result["next_action"] == "review_fields"
    # No raw storage path leaks in the upload response.
    assert "storage_path" not in result and "storage_key" not in result

    run = await upload_service.get_parse_run(
        db_session, principal=student, parse_run_id=uuid.UUID(result["parse_run_id"])
    )
    assert run["quality_code"] == "REVIEW_REQUIRED"
    assert run["user_message"]  # friendly, localized
    assert any(f["path"].startswith("education") for f in run["review_fields"])
    # Owner-only view must not leak parser internals.
    for leaked in ("provider_alias", "confidence", "error_message", "storage_path"):
        assert leaked not in run


async def test_upload_idempotent_returns_same_document(db_session) -> None:
    _u, student = await make_student(db_session)
    key = new_key()
    r1 = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=key, ctx=CTX,
    )
    r2 = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=key, ctx=CTX,
    )
    assert r1["document_id"] == r2["document_id"]


_EICAR_CV = cv_validation._EICAR + b" experience education skills"


@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [
        ("blank.txt", b"   \n  ", "BLANK_DOCUMENT"),
        (
            "notes.txt",
            (
                b"Bien ban hop khu pho cuoi nam. Hom nay chung toi thao luan ve ke "
                b"hoach to chuc tiec va trang tri cho buoi le sap toi trong tuan."
            ),
            "NOT_A_CV",
        ),
        ("virus.txt", _EICAR_CV, "FILE_REJECTED_SECURITY"),
        ("malware.exe", b"MZ\x90\x00 binary garbage", "UNSUPPORTED_FILE_TYPE"),
        ("broken.pdf", b"%PDF-1.4 not really a pdf", "CORRUPT_FILE"),
    ],
)
async def test_upload_negative_quality_codes(db_session, filename, data, expected) -> None:
    _u, student = await make_student(db_session)
    result = await upload_service.upload_cv(
        db_session, principal=student, filename=filename, data=data,
        content_type="application/octet-stream", idempotency_key=new_key(), ctx=CTX,
    )
    assert result["status"] == "failed"
    run = await upload_service.get_parse_run(
        db_session, principal=student, parse_run_id=uuid.UUID(result["parse_run_id"])
    )
    assert run["quality_code"] == expected
    assert run["user_message"]


async def test_upload_duplicate_file_detected(db_session) -> None:
    _u, student = await make_student(db_session)
    await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    dup = await upload_service.upload_cv(
        db_session, principal=student, filename="cv-again.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    run = await upload_service.get_parse_run(
        db_session, principal=student, parse_run_id=uuid.UUID(dup["parse_run_id"])
    )
    assert run["quality_code"] == "DUPLICATE_FILE"


async def test_security_rejected_file_not_stored(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await upload_service.upload_cv(
        db_session, principal=student, filename="virus.txt",
        data=cv_validation._EICAR + b" experience education skills",
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    from app.modules.documents.domain.models import Document

    doc = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(result["document_id"]))
        )
    ).scalar_one()
    assert doc.virus_scan_status == "infected"
    assert doc.storage_path == ""  # bytes were never written


async def test_parse_run_owner_only(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    result = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await upload_service.get_parse_run(
            db_session, principal=other, parse_run_id=uuid.UUID(result["parse_run_id"])
        )


# --------------------------------------------------------------------------- #
# Builder create per creation_mode                                           #
# --------------------------------------------------------------------------- #


async def test_create_blank_template_seeds_sections_and_version(db_session) -> None:
    await _seed(db_session)
    _u, student = await make_student(db_session)
    tpl = await _first_template_id(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "My CV", "template_id": str(tpl),
                 "creation_mode": "blank_template", "language": "vi"},
        ctx=CTX,
    )
    assert cv["status"] == "draft"
    assert cv["status_label"]
    assert len(cv["sections"]) >= 5
    assert cv["version"] == 1
    assert await _audit_count(db_session, "cv.created") == 1
    # A blank CV carries a header section first so it can render the owner's
    # name + contact once filled.
    from app.modules.documents.domain import catalog as _catalog

    assert _catalog.DEFAULT_SECTIONS[0]["section_type"] == "header"
    header = next(s for s in cv["sections"] if s["section_type"] == "header")
    assert header["sort_order"] == 5


async def test_delete_cv_soft_deletes_and_audits(db_session) -> None:
    await _seed(db_session)
    _u, student = await make_student(db_session)
    tpl = await _first_template_id(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Temp CV", "template_id": str(tpl),
                 "creation_mode": "blank_template", "language": "vi"},
        ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])

    await cv_service.delete_cv(db_session, principal=student, cv_id=cv_id, ctx=CTX)

    # Gone from the library (soft-deleted) and no longer fetchable; write audited.
    with pytest.raises(ResourceNotFoundError):
        await cv_service.get_cv(db_session, principal=student, cv_id=cv_id)
    assert await _audit_count(db_session, "cv.deleted") == 1


async def test_delete_cv_cross_owner_forbidden(db_session) -> None:
    await _seed(db_session)
    _u1, owner = await make_student(db_session, prefix="owner")
    _u2, other = await make_student(db_session, prefix="other")
    tpl = await _first_template_id(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=owner,
        payload={"title": "Owned", "template_id": str(tpl),
                 "creation_mode": "blank_template", "language": "vi"},
        ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await cv_service.delete_cv(
            db_session, principal=other, cv_id=uuid.UUID(cv["id"]), ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Removed creation modes (owner cleanup 2026-07-05)                            #
# --------------------------------------------------------------------------- #
#
# The ONLY supported CV creation paths are: from a template (``blank_template``),
# duplicate an existing CV (``duplicate_cv``), and upload-import (ingestion ->
# ``create_cv_from_sections``). The retired ``profile_import`` / ``notes_import`` /
# ``ai_assisted_draft`` modes — and the generic ``uploaded_import`` create branch —
# must be REJECTED by ``create_cv`` (AI is an in-builder assist, not a creation mode).


@pytest.mark.parametrize(
    "mode",
    ["profile_import", "notes_import", "ai_assisted_draft", "uploaded_import", "bogus_mode"],
)
async def test_create_cv_rejects_removed_creation_modes(db_session, mode) -> None:
    _u, student = await make_student(db_session)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_service.create_cv(
            db_session, principal=student,
            payload={"title": "X", "creation_mode": mode,
                     "source": {"raw_notes": "hi"}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "creation_mode"
    # Nothing was created for a rejected mode.
    assert await cv_service.count_cvs(db_session, principal=student) == 0


# --------------------------------------------------------------------------- #
# Section upsert + optimistic concurrency                                     #
# --------------------------------------------------------------------------- #


async def test_section_upsert_bumps_version_and_snapshots(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    section_id = uuid.UUID(cv["sections"][0]["id"])
    out = await cv_service.upsert_section(
        db_session, principal=student, cv_id=cv_id, section_id=section_id,
        payload={"content": {"items": [{"text": "Hello"}]}, "expected_version": cv["version"]},
        ctx=CTX,
    )
    assert out["cv_version"] == cv["version"] + 1
    assert await _audit_count(db_session, "cv.section.updated") == 1


async def test_section_upsert_version_conflict_returns_current(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    section_id = uuid.UUID(cv["sections"][0]["id"])
    with pytest.raises(CvVersionConflictError) as exc:
        await cv_service.upsert_section(
            db_session, principal=student, cv_id=cv_id, section_id=section_id,
            payload={"content": {"items": []}, "expected_version": 999}, ctx=CTX,
        )
    assert exc.value.details["current_version"] == cv["version"]


# --------------------------------------------------------------------------- #
# Version ids exposed (current_version_id + history) + add section + restore   #
# --------------------------------------------------------------------------- #


async def test_get_cv_exposes_current_version_id_that_resolves(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(created["id"])
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=cv_id)

    assert detail["current_version_id"] is not None
    assert len(detail["versions"]) == 1
    head = detail["versions"][0]
    assert head["id"] == detail["current_version_id"]
    assert head["is_current"] is True
    assert head["version"] == 1
    # The id must resolve to a real cv_versions row for this CV.
    from app.modules.documents.domain.models import CvVersion

    row = (
        await db_session.execute(
            select(CvVersion).where(
                CvVersion.id == uuid.UUID(detail["current_version_id"]),
                CvVersion.cv_id == cv_id,
            )
        )
    ).scalar_one()
    assert row.version_number == 1


async def test_list_versions_newest_first_and_owner_only(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(created["id"])
    # Add a section -> a second version.
    await cv_service.create_section(
        db_session, principal=student, cv_id=cv_id,
        payload={"section_type": "awards", "title": "Awards"}, ctx=CTX,
    )
    versions = await cv_service.list_versions(db_session, principal=student, cv_id=cv_id)
    assert [v["version"] for v in versions] == [2, 1]  # newest-first
    assert versions[0]["is_current"] is True
    assert versions[1]["is_current"] is False
    # Cross-owner cannot list another student's CV versions.
    with pytest.raises(ResourceNotFoundError):
        await cv_service.list_versions(db_session, principal=other, cv_id=cv_id)


async def test_create_section_adds_section_version_and_audit(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(created["id"])
    before = len(created["sections"])
    out = await cv_service.create_section(
        db_session, principal=student, cv_id=cv_id,
        payload={"section_type": "languages", "title": "Languages",
                 "content": {"items": [{"text": "English"}]},
                 "expected_version": created["version"]},
        ctx=CTX,
    )
    assert out["cv_version"] == created["version"] + 1
    assert out["section"]["section_type"] == "languages"
    # Appended after the previous last section.
    assert out["section"]["sort_order"] > 0
    assert await _audit_count(db_session, "cv.section.created") == 1

    detail = await cv_service.get_cv(db_session, principal=student, cv_id=cv_id)
    assert len(detail["sections"]) == before + 1
    assert len(detail["versions"]) == 2


async def test_create_section_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await cv_service.create_section(
            db_session, principal=other, cv_id=uuid.UUID(created["id"]),
            payload={"section_type": "awards"}, ctx=CTX,
        )


async def test_create_section_version_conflict(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    with pytest.raises(CvVersionConflictError) as exc:
        await cv_service.create_section(
            db_session, principal=student, cv_id=uuid.UUID(created["id"]),
            payload={"section_type": "awards", "expected_version": 999}, ctx=CTX,
        )
    assert exc.value.details["current_version"] == created["version"]


async def test_create_section_rejects_unknown_type(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    with pytest.raises(InvalidCvFieldError):
        await cv_service.create_section(
            db_session, principal=student, cv_id=uuid.UUID(created["id"]),
            payload={"section_type": "not_a_real_type"}, ctx=CTX,
        )


async def test_restore_version_rebuilds_sections_and_keeps_history(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(created["id"])
    base_sections = len(created["sections"])
    v1_id = uuid.UUID(created["current_version_id"])

    # Add a section -> v2 has an extra section.
    out = await cv_service.create_section(
        db_session, principal=student, cv_id=cv_id,
        payload={"section_type": "awards", "title": "Awards"}, ctx=CTX,
    )
    detail_v2 = await cv_service.get_cv(db_session, principal=student, cv_id=cv_id)
    assert len(detail_v2["sections"]) == base_sections + 1

    # Restore v1 -> sections back to base, new version (v3) recorded, history kept.
    restored = await cv_service.restore_version(
        db_session, principal=student, cv_id=cv_id, version_id=v1_id,
        payload={"expected_version": out["cv_version"]}, ctx=CTX,
    )
    assert len(restored["sections"]) == base_sections
    assert len(restored["versions"]) == 3  # v1, v2, v3(restore)
    assert restored["versions"][0]["change_source"] == "restore"
    assert restored["current_version_id"] == restored["versions"][0]["id"]
    assert await _audit_count(db_session, "cv.version.restored") == 1


async def test_restore_unknown_version_404(db_session) -> None:
    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await cv_service.restore_version(
            db_session, principal=student, cv_id=uuid.UUID(created["id"]),
            version_id=uuid.uuid4(), payload=None, ctx=CTX,
        )


async def test_export_using_version_id_from_get_detail(db_session) -> None:
    """End-to-end: read current_version_id from GET detail, export with it."""

    _u, student = await make_student(db_session)
    created = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Export from GET", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(created["id"])
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=cv_id)
    version_id = uuid.UUID(detail["current_version_id"])

    export = await export_service.create_export(
        db_session, principal=student, cv_id=cv_id, version_id=version_id,
        export_format="pdf", idempotency_key=new_key(), ctx=CTX,
    )
    got = await export_service.get_export(
        db_session, principal=student, export_id=uuid.UUID(export["export_id"])
    )
    assert got["status"] == "ready"
    token = got["download_url"].rsplit("/", 1)[-1]
    result = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert result.content[:4] == b"%PDF"


# --------------------------------------------------------------------------- #
# Duplicate never mutates source                                             #
# --------------------------------------------------------------------------- #


async def test_duplicate_does_not_mutate_source(db_session) -> None:
    _u, student = await make_student(db_session)
    src = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Original", "creation_mode": "blank_template"}, ctx=CTX,
    )
    src_id = uuid.UUID(src["id"])
    dup = await cv_service.duplicate_cv(
        db_session, principal=student, cv_id=src_id,
        payload={"title": "Copy", "idempotency_key": new_key()}, ctx=CTX,
    )
    assert dup["id"] != src["id"]
    assert dup["source_type"] == "duplicate_existing"
    # Source untouched.
    src_after = await cv_service.get_cv(db_session, principal=student, cv_id=src_id)
    assert src_after["title"] == "Original"
    assert src_after["version"] == src["version"]
    # Sections were copied, not moved.
    src_sections = (
        await db_session.execute(
            select(func.count()).select_from(CvSection).where(CvSection.cv_id == src_id)
        )
    ).scalar_one()
    assert src_sections >= 5


async def test_duplicate_is_idempotent(db_session) -> None:
    _u, student = await make_student(db_session)
    src = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Original", "creation_mode": "blank_template"}, ctx=CTX,
    )
    key = new_key()
    d1 = await cv_service.duplicate_cv(
        db_session, principal=student, cv_id=uuid.UUID(src["id"]),
        payload={"idempotency_key": key}, ctx=CTX,
    )
    d2 = await cv_service.duplicate_cv(
        db_session, principal=student, cv_id=uuid.UUID(src["id"]),
        payload={"idempotency_key": key}, ctx=CTX,
    )
    assert d1["id"] == d2["id"]


# --------------------------------------------------------------------------- #
# Active-CV library quota (QUOTA_EXCEEDED, 409)                                #
# --------------------------------------------------------------------------- #


async def _make_blank(db, student, title: str = "CV") -> dict:
    return await cv_service.create_cv(
        db, principal=student,
        payload={"title": title, "creation_mode": "blank_template"}, ctx=CTX,
    )


async def _seed_header_name(db, student, cv: dict, name: str = "Test Candidate") -> None:
    """Give a draft CV a header name so it passes the non-empty finalize gate."""

    header = next(s for s in cv["sections"] if s["section_type"] == "header")
    await cv_service.upsert_section(
        db, principal=student, cv_id=uuid.UUID(cv["id"]),
        section_id=uuid.UUID(header["id"]),
        payload={"content": {"name": name}, "expected_version": cv["version"]},
        ctx=CTX,
    )


async def test_quota_counts_only_ready_drafts_are_free(db_session) -> None:
    # Design spec 2026-07-05: unlimited scratch drafts, library capped at 5 ready CVs.
    _u, student = await make_student(db_session)
    limit = cv_service._active_cv_limit()
    assert limit == 5  # docs/BUSINESS_LOGIC.md §4B.4 default; tier-overridable.

    # Create N > limit drafts freely — none count toward the library.
    for i in range(limit + 2):
        cv = await _make_blank(db_session, student, title=f"Draft {i}")
        assert cv["status"] == "draft"
    assert await cv_service.count_cvs(db_session, principal=student) == 0

    # Finalize up to the limit (each needs real content; seed a header name).
    for i in range(limit):
        await make_ready_cv(db_session, student=student, title=f"Ready {i}")
    assert await cv_service.count_cvs(db_session, principal=student) == limit

    # The (limit+1)-th finalize is blocked with 409 QUOTA_EXCEEDED.
    with pytest.raises(CvQuotaReachedError) as exc:
        await make_ready_cv(db_session, student=student, title="over the limit")
    err = exc.value
    assert err.code == "QUOTA_EXCEEDED"
    assert err.http_status == 409
    assert err.details["reason"] == "cv_quota_reached"
    assert err.details["current"] == limit
    assert err.details["limit"] == limit
    assert "archive_existing" in err.details["actions"]


async def test_create_and_duplicate_never_quota_gated(db_session, monkeypatch) -> None:
    # Even at a full library (limit 1), creating and duplicating drafts is allowed.
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 1)
    _u, student = await make_student(db_session)
    await make_ready_cv(db_session, student=student, title="Library full")
    assert await cv_service.count_cvs(db_session, principal=student) == 1

    # Create a draft while full -> allowed (unlimited drafts).
    draft = await _make_blank(db_session, student, "Extra draft")
    assert draft["status"] == "draft"
    # Duplicate the library CV -> a new draft, also allowed.
    dup = await cv_service.duplicate_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]),
        payload={"idempotency_key": new_key()}, ctx=CTX,
    )
    assert dup["status"] == "draft"
    # Library count unchanged (only the one ready CV).
    assert await cv_service.count_cvs(db_session, principal=student) == 1


async def test_finalize_at_library_full_is_blocked(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    await make_ready_cv(db_session, student=student, title="A")
    await make_ready_cv(db_session, student=student, title="B")  # library 2/2

    # A third draft with real content cannot be finalized while the library is full.
    draft = await _make_blank(db_session, student, "C")
    await _seed_header_name(db_session, student, draft)
    with pytest.raises(CvQuotaReachedError) as exc:
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )
    assert exc.value.details["current"] == 2
    assert exc.value.details["limit"] == 2
    # Nothing mutated: the draft is still a draft.
    still = await cv_service.get_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"])
    )
    assert still["status"] == "draft"


async def test_archiving_a_ready_cv_frees_a_library_slot(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    a = await make_ready_cv(db_session, student=student, title="A")
    await make_ready_cv(db_session, student=student, title="B")  # library 2/2

    draft = await _make_blank(db_session, student, "C")
    await _seed_header_name(db_session, student, draft)
    with pytest.raises(CvQuotaReachedError):
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )

    # Archiving a ready CV frees a slot immediately.
    await cv_service.update_cv(
        db_session, principal=student, cv_id=uuid.UUID(a["id"]),
        payload={"status": "archived"}, ctx=CTX,
    )
    assert await cv_service.count_cvs(db_session, principal=student) == 1

    finalized = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
    )
    assert finalized["status"] == "ready"
    assert await cv_service.count_cvs(db_session, principal=student) == 2


async def test_soft_deleted_ready_cvs_do_not_count_toward_quota(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    a = await make_ready_cv(db_session, student=student, title="A")
    await make_ready_cv(db_session, student=student, title="B")  # library 2/2

    # Soft-delete A.
    row = (
        await db_session.execute(
            select(CvProfile).where(CvProfile.id == uuid.UUID(a["id"]))
        )
    ).scalar_one()
    row.deleted_at = _shared.now()
    await db_session.commit()

    assert await cv_service.count_cvs(db_session, principal=student) == 1
    draft = await _make_blank(db_session, student, "C")
    await _seed_header_name(db_session, student, draft)
    finalized = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
    )
    assert finalized["status"] == "ready"


async def test_cv_library_quota_meta_shape(db_session) -> None:
    _u, student = await make_student(db_session)
    # A draft does NOT show in the library counter; a finalized CV does.
    await _make_blank(db_session, student, "Draft")
    await make_ready_cv(db_session, student=student, title="Library CV")
    quota = await cv_service.cv_library_quota(db_session, principal=student)
    assert quota["active_cv_limit"] == 5
    assert quota["active_cv_used"] == 1  # only the ready CV counts
    assert quota["can_create"] is True
    assert quota["quota_reset_at"] is None
    assert quota["quota_source"] == "student_tier"


async def test_cross_owner_cv_access_is_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await cv_service.get_cv(db_session, principal=other, cv_id=uuid.UUID(cv["id"]))


# --------------------------------------------------------------------------- #
# Export + signed download                                                   #
# --------------------------------------------------------------------------- #


async def _export_ready(db, student) -> tuple[uuid.UUID, uuid.UUID]:
    cv = await cv_service.create_cv(
        db, principal=student, payload={"title": "Export CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    # The first version snapshot id:
    from app.modules.documents.domain.models import CvVersion

    version = (
        await db.execute(select(CvVersion).where(CvVersion.cv_id == cv_id))
    ).scalars().first()
    export = await export_service.create_export(
        db, principal=student, cv_id=cv_id, version_id=version.id,
        export_format="pdf", idempotency_key=new_key(), ctx=CTX,
    )
    return cv_id, uuid.UUID(export["export_id"])


async def test_export_produces_pdf_and_signed_download(db_session) -> None:
    _u, student = await make_student(db_session)
    _cv_id, export_id = await _export_ready(db_session, student)

    detail = await export_service.get_export(db_session, principal=student, export_id=export_id)
    assert detail["status"] == "ready"
    assert detail["download_url"] and "/cv-files/" in detail["download_url"]
    token = detail["download_url"].rsplit("/", 1)[-1]

    result = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert result.media_type == "application/pdf"
    assert result.content[:4] == b"%PDF"
    # Download was audited (no watermark for the owner).
    access = (
        await db_session.execute(
            select(SignedFileAccess).where(SignedFileAccess.resource_id == export_id)
        )
    ).scalars().all()
    assert len(access) == 1 and access[0].has_watermark is False
    assert await _audit_count(db_session, "cv.export.completed") == 1


async def test_export_idempotent(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student, payload={"title": "CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    from app.modules.documents.domain.models import CvVersion

    version = (
        await db_session.execute(select(CvVersion).where(CvVersion.cv_id == uuid.UUID(cv["id"])))
    ).scalars().first()
    key = new_key()
    e1 = await export_service.create_export(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]), version_id=version.id,
        export_format="pdf", idempotency_key=key, ctx=CTX,
    )
    e2 = await export_service.create_export(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]), version_id=version.id,
        export_format="pdf", idempotency_key=key, ctx=CTX,
    )
    assert e1["export_id"] == e2["export_id"]


async def test_bad_and_expired_tokens_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    _cv_id, export_id = await _export_ready(db_session, student)

    # Tampered token.
    with pytest.raises(download_service.InvalidDownloadTokenError):
        await download_service.resolve_download(db_session, token="not.a.valid.token", ctx=CTX)

    # Expired token (negative TTL).
    expired = storage.make_signed_token(
        {"kind": "export", "id": str(export_id), "uid": str(student.user_id),
         "purpose": "download", "wm": False},
        ttl_seconds=-10,
    )
    with pytest.raises(download_service.InvalidDownloadTokenError):
        await download_service.resolve_download(db_session, token=expired, ctx=CTX)

    # Signature tamper: mutate a payload char so the HMAC no longer matches.
    valid = storage.make_signed_token(
        {"kind": "export", "id": str(export_id), "uid": str(student.user_id),
         "purpose": "download", "wm": False}
    )
    pos = 8  # inside the payload segment
    tampered = valid[:pos] + ("X" if valid[pos] != "X" else "Y") + valid[pos + 1:]
    with pytest.raises(download_service.InvalidDownloadTokenError):
        await download_service.resolve_download(db_session, token=tampered, ctx=CTX)


async def test_export_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    _cv_id, export_id = await _export_ready(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await export_service.get_export(db_session, principal=other, export_id=export_id)


# --------------------------------------------------------------------------- #
# Application snapshots: immutable + cross-owner + partner watermark seam     #
# --------------------------------------------------------------------------- #


async def _make_snapshot(db, student) -> ApplicationCvSnapshot:
    # A builder CV must be committed to the library (``ready``) before it can be
    # snapshotted for an application (design spec 2026-07-05).
    cv = await make_ready_cv(db, student=student, title="Snap CV")
    return await snapshot_service.create_application_cv_snapshot(
        db, owner_id=student.user_id,
        cv_selection={"type": "builder_cv", "cv_profile_id": cv["id"],
                      "cv_version_id": cv["current_version_id"]},
        idempotency_key=new_key(), ctx=CTX,
    )


async def test_snapshot_created_and_immutable(db_session) -> None:
    _u, student = await make_student(db_session)
    snap = await _make_snapshot(db_session, student)
    assert snap.snapshot_json.get("title") == "Snap CV"
    assert await _audit_count(db_session, "cv.snapshot.created") == 1
    # No update/delete API exists; the service exposes only create + read.
    assert not hasattr(snapshot_service, "update_application_cv_snapshot")
    assert not hasattr(snapshot_service, "delete_application_cv_snapshot")


async def test_snapshot_from_uploaded_document(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    snap = await snapshot_service.create_application_cv_snapshot(
        db_session, owner_id=student.user_id,
        cv_selection={"type": "uploaded_document", "uploaded_document_id": up["document_id"]},
        idempotency_key=new_key(), ctx=CTX,
    )
    assert snap.snapshot_json.get("source_type") == "uploaded"


async def test_snapshot_owner_download_unwatermarked(db_session) -> None:
    _u, student = await make_student(db_session)
    snap = await _make_snapshot(db_session, student)
    out = await snapshot_service.get_snapshot_download(
        db_session, principal=student, snapshot_id=snap.id
    )
    assert out["has_watermark"] is False


async def test_snapshot_cross_owner_404_without_authorizer(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, partner = await make_student(db_session, prefix="partner")
    snap = await _make_snapshot(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await snapshot_service.get_snapshot_download(
            db_session, principal=partner, snapshot_id=snap.id
        )


async def test_snapshot_partner_download_is_watermarked(db_session) -> None:
    _u, student = await make_student(db_session)
    snap = await _make_snapshot(db_session, student)
    partner = Principal(user_id=uuid.uuid4(), persona="partner_member", org_id=uuid.uuid4())

    def _authorizer(principal: Principal, s: ApplicationCvSnapshot):
        return snapshot_service.SnapshotAccess(watermark_text="VinUni Career - Partner Co")

    snapshot_service.set_snapshot_access_authorizer(_authorizer)
    out = await snapshot_service.get_snapshot_download(
        db_session, principal=partner, snapshot_id=snap.id
    )
    assert out["has_watermark"] is True
    token = out["download_url"].rsplit("/", 1)[-1]
    result = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert result.content[:4] == b"%PDF"
    access = (
        await db_session.execute(
            select(SignedFileAccess).where(SignedFileAccess.resource_id == snap.id)
        )
    ).scalars().one()
    assert access.has_watermark is True
    assert access.watermark_text == "VinUni Career - Partner Co"


# --------------------------------------------------------------------------- #
# Finalize: commit a draft into the library (draft -> ready)                   #
# --------------------------------------------------------------------------- #


async def test_finalize_promotes_draft_to_ready_with_version_and_audit(db_session) -> None:
    _u, student = await make_student(db_session)
    draft = await _make_blank(db_session, student, "To finalize")
    await _seed_header_name(db_session, student, draft)
    versions_before = len(
        await cv_service.list_versions(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"])
        )
    )

    detail = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
    )

    assert detail["status"] == "ready"
    assert detail["in_library"] is True
    assert detail["finalized_at"] is not None
    assert detail["status_label"] == "Sẵn sàng ứng tuyển"
    # A new immutable version was snapshotted with change_source=finalize.
    assert len(detail["versions"]) == versions_before + 1
    assert detail["versions"][0]["change_source"] == "finalize"
    assert detail["versions"][0]["is_current"] is True
    assert detail["current_version_id"] == detail["versions"][0]["id"]
    # It now counts toward the library and is audited.
    assert await cv_service.count_cvs(db_session, principal=student) == 1
    assert await _audit_count(db_session, "cv.finalized") == 1


async def test_finalize_empty_cv_is_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    # A blank template CV has no header name and no section content.
    draft = await _make_blank(db_session, student, "Empty")
    with pytest.raises(CvEmptyError) as exc:
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )
    assert exc.value.details["reason"] == "cv_empty"
    assert exc.value.http_status == 422
    # Nothing committed; still a draft, still not counted.
    still = await cv_service.get_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"])
    )
    assert still["status"] == "draft"
    assert await cv_service.count_cvs(db_session, principal=student) == 0


async def test_finalize_accepts_content_only_cv_without_header_name(db_session) -> None:
    # A CV with no header name but a real visible section (skills) is finalizable.
    _u, student = await make_student(db_session)
    draft = await _make_blank(db_session, student, "Skills only")
    skills = next(s for s in draft["sections"] if s["section_type"] == "skills")
    await cv_service.upsert_section(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]),
        section_id=uuid.UUID(skills["id"]),
        payload={"content": {"items": [{"text": "Python"}]},
                 "expected_version": draft["version"]},
        ctx=CTX,
    )
    detail = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
    )
    assert detail["status"] == "ready"


async def test_finalize_is_idempotent_when_already_ready(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await make_ready_cv(db_session, student=student, title="Already ready")
    cv_id = uuid.UUID(detail["id"])
    versions_after_first = len(detail["versions"])

    # Re-finalize -> same ready detail, no new version, no double audit, no re-count.
    again = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=cv_id, ctx=CTX,
    )
    assert again["status"] == "ready"
    assert len(again["versions"]) == versions_after_first
    assert await _audit_count(db_session, "cv.finalized") == 1
    assert await cv_service.count_cvs(db_session, principal=student) == 1


async def test_finalize_cross_owner_is_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    draft = await _make_blank(db_session, student, "Owned")
    await _seed_header_name(db_session, student, draft)
    with pytest.raises(ResourceNotFoundError):
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=other, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Finalize analysis: matching_json derive (design spec §"Data contracts" 3)     #
# --------------------------------------------------------------------------- #


async def _matching_json(db, cv_id: uuid.UUID) -> dict | None:
    row = (
        await db.execute(select(CvProfile).where(CvProfile.id == cv_id))
    ).scalar_one()
    return row.matching_json


async def test_finalize_writes_matching_representation(db_session) -> None:
    _u, student = await make_student(db_session)
    draft = await _make_blank(db_session, student, "Rich CV")
    header_id = next(
        s for s in draft["sections"] if s["section_type"] == "header"
    )["id"]
    skills_id = next(
        s for s in draft["sections"] if s["section_type"] == "skills"
    )["id"]
    exp_id = next(
        s for s in draft["sections"] if s["section_type"] == "experience"
    )["id"]

    # Header with contact + links; skills with named items; experience entries.
    await cv_service.upsert_section(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]),
        section_id=uuid.UUID(header_id),
        payload={
            "content": {
                "name": "Nguyen Van A",
                "email": "a@example.com",
                "phone": "+84900000000",
                "links": [{"label": "GitHub", "url": "https://github.com/a",
                           "type": "github"}],
            },
            "expected_version": draft["version"],
        },
        ctx=CTX,
    )
    v = draft["version"] + 1
    await cv_service.upsert_section(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]),
        section_id=uuid.UUID(skills_id),
        payload={
            "content": {"items": [{"name": "Python", "level": 90},
                                  {"name": "FastAPI"}, {"name": "python"}]},
            "expected_version": v,
        },
        ctx=CTX,
    )
    v += 1
    await cv_service.upsert_section(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]),
        section_id=uuid.UUID(exp_id),
        payload={
            "content": {
                "entries": [
                    {"heading": "Software Intern", "subheading": "Example Tech",
                     "highlights": ["Built REST APIs with FastAPI and PostgreSQL"]},
                ]
            },
            "expected_version": v,
        },
        ctx=CTX,
    )

    detail = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
    )
    assert detail["status"] == "ready"
    # The matching representation is INTERNAL — it must NOT leak into the response.
    import json

    assert "matching_json" not in json.dumps(detail)

    matching = await _matching_json(db_session, uuid.UUID(draft["id"]))
    assert matching is not None
    # Skills normalized + deduped (case-insensitive): python appears once.
    assert matching["skills"] == ["python", "fastapi"]
    assert matching["skill_count"] == 2
    # Contact presence flags derived from the header.
    assert matching["contact"]["email"] is True
    assert matching["contact"]["phone"] is True
    assert matching["contact"]["links"] is True
    assert matching["contact"]["location"] is False
    # One experience entry counted.
    assert matching["experience_entry_count"] == 1
    # Keywords come from experience/projects/summary text (stopwords dropped).
    assert "fastapi" in matching["keywords"]
    assert "postgresql" in matching["keywords"]
    assert "and" not in matching["keywords"]
    assert matching["schema_version"] == cv_lifecycle_service.MATCHING_SCHEMA_VERSION


async def test_finalize_matching_is_idempotent_and_quota_gated(db_session) -> None:
    # matching_json is written on the first finalize; re-finalize (idempotent) does
    # not re-run analysis or create a new version.
    _u, student = await make_student(db_session)
    detail = await make_ready_cv(db_session, student=student, title="Ready")
    cv_id = uuid.UUID(detail["id"])
    first = await _matching_json(db_session, cv_id)
    assert first is not None
    versions_after_first = len(detail["versions"])

    again = await cv_lifecycle_service.finalize_cv(
        db_session, principal=student, cv_id=cv_id, ctx=CTX,
    )
    assert again["status"] == "ready"
    assert len(again["versions"]) == versions_after_first  # no new version
    assert await _matching_json(db_session, cv_id) == first  # unchanged


async def test_finalize_empty_cv_does_not_write_matching(db_session) -> None:
    _u, student = await make_student(db_session)
    draft = await _make_blank(db_session, student, "Empty")
    with pytest.raises(CvEmptyError):
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )
    # A rejected finalize never analyzed the CV.
    assert await _matching_json(db_session, uuid.UUID(draft["id"])) is None


async def test_finalize_at_library_full_does_not_write_matching(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 1)
    _u, student = await make_student(db_session)
    await make_ready_cv(db_session, student=student, title="Full")  # library 1/1
    draft = await _make_blank(db_session, student, "Third")
    await _seed_header_name(db_session, student, draft)
    with pytest.raises(CvQuotaReachedError):
        await cv_lifecycle_service.finalize_cv(
            db_session, principal=student, cv_id=uuid.UUID(draft["id"]), ctx=CTX,
        )
    # Quota gate runs before analysis: nothing was written.
    assert await _matching_json(db_session, uuid.UUID(draft["id"])) is None


# --------------------------------------------------------------------------- #
# Upload import lands ``ready`` in the library (+ quota-checked at start)      #
# --------------------------------------------------------------------------- #


async def test_upload_import_creates_ready_library_cv(db_session) -> None:
    from app.modules.documents.application import ingestion_service

    _u, student = await make_student(db_session)
    up = await ingestion_service.create_upload(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    ing = await ingestion_service.start_ingestion(
        db_session, principal=student,
        document_id=uuid.UUID(up["document_id"]), ctx=CTX,
    )
    detail = await ingestion_service.import_ingestion(
        db_session, principal=student, ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Uploaded CV", "fact_confirmation": True}, ctx=CTX,
    )
    # An uploaded CV is analyzed on arrival -> lands directly in the library.
    assert detail["status"] == "ready"
    assert detail["in_library"] is True
    assert detail["finalized_at"] is not None
    assert await cv_service.count_cvs(db_session, principal=student) == 1


async def test_upload_start_blocked_when_library_full(db_session, monkeypatch) -> None:
    # An uploaded CV lands in the library, so when the library is full the ingestion
    # is blocked at START (before spending extraction tokens).
    from app.modules.documents.application import ingestion_service

    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 1)
    _u, student = await make_student(db_session)
    await make_ready_cv(db_session, student=student, title="Library full")

    up = await ingestion_service.create_upload(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    with pytest.raises(CvQuotaReachedError):
        await ingestion_service.start_ingestion(
            db_session, principal=student,
            document_id=uuid.UUID(up["document_id"]), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Apply / job-fit eligibility: only ``ready`` CVs; a draft is rejected         #
# --------------------------------------------------------------------------- #


async def test_apply_snapshot_rejects_draft_cv(db_session) -> None:
    _u, student = await make_student(db_session)
    draft = await _make_blank(db_session, student, "Draft CV")
    from app.modules.documents.domain.models import CvVersion

    version = (
        await db_session.execute(
            select(CvVersion).where(CvVersion.cv_id == uuid.UUID(draft["id"]))
        )
    ).scalars().first()
    with pytest.raises(CvNotInLibraryError) as exc:
        await snapshot_service.create_application_cv_snapshot(
            db_session, owner_id=student.user_id,
            cv_selection={"type": "builder_cv", "cv_profile_id": draft["id"],
                          "cv_version_id": str(version.id)},
            idempotency_key=new_key(), ctx=CTX,
        )
    assert exc.value.details["reason"] == "cv_not_in_library"
    assert exc.value.http_status == 409


async def test_apply_snapshot_accepts_ready_cv(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await make_ready_cv(db_session, student=student, title="Library CV")
    snap = await snapshot_service.create_application_cv_snapshot(
        db_session, owner_id=student.user_id,
        cv_selection={"type": "builder_cv", "cv_profile_id": detail["id"],
                      "cv_version_id": detail["current_version_id"]},
        idempotency_key=new_key(), ctx=CTX,
    )
    assert snap.cv_id == uuid.UUID(detail["id"])
