# backend/tests/unit/ai_extraction_jd/test_jd_validation.py
from app.ai.extraction.jd.validation import classify_jd_content, reject_copy
from app.ai.extraction.text_extraction import FileKind


def test_real_jd_text_is_ok():
    text = (
        "Tuyển dụng Nhân viên Kinh doanh. Mô tả công việc: tìm kiếm khách hàng. "
        "Yêu cầu: tốt nghiệp đại học, 1 năm kinh nghiệm. Quyền lợi: lương thưởng hấp dẫn. "
        "Mức lương: 10-15 triệu."
    )
    assert classify_jd_content(text, kind=FileKind.PDF, ocr_used=False) == "ok"


def test_cv_text_is_rejected_as_not_a_jd():
    cv = (
        "Nguyen Van A. Email: a@example.com. Kinh nghiệm làm việc tại công ty X. "
        "Học vấn: Đại học Bách Khoa. Kỹ năng: Python."
    )
    assert classify_jd_content(cv, kind=FileKind.PDF, ocr_used=False) == "not_a_jd"


def test_blank_text_is_blank():
    assert classify_jd_content("   ", kind=FileKind.PDF, ocr_used=False) == "blank"


def test_blank_image_is_low_quality_scan():
    assert classify_jd_content("", kind=FileKind.IMAGE, ocr_used=True) == "low_quality_scan"


def test_reject_copy_is_user_safe_bilingual():
    copy = reject_copy("not_a_jd")
    assert copy["reason"] == "not_a_jd"
    assert copy["message_vi"] and copy["message_en"]
    assert "upload_another" in copy["next_actions"]
