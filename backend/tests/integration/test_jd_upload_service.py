import pytest
from app.ai.extraction.jd import cascade
from app.ai.extraction.text_extraction import ExtractionResult
from app.modules.opportunities.application import jd_upload_service as svc
from app.shared.exceptions import ValidationFailedError


@pytest.mark.asyncio
async def test_ok_returns_backward_compatible_and_new_fields(monkeypatch):
    jd_text = ("Tuyển Kỹ sư Backend. Mô tả công việc: xây dựng API. "
               "Yêu cầu: 2 năm kinh nghiệm. Quyền lợi: lương 20-30 triệu gross.")
    monkeypatch.setattr(
        cascade, "extract_text",
        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"),
    )

    async def fake_structurer(text):
        return {"title": "Kỹ sư Backend", "employment_type": "full_time",
                "salary_mode": "range", "salary_min": 20000000, "salary_max": 30000000,
                "salary_gross_net": "gross", "experience_mode": "min",
                "experience_min_years": 2, "detected_language": "vi",
                "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}}}

    out = await svc.extract_jd_from_upload_with(
        filename="jd.pdf", data=b"%PDF fake", structurer=fake_structurer,
        vision_runner=lambda *a, **k: None,
    )
    # backward-compatible keys
    assert out["is_ai_extraction"] is True
    assert out["employment_type"] == "full_time"
    assert out["field_confidence"]["employment_type"]["needs_review"] is True
    # new fields
    assert out["salary_mode"] == "range"
    assert out["candidate_requirements"]["gender"]["mode"] == "required"
    assert out["status"] == "ok"


@pytest.mark.asyncio
async def test_not_a_jd_raises_user_safe_error(monkeypatch):
    cv_text = "Nguyen Van A. Email a@x.com. Học vấn Đại học. Kinh nghiệm. Kỹ năng Python."
    monkeypatch.setattr(
        cascade, "extract_text",
        lambda f, d: ExtractionResult(text=cv_text, page_count=1, engine="pdfplumber"),
    )

    async def unused(text):
        raise AssertionError("no LLM for non-JD")

    with pytest.raises(ValidationFailedError) as ei:
        await svc.extract_jd_from_upload_with(
            filename="resume.pdf", data=b"%PDF fake",
            structurer=unused, vision_runner=lambda *a, **k: None)
    assert ei.value.details["reason"] == "not_a_jd"
