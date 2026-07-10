"""Partner CV serving = the STUDENT'S ORIGINAL file (owner decision 2026-07-10).

Covers: the partner CV block serves the original (no watermark) with an inline
view + attachment download URL; the stored-XSS hardening (hostile HTML/SVG "CV"
is force-served as a sandboxed ``attachment`` + ``octet-stream``, never inline);
the sandbox + nosniff response headers; header-injection-safe filenames; and the
``cv_previewed`` audit event on an inline CV view.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.api import router as docs_router
from app.modules.documents.application import download_service, snapshot_service
from app.modules.documents.domain.models import ApplicationCvSnapshot, Document
from app.modules.documents.infrastructure import storage
from app.modules.recruitment.application import apply_service
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student, new_key
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


def _token_of(url: str) -> str:
    return url.rsplit("/", 1)[-1]


async def _make_uploaded_snapshot(
    db, *, user_id: uuid.UUID, mime: str, name: str, data: bytes
) -> ApplicationCvSnapshot:
    key = new_key()
    storage.get_storage().save(key, data)
    doc = Document(
        user_id=user_id,
        doc_type="cv",
        original_name=name,
        storage_path=key,
        mime_type=mime,
        file_size_bytes=len(data),
        checksum_sha256="0" * 64,
        virus_scan_status="clean",
    )
    db.add(doc)
    await db.flush()
    snap = ApplicationCvSnapshot(
        user_id=user_id,
        uploaded_document_id=doc.id,
        snapshot_json={
            "title": name,
            "source_type": "uploaded",
            "document_id": str(doc.id),
            "sections": [],
        },
    )
    db.add(snap)
    await db.flush()
    return snap


# --------------------------------------------------------------------------- #
# Builder-CV snapshot: partner view serves the ORIGINAL rendered PDF, inline    #
# --------------------------------------------------------------------------- #


async def test_partner_view_serves_original_pdf_inline_no_watermark(db_session) -> None:
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    _su, student = await make_student(db_session, prefix="orig")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    snap_id = uuid.UUID(app["snapshot_id"])

    view = await snapshot_service.build_partner_cv_view(
        db_session, snapshot_id=snap_id, actor_id=partner.user_id
    )
    assert view is not None
    assert view["has_watermark"] is False
    assert view["view_url"] and view["download_url"]

    # Inline view: a builder CV renders to a real PDF (magic %PDF) -> served inline.
    inline = await download_service.resolve_download(
        db_session, token=_token_of(view["view_url"]), ctx=CTX
    )
    assert inline.disposition == "inline"
    assert inline.media_type == "application/pdf"
    assert inline.content[:4] == b"%PDF"

    # Download URL: same original bytes, forced attachment.
    dl = await download_service.resolve_download(
        db_session, token=_token_of(view["download_url"]), ctx=CTX
    )
    assert dl.disposition == "attachment"
    assert dl.media_type == "application/pdf"


# --------------------------------------------------------------------------- #
# Stored-XSS hardening: hostile HTML / SVG "CV" is forced to attachment          #
# --------------------------------------------------------------------------- #


async def test_hostile_html_cv_forced_to_attachment(db_session) -> None:
    _su, student = await make_student(db_session, prefix="evil")
    snap = await _make_uploaded_snapshot(
        db_session,
        user_id=student.user_id,
        mime="text/html",
        name="cv.html",
        data=b"<html><script>alert(document.cookie)</script></html>",
    )
    view = await snapshot_service.build_partner_cv_view(
        db_session, snapshot_id=snap.id, actor_id=student.user_id
    )
    assert view is not None
    # Even though the token REQUESTS inline, an HTML upload is force-downgraded.
    result = await download_service.resolve_download(
        db_session, token=_token_of(view["view_url"]), ctx=CTX
    )
    assert result.disposition == "attachment"
    assert result.media_type == "application/octet-stream"


async def test_hostile_svg_cv_forced_to_attachment(db_session) -> None:
    _su, student = await make_student(db_session, prefix="svg")
    snap = await _make_uploaded_snapshot(
        db_session,
        user_id=student.user_id,
        mime="image/svg+xml",
        name="cv.svg",
        data=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
    )
    view = await snapshot_service.build_partner_cv_view(
        db_session, snapshot_id=snap.id, actor_id=student.user_id
    )
    result = await download_service.resolve_download(
        db_session, token=_token_of(view["view_url"]), ctx=CTX
    )
    assert result.disposition == "attachment"
    assert result.media_type == "application/octet-stream"


async def test_spoofed_pdf_mime_but_html_bytes_forced_to_attachment(db_session) -> None:
    """A file stored as ``application/pdf`` whose bytes are actually HTML must not
    be inline-served (magic-number mismatch)."""

    _su, student = await make_student(db_session, prefix="spoof")
    snap = await _make_uploaded_snapshot(
        db_session,
        user_id=student.user_id,
        mime="application/pdf",
        name="cv.pdf",
        data=b"<html><body><script>alert(1)</script></body></html>",
    )
    view = await snapshot_service.build_partner_cv_view(
        db_session, snapshot_id=snap.id, actor_id=student.user_id
    )
    result = await download_service.resolve_download(
        db_session, token=_token_of(view["view_url"]), ctx=CTX
    )
    assert result.disposition == "attachment"
    assert result.media_type == "application/octet-stream"


async def test_real_uploaded_png_served_inline(db_session) -> None:
    _su, student = await make_student(db_session, prefix="png")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    snap = await _make_uploaded_snapshot(
        db_session, user_id=student.user_id, mime="image/png", name="cv.png", data=png
    )
    view = await snapshot_service.build_partner_cv_view(
        db_session, snapshot_id=snap.id, actor_id=student.user_id
    )
    result = await download_service.resolve_download(
        db_session, token=_token_of(view["view_url"]), ctx=CTX
    )
    assert result.disposition == "inline"
    assert result.media_type == "image/png"


# --------------------------------------------------------------------------- #
# Response headers: sandbox + nosniff + frame-ancestors; safe filename          #
# --------------------------------------------------------------------------- #


def test_security_headers_present() -> None:
    headers = docs_router._cv_file_security_headers("inline", "cv.pdf")
    assert headers["X-Content-Type-Options"] == "nosniff"
    csp = headers["Content-Security-Policy"]
    assert "sandbox" in csp
    assert "frame-ancestors" in csp
    # Same key control works cross-origin; X-Frame-Options is intentionally absent
    # (it would block the legitimate cross-origin FE iframe).
    assert "X-Frame-Options" not in headers


def test_content_disposition_strips_header_injection() -> None:
    header = docs_router._content_disposition("attachment", 'cv";\r\nSet-Cookie: x=1.pdf')
    assert "\r" not in header and "\n" not in header
    assert "Set-Cookie" in header  # kept as literal filename text, not a new header line
    assert header.startswith("attachment; filename=")


def test_content_disposition_rfc5987_for_non_ascii() -> None:
    header = docs_router._content_disposition("attachment", "Hồ sơ.pdf")
    assert "filename*=UTF-8''" in header


# --------------------------------------------------------------------------- #
# Audit: an inline CV view fires a ``cv_previewed`` access event                 #
# --------------------------------------------------------------------------- #


async def test_cv_previewed_audit_on_partner_detail_open(db_session) -> None:
    from app.modules.analytics.domain.partner_read_models import PartnerCandidateAccessEvent

    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    _su, student = await make_student(db_session, prefix="prev")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    detail = await apply_service.get_application(
        db_session, principal=partner, application_id=app_id
    )
    assert detail["cv"] is not None  # admin holds the wildcard -> CV viewable

    previewed = (
        await db_session.execute(
            select(func.count())
            .select_from(PartnerCandidateAccessEvent)
            .where(
                PartnerCandidateAccessEvent.application_id == app_id,
                PartnerCandidateAccessEvent.event_type == "cv_previewed",
            )
        )
    ).scalar_one()
    assert previewed == 1
