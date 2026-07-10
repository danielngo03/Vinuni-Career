"""CV ingestion cascade + explicit ingestion API tests.

Covers (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §8 eval set + minimum acceptance):

- upload preview metadata (no storage path) + signed preview download;
- classification of blank / not-CV / corrupt / password / duplicate / low-quality;
- deterministic structuring captures contact + key sections for text PDF / DOCX;
- OCR fallback path with a MOCKED OCR engine (unavailable -> LOW_QUALITY_SCAN);
- LLM structuring fallback DISABLED/unavailable AND enabled-with-FAKE provider
  (text-only input asserted — raw bytes never reach the LLM);
- import creates a versioned draft, is idempotent, respects quota, never
  overwrites accepted content;
- no raw CV text in any audit payload; no engine/provider/model leak in responses;
- owner-only access (cross-owner -> 404).
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from app.ai.extraction import cv_ingestion_cascade
from app.ai.extraction.adapters import (
    resolve_policy,
    run_llm_structuring,
    set_llm_structuring_adapter,
    set_ocr_adapter,
    set_vision_adapter,
)
from app.ai.extraction.text_extraction import ExtractionError
from app.core.config import get_settings
from app.modules.documents.application import (
    cv_service,
    download_service,
    ingestion_service,
    template_seed,
)
from app.modules.documents.application.errors import (
    CvQuotaReachedError,
    FactConfirmationFieldsRequiredError,
)
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvIngestion, Document
from app.modules.documents.infrastructure import storage
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.models import AuditLog
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import (
    InMemoryStorage,
    make_ready_cv,
    make_student,
    new_key,
)
from tests.fixtures import cv as F


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


@pytest.fixture(autouse=True)
def _reset_adapters_and_settings():
    yield
    import os

    from app.ai.gateway import runtime_config

    set_ocr_adapter(None)
    set_llm_structuring_adapter(None)
    set_vision_adapter(None)
    # `_enable_llm`/`_enable_ocr_engine` set these process-wide env vars; they must
    # be removed (not just cache-cleared) or they leak into `get_settings()` and the
    # published gateway snapshot, failing combined runs (e.g. ai_settings tests).
    os.environ.pop("CV_LLM_STRUCTURING_ENABLED", None)
    os.environ.pop("CV_OCR_ENGINE", None)
    get_settings.cache_clear()
    # Drop any snapshot this test published so `runtime_config.current()` returns
    # the clean env default for the next test in the same process.
    runtime_config.reset_to_bootstrap()


# Rich, valid CV text so OCR-success classifies as REVIEW_REQUIRED.
_OCR_TEXT = (
    "Scanned Candidate\n"
    "Email: scanned.candidate@example.com | Phone: +84 900 333 444\n"
    "Summary\nData engineering intern with pipeline experience.\n"
    "Experience\nData Intern at Example Corp (2024-2025). Built ETL jobs in Python.\n"
    "Education\nVinUniversity BSc Computer Science 2026.\n"
    "Skills\nPython, SQL, Airflow, dbt, PostgreSQL.\n"
)


class FakeOcr:
    engine_family = "ocr_fake"
    engine_version = "fake-ocr-1"

    def __init__(self, text: str = _OCR_TEXT) -> None:
        self._text = text
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def recognize(self, data: bytes, langs: str) -> str:
        self.calls += 1
        return self._text


class FakeLlm:
    """Fake LLM structuring engine that records the TYPE of its input."""

    def __init__(self) -> None:
        self.inputs: list[object] = []

    @property
    def available(self) -> bool:
        return True

    def refine(self, text, base_result):
        self.inputs.append(text)
        refined = dict(base_result)
        refined["llm_marker"] = True
        return refined


def _enable_ocr_engine() -> None:
    import os

    os.environ["CV_OCR_ENGINE"] = "tesseract"
    get_settings.cache_clear()


def _enable_llm() -> None:
    import os

    os.environ["CV_LLM_STRUCTURING_ENABLED"] = "true"
    get_settings.cache_clear()


def _disable_async() -> None:
    import os

    os.environ["CV_INGESTION_ASYNC"] = "false"
    get_settings.cache_clear()


async def _upload(db, student, *, filename, data, content_type="application/pdf"):
    return await ingestion_service.create_upload(
        db,
        principal=student,
        filename=filename,
        data=data,
        content_type=content_type,
        idempotency_key=new_key(),
        ctx=CTX,
    )


async def _ingest(db, student, document_id):
    return await ingestion_service.start_ingestion(
        db,
        principal=student,
        document_id=uuid.UUID(document_id),
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Upload preview                                                              #
# --------------------------------------------------------------------------- #


async def test_upload_returns_preview_metadata_without_storage_path(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    assert result["document_id"]
    assert result["filename"] == "cv.pdf"
    assert result["content_type"] == "application/pdf"
    assert result["size"] > 0
    assert result["preview_url"].startswith("http")
    assert "/api/v1/cv-files/" in result["preview_url"]
    # No storage path / key leaks anywhere in the payload.
    blob = json.dumps(result)
    assert "cv-uploads/" not in blob
    assert "storage" not in blob.lower()


async def test_upload_preview_token_downloads_original(db_session) -> None:
    _u, student = await make_student(db_session)
    data = F.text_pdf_en()
    result = await _upload(db_session, student, filename="cv.pdf", data=data)
    token = result["preview_url"].rsplit("/", 1)[-1]
    download = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert download.content == data


async def test_upload_rejects_infected_file_without_storing(db_session) -> None:
    from app.ai.extraction import cv_validation

    _u, student = await make_student(db_session)
    infected = cv_validation._EICAR + b" experience education skills"
    with pytest.raises(ValidationFailedError):
        await _upload(
            db_session,
            student,
            filename="virus.txt",
            data=infected,
            content_type="text/plain",
        )


# --------------------------------------------------------------------------- #
# Image CV -> PDF on upload (owner decision 2026-07-10)                         #
# --------------------------------------------------------------------------- #


def _real_png(text: str = "Candidate CV") -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 640), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _real_webp(text: str = "Candidate CV") -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 640), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


@pytest.mark.parametrize(
    ("filename", "builder", "content_type"),
    [
        ("resume.png", _real_png, "image/png"),
        ("resume.webp", _real_webp, "image/webp"),
    ],
)
async def test_image_cv_is_stored_and_served_as_pdf(
    db_session, filename, builder, content_type
) -> None:
    _u, student = await make_student(db_session)
    result = await _upload(
        db_session, student, filename=filename, data=builder(), content_type=content_type
    )
    # The upload preview reports a PDF artifact + a ``.pdf`` display name.
    assert result["content_type"] == "application/pdf"
    assert result["filename"].endswith(".pdf")

    # The stored document is a real PDF (magic %PDF), and the preview token serves it.
    doc = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(result["document_id"]))
        )
    ).scalar_one()
    assert doc.mime_type == "application/pdf"
    assert storage.get_storage().load(doc.storage_path)[:5] == b"%PDF-"

    token = result["preview_url"].rsplit("/", 1)[-1]
    served = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert served.media_type == "application/pdf"
    assert served.content[:5] == b"%PDF-"


async def test_corrupt_image_upload_stored_then_rejected_by_cascade(db_session) -> None:
    # A corrupt image cannot be wrapped into a PDF: the upload does NOT crash (the
    # original bytes are stored) and the ingestion cascade classifies it as a
    # failed low-quality scan — never fabricated into a CV.
    _u, student = await make_student(db_session)
    corrupt = b"\x89PNG\r\n\x1a\n" + b"not-a-decodable-image" * 4
    result = await _upload(
        db_session, student, filename="broken.png", data=corrupt, content_type="image/png"
    )
    # Unconvertible -> stored as the original image (no crash).
    assert result["content_type"] == "image/png"
    doc = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(result["document_id"]))
        )
    ).scalar_one()
    assert storage.get_storage().load(doc.storage_path) == corrupt

    ing = await _ingest(db_session, student, result["document_id"])
    assert ing["status"] == "failed"
    assert ing["quality_code"] in ("LOW_QUALITY_SCAN", "CORRUPT_FILE")


async def test_duplicate_image_cv_detected_despite_pdf_conversion(db_session) -> None:
    # Two uploads of the SAME image become two (non-byte-identical) PDFs, but the
    # checksum is pinned to the ORIGINAL image bytes so the duplicate is still caught
    # at the cascade's file gate (before any OCR/vision work).
    _u, student = await make_student(db_session)
    img = _real_png("Dup CV")
    up1 = await _upload(db_session, student, filename="a.png", data=img, content_type="image/png")
    await _ingest(db_session, student, up1["document_id"])
    up2 = await _upload(db_session, student, filename="b.png", data=img, content_type="image/png")
    ing2 = await _ingest(db_session, student, up2["document_id"])
    assert ing2["status"] == "failed"
    assert ing2["quality_code"] == "DUPLICATE_FILE"


# --------------------------------------------------------------------------- #
# Happy path: text PDF + DOCX deterministic structuring                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "builder", "content_type", "language"),
    [
        ("cv.pdf", F.text_pdf_en, "application/pdf", "en"),
        ("cv.docx", F.docx_cv, "application/vnd.openxmlformats", "en"),
        ("cv.txt", F.vietnamese_cv_txt, "text/plain", "vi"),
        ("two.pdf", F.two_column_pdf, "application/pdf", "en"),
    ],
)
async def test_ingest_text_documents_capture_contact_and_sections(
    db_session, filename, builder, content_type, language
) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(
        db_session, student, filename=filename, data=builder(), content_type=content_type
    )
    ing = await _ingest(db_session, student, up["document_id"])

    assert ing["status"] in ("needs_review", "ready")
    assert ing["quality_code"] == "REVIEW_REQUIRED"
    assert ing["detected_language"] == language
    assert ing["quality_message"]
    assert "import_to_cv" in ing["next_actions"]
    # review_fields carry needs-review markers, not numeric confidence.
    paths = {f["path"] for f in ing["review_fields"]}
    assert "contact.email" in paths
    for f in ing["review_fields"]:
        assert "confidence" not in f
        assert set(f.keys()) <= {"path", "value", "needs_review", "source_span", "page"}
    # Contact email was actually captured.
    email_field = next(f for f in ing["review_fields"] if f["path"] == "contact.email")
    assert "@" in email_field["value"]


async def test_ingestion_response_has_no_engine_or_provider_leak(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, student, up["document_id"])
    # Internal engine/provider keys + diagnostics must never appear in the response.
    assert "engine_family" not in ing
    assert "engine_version" not in ing
    assert "text_length" not in ing
    assert "error_code" not in ing
    assert "extracted_data" not in ing
    blob = json.dumps(ing).lower()
    for needle in (
        "pdfplumber",
        "pymupdf",
        "tesseract",
        "native_pdf",
        "engine_family",
        "engine_version",
        "openrouter",
        "deepseek",
        "provider_alias",
    ):
        assert needle not in blob, needle


# --------------------------------------------------------------------------- #
# Classification of failure cases                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "builder", "content_type", "expected"),
    [
        ("blank.pdf", F.blank_pdf, "application/pdf", "BLANK_DOCUMENT"),
        ("notes.pdf", F.not_cv_pdf, "application/pdf", "NOT_A_CV"),
        ("broken.pdf", F.corrupt_pdf, "application/pdf", "CORRUPT_FILE"),
        ("sparse.pdf", F.sparse_canvas_pdf, "application/pdf", "LOW_QUALITY_SCAN"),
        ("scan.png", F.scanned_image_cv, "image/png", "LOW_QUALITY_SCAN"),
    ],
)
async def test_ingest_failure_cases_classified(
    db_session, filename, builder, content_type, expected
) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(
        db_session, student, filename=filename, data=builder(), content_type=content_type
    )
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] == "failed"
    assert ing["quality_code"] == expected
    assert ing["quality_message"]
    assert ing["next_actions"]  # always a practical recovery path


async def test_ingest_duplicate_detected(db_session) -> None:
    _u, student = await make_student(db_session)
    data = F.text_pdf_en()
    up1 = await _upload(db_session, student, filename="cv.pdf", data=data)
    await _ingest(db_session, student, up1["document_id"])
    up2 = await _upload(db_session, student, filename="cv-again.pdf", data=data)
    ing2 = await _ingest(db_session, student, up2["document_id"])
    assert ing2["status"] == "failed"
    assert ing2["quality_code"] == "DUPLICATE_FILE"


async def test_ingest_password_protected_mocked(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="locked.pdf", data=F.text_pdf_en())

    class LockedAdapter:
        def __init__(self, *_a, **_k) -> None: ...

        def extract(self, filename, data):
            raise ExtractionError("PASSWORD_PROTECTED_FILE")

    monkeypatch.setattr(cv_ingestion_cascade, "NativeTextAdapter", LockedAdapter)
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] == "failed"
    assert ing["quality_code"] == "PASSWORD_PROTECTED_FILE"


# --------------------------------------------------------------------------- #
# OCR fallback (mocked engine)                                                 #
# --------------------------------------------------------------------------- #


async def test_ocr_fallback_with_mocked_engine(db_session) -> None:
    _u, student = await make_student(db_session)
    fake = FakeOcr()
    set_ocr_adapter(fake)
    _enable_ocr_engine()
    up = await _upload(
        db_session,
        student,
        filename="scan.png",
        data=F.scanned_image_cv(),
        content_type="image/png",
    )
    ing = await _ingest(db_session, student, up["document_id"])
    assert fake.calls >= 1
    assert ing["status"] in ("needs_review", "ready")
    assert ing["quality_code"] == "REVIEW_REQUIRED"
    email_field = next(f for f in ing["review_fields"] if f["path"] == "contact.email")
    assert "@" in email_field["value"]


async def test_ocr_unavailable_records_low_quality(db_session) -> None:
    # Default policy has no OCR engine available -> scanned image -> LOW_QUALITY_SCAN,
    # and the user copy never mentions a missing engine.
    _u, student = await make_student(db_session)
    up = await _upload(
        db_session,
        student,
        filename="scan.png",
        data=F.scanned_image_cv(),
        content_type="image/png",
    )
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["quality_code"] == "LOW_QUALITY_SCAN"
    assert "engine" not in ing["quality_message"].lower()
    assert "ocr" not in ing["quality_message"].lower()


# --------------------------------------------------------------------------- #
# Vision-LLM tier (styled image / scanned CV) — fake adapter, no real calls     #
# --------------------------------------------------------------------------- #


class FakeVision:
    """Fake multimodal extraction engine (returns a pre-baked structured result)."""

    engine_family = "vision_fake"
    engine_version = "fake-vision-1"

    def __init__(self, result: dict | None) -> None:
        self._result = result
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        self.calls += 1
        assert isinstance(data, (bytes, bytearray))  # the vision tier gets bytes
        return self._result


def test_vision_tier_structures_styled_image_cv() -> None:
    # A styled/multi-column image CV is structured by the vision tier directly,
    # bypassing the unreliable OCR + regex path. Vision output flows through the
    # same review_fields shape as every other engine.
    from app.ai.extraction.cv_structuring import review_fields_for_extracted

    extracted = {
        "contact": {
            "name": "Nguyễn Hương Lê",
            "email": "hotro@topcv.vn",
            "phone": "(024) 6680 5588",
            "location": "Ba Đình, Hà Nội",
        },
        "experience": {"items": [{"text": "Điều dưỡng nhi khoa - Trung tâm Y tế - 04/2020 - Nay"}]},
        "skills": {"items": [{"text": "Kỹ năng giao tiếp"}]},
    }
    fake = FakeVision(
        {
            "extracted_data": extracted,
            "review_fields": review_fields_for_extracted(extracted),
            "detected_language": "vi",
        }
    )
    set_vision_adapter(fake)
    try:
        outcome = cv_ingestion_cascade.run_cascade(
            "cv.png",
            F.scanned_image_cv(),
            max_bytes=50 * 1024 * 1024,
            policy=resolve_policy(),
        )
        assert fake.calls == 1
        assert outcome.accepted is True
        assert outcome.vision_used is True
        assert outcome.ocr_used is False
        assert outcome.quality_code == "REVIEW_REQUIRED"
        assert outcome.engine_family == "vision_llm_gateway"  # internal-only
        assert outcome.extracted_data["contact"]["name"] == "Nguyễn Hương Lê"
        assert outcome.detected_language == "vi"
        paths = {f["path"] for f in outcome.review_fields}
        assert "contact.email" in paths
        assert "experience[0].text" in paths
    finally:
        set_vision_adapter(None)


def test_vision_returns_nothing_falls_back_to_ocr() -> None:
    # When the vision tier is enabled but yields nothing (model error / offline),
    # the cascade degrades to the local OCR + deterministic structuring path.
    fake_vision = FakeVision(None)
    fake_ocr = FakeOcr()
    set_vision_adapter(fake_vision)
    set_ocr_adapter(fake_ocr)
    _enable_ocr_engine()
    try:
        outcome = cv_ingestion_cascade.run_cascade(
            "scan.png",
            F.scanned_image_cv(),
            max_bytes=50 * 1024 * 1024,
            policy=resolve_policy(),
        )
        assert fake_vision.calls == 1
        assert fake_ocr.calls >= 1
        assert outcome.vision_used is False
        assert outcome.ocr_used is True
        assert outcome.accepted is True
    finally:
        set_vision_adapter(None)
        set_ocr_adapter(None)


# --------------------------------------------------------------------------- #
# LLM structuring fallback (disabled by default + fake provider; text only)    #
# --------------------------------------------------------------------------- #


def test_llm_structuring_disabled_by_default() -> None:
    # No adapter wired + flag off -> deterministic result is final.
    policy = resolve_policy()
    assert policy.llm_enabled is False
    assert run_llm_structuring("some extracted text", {"extracted_data": {}}) is None


def test_llm_structuring_enabled_receives_text_only() -> None:
    fake = FakeLlm()
    set_llm_structuring_adapter(fake)
    _enable_llm()
    try:
        outcome = cv_ingestion_cascade.run_cascade(
            "cv.pdf",
            F.text_pdf_en(),
            max_bytes=50 * 1024 * 1024,
            policy=resolve_policy(),
        )
        assert outcome.llm_used is True
        # The adapter only ever saw a str (extracted text) — never bytes.
        assert fake.inputs
        assert all(isinstance(x, str) for x in fake.inputs)
        assert not any(isinstance(x, (bytes, bytearray)) for x in fake.inputs)
    finally:
        set_llm_structuring_adapter(None)


def test_llm_structuring_rejects_raw_bytes() -> None:
    fake = FakeLlm()
    set_llm_structuring_adapter(fake)
    try:
        with pytest.raises(TypeError):
            run_llm_structuring(b"%PDF-1.4 raw bytes", {})  # type: ignore[arg-type]
    finally:
        set_llm_structuring_adapter(None)


# --------------------------------------------------------------------------- #
# Import: versioned draft, idempotent, quota, no overwrite                     #
# --------------------------------------------------------------------------- #


async def _ingest_ready(db, student, *, filename="cv.pdf", builder=F.text_pdf_en):
    up = await _upload(db, student, filename=filename, data=builder())
    ing = await _ingest(db, student, up["document_id"])
    return ing


async def test_import_creates_versioned_draft(db_session) -> None:
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)

    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Imported CV"},
        ctx=CTX,
    )
    # An uploaded CV is already extracted/analyzed -> lands directly in the library
    # (``ready``), not a scratch draft (design spec 2026-07-05).
    assert detail["status"] == "ready"
    assert detail["in_library"] is True
    assert detail["finalized_at"] is not None
    assert detail["source_type"] == "uploaded_import"
    assert detail["current_version_id"]
    assert len(detail["versions"]) == 1
    assert detail["sections"]
    # The ingestion row now points at the created library CV.
    ing_row = (
        await db_session.execute(
            select(CvIngestion).where(CvIngestion.id == uuid.UUID(ing["ingestion_id"]))
        )
    ).scalar_one()
    assert str(ing_row.imported_cv_id) == detail["id"]


def _section_texts(detail: dict, section_type: str) -> list[str]:
    sect = next(s for s in detail["sections"] if s["section_type"] == section_type)
    content = sect.get("content") or {}
    # Item sections carry {text} (free text) or {name} (skills/languages); entry
    # sections (experience/education/projects) carry {heading, ...}. Read whichever
    # this section uses so the helper works across all structured shapes (B-599).
    out = [
        it.get("text") if it.get("text") is not None else it.get("name")
        for it in content.get("items", [])
    ]
    out += [e.get("heading") for e in content.get("entries", [])]
    return out


async def test_import_carries_contact_in_header_section(db_session) -> None:
    # An imported CV must carry the person's name + contact in a header section so
    # the rendered CV can show a real header (not a nameless document).
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)

    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Imported CV"},
        ctx=CTX,
    )
    header = next(s for s in detail["sections"] if s["section_type"] == "header")
    content = header["content"]
    assert content.get("name") == "Jane Engineer"
    assert content.get("email") == "jane.engineer@example.com"
    assert content.get("phone")  # phone flowed through
    # Header content is a flat contact object — never entries/items.
    assert "entries" not in content and "items" not in content


async def test_import_applies_review_field_overrides(db_session) -> None:
    # The student edits a low-confidence free-text field on the review screen; the
    # edited value (not the original extracted value) must land in the draft. Free
    # text sections (summary) keep the reviewable {text} shape; structured sections
    # (skills as {name,level}, experience as entries) are backend-authoritative.
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)

    paths = {f["path"] for f in ing["review_fields"]}
    assert "summary[0].text" in paths
    original = next(f["value"] for f in ing["review_fields"] if f["path"] == "summary[0].text")
    edited = "Backend intern specialising in data pipelines and APIs."
    assert edited != original

    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [{"path": "summary[0].text", "value": edited}],
        },
        ctx=CTX,
    )
    # The edited value is in the created draft's summary section...
    assert edited in _section_texts(detail, "summary")
    assert original not in _section_texts(detail, "summary")
    # ...while non-overridden sections are preserved unchanged (experience entries,
    # skills names still present).
    assert _section_texts(detail, "experience")
    assert _section_texts(detail, "skills")
    # A brand-new versioned library CV (never an overwrite of an existing CV).
    assert detail["status"] == "ready"
    assert len(detail["versions"]) == 1
    # The stored ingestion row's extracted_data is NOT mutated by the override.
    ing_row = (
        await db_session.execute(
            select(CvIngestion).where(CvIngestion.id == uuid.UUID(ing["ingestion_id"]))
        )
    ).scalar_one()
    stored = ing_row.extracted_data["summary"]["items"][0]["text"]
    assert stored == original


async def test_import_overrides_reject_unknown_paths(db_session) -> None:
    # An override path the ingestion never produced is ignored — no injection of
    # new sections/values into the draft.
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    original = next(f["value"] for f in ing["review_fields"] if f["path"] == "summary[0].text")

    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [
                {"path": "evil[0].text", "value": "<script>alert(1)</script>"},
                {"path": "contact.ssn", "value": "999"},
                {"path": "summary[99].text", "value": "out of range"},
            ],
        },
        ctx=CTX,
    )
    # No forbidden section type appears; summary untouched by the rejected paths.
    section_types = {s["section_type"] for s in detail["sections"]}
    assert "evil" not in section_types
    assert _section_texts(detail, "summary") == [original]
    blob = json.dumps(detail)
    assert "<script>" not in blob
    assert "999" not in blob


async def test_import_without_overrides_unchanged(db_session) -> None:
    # Regression: omitting overrides behaves exactly as the original import.
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    original = next(f["value"] for f in ing["review_fields"] if f["path"] == "summary[0].text")
    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Imported CV"},
        ctx=CTX,
    )
    assert detail["status"] == "ready"
    assert len(detail["versions"]) == 1
    assert _section_texts(detail, "summary") == [original]


async def test_import_with_overrides_never_overwrites_accepted_cv(db_session) -> None:
    # Overrides + an accepted target CV must still be blocked (no overwrite).
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    blank = await cv_service.create_cv(
        db_session,
        principal=student,
        payload={"title": "Accepted CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    await cv_service.update_cv(
        db_session,
        principal=student,
        cv_id=uuid.UUID(blank["id"]),
        payload={"status": "ready"},
        ctx=CTX,
    )
    with pytest.raises(ValidationFailedError):
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={
                "target_cv_id": blank["id"],
                "overrides": [{"path": "summary[0].text", "value": "edited"}],
            },
            ctx=CTX,
        )


async def test_import_with_overrides_respects_quota(db_session) -> None:
    # Overrides do not bypass the active-CV quota gate (still 409). The library must
    # be filled with READY CVs (drafts are free / don't count) to hit the cap.
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    limit = cv_service._active_cv_limit()
    for i in range(limit):
        await make_ready_cv(db_session, student=student, title=f"CV {i}")
    with pytest.raises(CvQuotaReachedError) as exc:
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={"overrides": [{"path": "summary[0].text", "value": "edited"}]},
            ctx=CTX,
        )
    assert exc.value.http_status == 409


async def test_import_is_idempotent(db_session) -> None:
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    first = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={},
        ctx=CTX,
    )
    second = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={},
        ctx=CTX,
    )
    assert first["id"] == second["id"]


async def test_import_respects_active_cv_quota(db_session) -> None:
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    # Fill the active-CV library to the default cap with READY (committed) CVs.
    limit = cv_service._active_cv_limit()
    for i in range(limit):
        await make_ready_cv(db_session, student=student, title=f"CV {i}")
    with pytest.raises(CvQuotaReachedError) as exc:
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={},
            ctx=CTX,
        )
    assert exc.value.http_status == 409


async def test_import_into_ready_cv_is_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    # Create a CV and mark it ready (accepted) — import must not overwrite it.
    blank = await cv_service.create_cv(
        db_session,
        principal=student,
        payload={"title": "Accepted CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    await cv_service.update_cv(
        db_session,
        principal=student,
        cv_id=uuid.UUID(blank["id"]),
        payload={"status": "ready"},
        ctx=CTX,
    )
    with pytest.raises(ValidationFailedError):
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={"target_cv_id": blank["id"]},
            ctx=CTX,
        )


async def test_import_requires_ready_ingestion(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="blank.pdf", data=F.blank_pdf())
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] == "failed"
    with pytest.raises(ValidationFailedError):
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={},
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Owner isolation                                                              #
# --------------------------------------------------------------------------- #


async def test_cross_owner_ingestion_access_returns_404(db_session) -> None:
    _u1, owner = await make_student(db_session, prefix="owner")
    _u2, other = await make_student(db_session, prefix="other")
    up = await _upload(db_session, owner, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, owner, up["document_id"])
    with pytest.raises(ResourceNotFoundError):
        await ingestion_service.get_ingestion(
            db_session, principal=other, ingestion_id=uuid.UUID(ing["ingestion_id"])
        )


async def test_cross_owner_ingest_of_foreign_document_returns_404(db_session) -> None:
    _u1, owner = await make_student(db_session, prefix="owner")
    _u2, other = await make_student(db_session, prefix="other")
    up = await _upload(db_session, owner, filename="cv.pdf", data=F.text_pdf_en())
    with pytest.raises(ResourceNotFoundError):
        await ingestion_service.start_ingestion(
            db_session,
            principal=other,
            document_id=uuid.UUID(up["document_id"]),
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Privacy: no raw CV text in any audit payload                                 #
# --------------------------------------------------------------------------- #


async def test_no_raw_cv_text_in_audit_payloads(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    await _ingest(db_session, student, up["document_id"])

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert rows
    dumped = json.dumps(
        [{"a": r.action, "before": r.before_snapshot, "after": r.after_snapshot} for r in rows]
    )
    # Known raw-CV tokens from the fixture must never appear in audit data.
    for token in ("jane.engineer", "FastAPI", "VinUniversity", "SQLAlchemy"):
        assert token not in dumped, token


async def test_async_and_inline_paths_both_complete(db_session) -> None:
    # Inline (sync) execution path still yields a terminal ingestion.
    _disable_async()
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] in ("needs_review", "ready")


# --------------------------------------------------------------------------- #
# Per-field reject (accepted=False) excludes the field from import            #
# --------------------------------------------------------------------------- #


async def test_import_override_reject_excludes_item(db_session) -> None:
    # A field the student explicitly REJECTS (not just edits) must never land in
    # the imported draft — a real accept/edit/reject diff, not a blanket checkbox.
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)
    original = next(f["value"] for f in ing["review_fields"] if f["path"] == "summary[0].text")

    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [{"path": "summary[0].text", "accepted": False}],
        },
        ctx=CTX,
    )
    assert _section_texts(detail, "summary") == []
    assert original not in json.dumps(detail)
    # Other sections are unaffected (experience entries + skills survive).
    assert _section_texts(detail, "experience")
    assert _section_texts(detail, "skills")


async def test_import_override_reject_contact_field(db_session) -> None:
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)
    ing = await _ingest_ready(db_session, student)

    ing_row = (
        await db_session.execute(
            select(CvIngestion).where(CvIngestion.id == uuid.UUID(ing["ingestion_id"]))
        )
    ).scalar_one()
    original_email = ing_row.extracted_data["contact"]["email"]

    await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [{"path": "contact.email", "accepted": False}],
        },
        ctx=CTX,
    )
    # The stored ingestion row is never mutated by the reject decision.
    await db_session.refresh(ing_row)
    assert ing_row.extracted_data["contact"]["email"] == original_email


# --------------------------------------------------------------------------- #
# Per-field confirmation gate for NEEDS_REVIEW ingestions                     #
# --------------------------------------------------------------------------- #


async def _make_needs_review_ingestion(db) -> tuple[object, dict]:
    """Directly construct a NEEDS_REVIEW ingestion with one flagged field.

    Bypasses the full extraction cascade (no fixture reliably produces
    ``needs_review = True`` deterministically) to exercise the per-field
    confirmation gate in isolation.
    """

    _u, student = await make_student(db)
    document = Document(
        user_id=student.user_id,
        doc_type="cv",
        original_name="cv.pdf",
        storage_path="cv-uploads/x",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="x" * 64,
        virus_scan_status="clean",
    )
    db.add(document)
    await db.flush()
    ing = CvIngestion(
        document_id=document.id,
        user_id=student.user_id,
        status=catalog.INGEST_NEEDS_REVIEW,
        quality_code="REVIEW_REQUIRED",
        detected_language="en",
        extracted_data={
            "contact": {"name": "Jane Doe", "email": "", "phone": ""},
            "skills": {"items": [{"text": "Python"}]},
        },
        review_fields=[
            {"path": "contact.name", "value": "Jane Doe", "needs_review": False},
            {"path": "contact.email", "value": "", "needs_review": True},
            {"path": "skills[0].text", "value": "Python", "needs_review": False},
        ],
        next_actions=["review_fields", "import_to_cv", "keep_original"],
    )
    db.add(ing)
    await db.flush()
    await db.commit()
    return student, {"ingestion_id": str(ing.id)}


async def test_import_needs_review_requires_per_field_decision(db_session) -> None:
    student, ing = await _make_needs_review_ingestion(db_session)
    with pytest.raises(FactConfirmationFieldsRequiredError) as exc:
        await ingestion_service.import_ingestion(
            db_session,
            principal=student,
            ingestion_id=uuid.UUID(ing["ingestion_id"]),
            payload={"title": "Imported CV"},
            ctx=CTX,
        )
    assert exc.value.details["fields"] == ["contact.email"]


async def test_import_needs_review_succeeds_with_per_field_override(db_session) -> None:
    student, ing = await _make_needs_review_ingestion(db_session)
    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [{"path": "contact.email", "value": "jane@example.com"}],
        },
        ctx=CTX,
    )
    assert detail["status"] == "ready"


async def test_import_needs_review_succeeds_with_field_rejected(db_session) -> None:
    student, ing = await _make_needs_review_ingestion(db_session)
    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={
            "title": "Imported CV",
            "overrides": [{"path": "contact.email", "accepted": False}],
        },
        ctx=CTX,
    )
    assert detail["status"] == "ready"


async def test_import_needs_review_succeeds_with_blanket_fact_confirmation(db_session) -> None:
    student, ing = await _make_needs_review_ingestion(db_session)
    detail = await ingestion_service.import_ingestion(
        db_session,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Imported CV", "fact_confirmation": True},
        ctx=CTX,
    )
    assert detail["status"] == "ready"
