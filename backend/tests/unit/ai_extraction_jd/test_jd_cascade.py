# backend/tests/unit/ai_extraction_jd/test_jd_cascade.py
import pytest
from app.ai.extraction.jd import cascade
from app.ai.extraction.text_extraction import ExtractionResult
from app.shared.exceptions import AIUnavailableError


class _Res(ExtractionResult):
    pass


@pytest.mark.asyncio
async def test_digital_pdf_uses_text_path_no_vision(monkeypatch):
    jd_text = (
        "Tuyển Nhân viên Kinh doanh. Mô tả công việc: bán hàng. "
        "Yêu cầu: 1 năm kinh nghiệm. Quyền lợi: lương 10-15 triệu."
    )
    monkeypatch.setattr(
        cascade,
        "extract_text",
        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"),
    )

    async def fake_structurer(text):
        return {
            "is_jd": True,
            "title": "Nhân viên Kinh doanh",
            "employment_type": "full_time",
            "salary_mode": "range",
            "salary_min": 10000000,
            "salary_max": 15000000,
        }

    vision_calls = []

    def fake_vision(*a, **k):
        vision_calls.append(1)
        return None

    out = await cascade.run_jd_cascade(
        "jd.pdf", b"%PDF-1.4 fake", structurer=fake_structurer, vision_runner=fake_vision
    )
    assert out.status == "ok"
    assert out.is_ai_extraction is True
    assert out.fields["employment_type"] == "full_time"
    assert out.fields["salary_mode"] == "range"
    assert vision_calls == []  # digital text never reaches vision


@pytest.mark.asyncio
async def test_image_uses_vision_path(monkeypatch):
    monkeypatch.setattr(
        cascade, "extract_text", lambda f, d: ExtractionResult(text="", page_count=1, engine="none")
    )

    def fake_vision(data, kind, *, enabled, max_image_px, max_pages, native_text=None):
        return {
            "is_jd": True,
            "title": "Sales Exec",
            "employment_type": "full_time",
            "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}},
        }

    async def fake_structurer(text):
        raise AssertionError("text structurer must not run on the vision path")

    out = await cascade.run_jd_cascade(
        "jd.png", b"\xff\xd8\xff fake", structurer=fake_structurer, vision_runner=fake_vision
    )
    assert out.status == "ok"
    assert out.fields["title"] == "Sales Exec"
    assert out.fields["candidate_requirements"]["gender"]["mode"] == "required"
    assert out.vision_used is True


@pytest.mark.asyncio
async def test_cv_pdf_rejected_as_not_a_jd(monkeypatch):
    cv_text = (
        "Nguyen Van A. Email a@x.com. Học vấn: Đại học. Kinh nghiệm: công ty X. Kỹ năng: Python."
    )
    monkeypatch.setattr(
        cascade,
        "extract_text",
        lambda f, d: ExtractionResult(text=cv_text, page_count=1, engine="pdfplumber"),
    )

    async def fake_structurer(text):
        raise AssertionError("must not call LLM for a non-JD")

    out = await cascade.run_jd_cascade(
        "resume.pdf",
        b"%PDF fake",
        structurer=fake_structurer,
        vision_runner=lambda *a, **k: None,
    )
    assert out.status == "not_a_jd"
    assert out.is_ai_extraction is False
    assert out.fields == {}


@pytest.mark.asyncio
async def test_ai_unavailable_returns_raw_text_fallback(monkeypatch):
    jd_text = "Tuyển dụng: Mô tả công việc và yêu cầu, quyền lợi mức lương 10 triệu." * 3
    monkeypatch.setattr(
        cascade,
        "extract_text",
        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"),
    )

    async def down(text):
        raise AIUnavailableError()

    out = await cascade.run_jd_cascade(
        "jd.pdf", b"%PDF fake", structurer=down, vision_runner=lambda *a, **k: None
    )
    assert out.status == "ai_unavailable"
    assert out.is_ai_extraction is False
    assert out.raw_text_preview and "Tuyển dụng" in out.raw_text_preview


@pytest.mark.asyncio
async def test_oversize_file_rejected(monkeypatch):
    from app.ai.extraction.jd.policy import JdEnginePolicy

    pol = JdEnginePolicy(
        max_bytes=10,
        ocr_langs="vie+eng",
        vision_enabled=False,
        vision_max_image_px=2200,
        vision_max_pages=3,
    )
    out = await cascade.run_jd_cascade("jd.pdf", b"x" * 50, policy=pol)
    assert out.status == "file_too_large"
