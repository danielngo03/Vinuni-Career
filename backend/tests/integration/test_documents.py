"""Documents / CV Studio (non-AI) service tests.

Covers: template seed + list, upload happy + every negative quality_code, parse-run
owner-only (cross-owner 404), CV create per non-AI creation_mode + ai_assisted_draft
rejection, section upsert optimistic-version conflict (409), duplicate never mutates
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
    cv_service,
    download_service,
    export_service,
    snapshot_service,
    template_admin_service,
    template_seed,
    upload_service,
)
from app.modules.documents.application.errors import (
    CvQuotaReachedError,
    CvSourceRequiredError,
    CvVersionConflictError,
)
from app.modules.documents.domain.models import (
    ApplicationCvSnapshot,
    CvProfile,
    CvSection,
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
    assert n1 >= 1 and n2 == 0
    templates = await cv_service.list_templates(db_session)
    keys = {t["key"] for t in templates}
    assert {
        "classic_one_page",
        "data_analytics_research",
        "finance_consulting",
        "marketing_growth",
        "healthcare_impact",
    }.issubset(keys)
    assert all("preview_url" in t for t in templates)
    assert all("layout_schema" in t for t in templates)
    data_template = next(t for t in templates if t["key"] == "data_analytics_research")
    assert "target_roles" in data_template["layout_schema"]


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
            "is_premium": False,
            "is_active": True,
        },
        ctx=CTX,
    )
    assert created["key"] == "policy_research"
    assert created["name_vi"] == "Chính sách & nghiên cứu"
    assert created["name_en"] == "Policy & Research"
    assert created["layout_schema"]["target_roles"] == ["Policy Intern"]

    updated = await template_admin_service.update_template(
        db_session,
        principal=admin,
        template_id=uuid.UUID(created["id"]),
        payload={"is_premium": True, "is_active": False},
        ctx=CTX,
    )
    assert updated["is_premium"] is True
    assert updated["is_active"] is False


async def test_partner_admin_cannot_manage_cv_templates(db_session) -> None:
    _u, _org, partner_admin = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await template_admin_service.list_templates_admin(
            db_session, principal=partner_admin
        )


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


async def test_create_profile_import(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "From profile", "creation_mode": "profile_import",
                 "language": "en", "source": {"import_profile": True, "raw_notes": "hi"}},
        ctx=CTX,
    )
    assert cv["source_type"] == "profile_import"


async def test_create_uploaded_import(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=new_key(), ctx=CTX,
    )
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "From upload", "creation_mode": "uploaded_import",
                 "language": "en",
                 "source": {"uploaded_document_id": up["document_id"],
                            "cv_parse_run_id": up["parse_run_id"]}},
        ctx=CTX,
    )
    assert cv["source_type"] == "uploaded_import"
    # Extracted education flowed into the section content.
    edu = next(s for s in cv["sections"] if s["section_type"] == "education")
    assert edu["content"].get("items")


async def test_ai_assisted_draft_creates_blank_cv_with_pending_suggestion(
    db_session,
) -> None:
    # ai_assisted_draft now creates a blank draft + a pending AI suggestion
    # (it does NOT auto-populate the CV). Full AI behaviour is covered in
    # tests/integration/test_cv_ai_suggestions.py.
    _u, student = await make_student(db_session)
    detail = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "AI", "creation_mode": "ai_assisted_draft"},
        ctx=CTX,
    )
    assert detail["source_type"] == "ai_draft"
    assert detail["pending_suggestion"]["status"] == "pending"


# --------------------------------------------------------------------------- #
# Create from raw notes (CV-first, deterministic, NO AI)                       #
# --------------------------------------------------------------------------- #

# A freshly-registered student has zero structured profile rows; the notes path
# must still produce a usable, fact-grounded CV from the pasted text alone.
_RAW_NOTES = (
    "Sinh viên CNTT VinUni, tìm thực tập backend.\n"
    "Experience: Trợ giảng môn CS101; Thực tập tại Example Tech.\n"
    "Skills: Python, FastAPI, PostgreSQL\n"
)


def _items(cv: dict, section_type: str) -> list[dict]:
    section = next(s for s in cv["sections"] if s["section_type"] == section_type)
    return section["content"].get("items") or []


async def test_create_notes_import_seeds_sections_without_profile(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "From notes", "creation_mode": "notes_import",
                 "language": "vi", "source": {"raw_notes": _RAW_NOTES}},
        ctx=CTX,
    )
    # Usable CV: draft, versioned, audited — no AI suggestion involved.
    assert cv["source_type"] == "notes_import"
    assert cv["status"] == "draft"
    assert cv["version"] == 1
    assert "pending_suggestion" not in cv
    assert await _audit_count(db_session, "cv.created") == 1

    # Deterministic routing: pre-header line -> summary; Experience/Skills headers
    # route the rest. Every seeded item is a verbatim slice of the user's notes.
    summary = [i["text"] for i in _items(cv, "summary")]
    experience = [i["text"] for i in _items(cv, "experience")]
    skills = [i["text"] for i in _items(cv, "skills")]
    assert summary == ["Sinh viên CNTT VinUni, tìm thực tập backend."]
    assert experience == ["Trợ giảng môn CS101", "Thực tập tại Example Tech."]
    assert skills == ["Python", "FastAPI", "PostgreSQL"]
    # Nothing fabricated into sections with no matching notes.
    assert _items(cv, "education") == []


async def test_create_notes_import_is_deterministic(db_session) -> None:
    # Same input -> byte-identical seeded sections on every call (no AI/randomness).
    _u, student = await make_student(db_session)
    a = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Notes A", "creation_mode": "notes_import",
                 "source": {"raw_notes": _RAW_NOTES}},
        ctx=CTX,
    )
    b = await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "Notes B", "creation_mode": "notes_import",
                 "source": {"raw_notes": _RAW_NOTES}},
        ctx=CTX,
    )

    def _shape(cv: dict) -> list[tuple]:
        return [
            (s["section_type"], tuple(i["text"] for i in (s["content"].get("items") or [])))
            for s in cv["sections"]
        ]

    assert _shape(a) == _shape(b)


async def test_create_notes_import_requires_notes(db_session) -> None:
    _u, student = await make_student(db_session)
    with pytest.raises(CvSourceRequiredError) as exc:
        await cv_service.create_cv(
            db_session, principal=student,
            payload={"title": "Empty notes", "creation_mode": "notes_import",
                     "source": {"raw_notes": "   \n  "}},
            ctx=CTX,
        )
    assert exc.value.details["reason"] == "source_required"
    assert exc.value.details["field"] == "raw_notes"
    assert exc.value.http_status == 422


async def test_create_notes_import_respects_active_cv_quota(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 1)
    _u, student = await make_student(db_session)
    await cv_service.create_cv(
        db_session, principal=student,
        payload={"title": "First", "creation_mode": "notes_import",
                 "source": {"raw_notes": _RAW_NOTES}},
        ctx=CTX,
    )
    with pytest.raises(CvQuotaReachedError):
        await cv_service.create_cv(
            db_session, principal=student,
            payload={"title": "Over limit", "creation_mode": "notes_import",
                     "source": {"raw_notes": _RAW_NOTES}},
            ctx=CTX,
        )


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
    from app.modules.documents.application.errors import InvalidCvFieldError

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


async def test_create_at_active_cv_limit_returns_quota_exceeded(db_session) -> None:
    # Faithful to the documented VinUni default of 5 active CVs.
    _u, student = await make_student(db_session)
    limit = cv_service._active_cv_limit()
    assert limit == 5  # docs/BUSINESS_LOGIC.md §4B.4 default; tier-overridable.
    for i in range(limit):
        await _make_blank(db_session, student, title=f"CV {i}")

    with pytest.raises(CvQuotaReachedError) as exc:
        await _make_blank(db_session, student, title="over the limit")

    err = exc.value
    assert err.code == "QUOTA_EXCEEDED"
    assert err.http_status == 409
    assert err.details["reason"] == "cv_quota_reached"
    assert err.details["current"] == limit
    assert err.details["limit"] == limit
    assert "archive_existing" in err.details["actions"]


async def test_duplicate_at_active_cv_limit_is_blocked(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    a = await _make_blank(db_session, student, "A")
    await _make_blank(db_session, student, "B")  # now at 2/2 active

    with pytest.raises(CvQuotaReachedError) as exc:
        await cv_service.duplicate_cv(
            db_session, principal=student, cv_id=uuid.UUID(a["id"]),
            payload={"idempotency_key": new_key()}, ctx=CTX,
        )
    assert exc.value.details["current"] == 2
    assert exc.value.details["limit"] == 2


async def test_archiving_a_cv_frees_a_quota_slot(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    a = await _make_blank(db_session, student, "A")
    await _make_blank(db_session, student, "B")  # at 2/2

    with pytest.raises(CvQuotaReachedError):
        await _make_blank(db_session, student, "C blocked")

    # Archiving frees a slot (archived CVs do not count toward the active limit).
    await cv_service.update_cv(
        db_session, principal=student, cv_id=uuid.UUID(a["id"]),
        payload={"status": "archived"}, ctx=CTX,
    )
    assert await cv_service.count_cvs(db_session, principal=student) == 1

    c = await _make_blank(db_session, student, "C now allowed")
    assert c["status"] == "draft"
    # B + C are active; archived A still excluded.
    assert await cv_service.count_cvs(db_session, principal=student) == 2


async def test_soft_deleted_cvs_do_not_count_toward_quota(db_session, monkeypatch) -> None:
    monkeypatch.setattr(_cv_core, "_active_cv_limit", lambda: 2)
    _u, student = await make_student(db_session)
    a = await _make_blank(db_session, student, "A")
    await _make_blank(db_session, student, "B")  # at 2/2

    # Soft-delete A (deleting a CV archives/soft-deletes the row).
    row = (
        await db_session.execute(
            select(CvProfile).where(CvProfile.id == uuid.UUID(a["id"]))
        )
    ).scalar_one()
    row.deleted_at = _shared.now()
    await db_session.commit()

    assert await cv_service.count_cvs(db_session, principal=student) == 1
    c = await _make_blank(db_session, student, "C now allowed")
    assert c["status"] == "draft"


async def test_cv_library_quota_meta_shape(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_blank(db_session, student, "A")
    quota = await cv_service.cv_library_quota(db_session, principal=student)
    assert quota["active_cv_limit"] == 5
    assert quota["active_cv_used"] == 1
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
    cv = await cv_service.create_cv(
        db, principal=student, payload={"title": "Snap CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    from app.modules.documents.domain.models import CvVersion

    version = (
        await db.execute(select(CvVersion).where(CvVersion.cv_id == uuid.UUID(cv["id"])))
    ).scalars().first()
    return await snapshot_service.create_application_cv_snapshot(
        db, owner_id=student.user_id,
        cv_selection={"type": "builder_cv", "cv_profile_id": cv["id"],
                      "cv_version_id": str(version.id)},
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
