"""Unit tests for the deterministic content-policy scanner."""

from __future__ import annotations

from app.ai.safety.content_moderation import (
    CATEGORY_ADULT,
    CATEGORY_EARNINGS,
    CATEGORY_FEE,
    CATEGORY_OFF_PLATFORM,
    CATEGORY_PYRAMID,
    check_content,
)


class TestFeeCollection:
    def test_vietnamese_fee_phrases_are_high_risk(self) -> None:
        result = check_content("Vui lòng nộp phí hồ sơ 200k trước khi phỏng vấn.")
        assert result.flagged
        assert result.policy_violation
        assert {f.category for f in result.findings} == {CATEGORY_FEE}

    def test_deposit_is_high_risk(self) -> None:
        assert check_content("Yêu cầu đặt cọc 500k.").policy_violation

    def test_english_training_fee_is_high_risk(self) -> None:
        result = check_content("A training fee of $50 must be paid upfront.")
        assert result.policy_violation
        assert result.findings[0].category == CATEGORY_FEE


class TestPyramidAndEarnings:
    def test_mlm_vietnamese(self) -> None:
        result = check_content("Cơ hội kinh doanh đa cấp cho sinh viên.")
        assert result.policy_violation
        assert result.findings[0].category == CATEGORY_PYRAMID

    def test_viec_nhe_luong_cao_is_high(self) -> None:
        result = check_content("Việc nhẹ lương cao làm tại nhà.")
        assert result.policy_violation
        assert result.findings[0].category == CATEGORY_EARNINGS

    def test_thu_nhap_khung_is_medium_not_violation(self) -> None:
        result = check_content("Thu nhập khủng tới 50 triệu.")
        assert result.flagged
        assert not result.policy_violation


class TestOffPlatformAndAdult:
    def test_zalo_pressure_is_medium(self) -> None:
        result = check_content("Nhắn tin qua Zalo trước để được nhận việc.")
        assert result.flagged
        assert not result.policy_violation
        assert result.findings[0].category == CATEGORY_OFF_PLATFORM

    def test_adult_content_is_high(self) -> None:
        result = check_content("Hiring for adult entertainment venues.")
        assert result.policy_violation
        assert result.findings[0].category == CATEGORY_ADULT


class TestRobustness:
    def test_clean_text_not_flagged(self) -> None:
        result = check_content("Tuyển kỹ sư Python, 2 năm kinh nghiệm, lương 20-25tr.")
        assert not result.flagged
        assert result.as_dict() == {
            "flagged": False,
            "policy_violation": False,
            "findings": [],
        }

    def test_empty_and_non_string_inputs_never_raise(self) -> None:
        for garbage in ("", "   ", None, 123, ["nộp", "phí"], {"x": 1}):
            result = check_content(garbage)  # type: ignore[arg-type]
            assert not result.flagged

    def test_matched_phrase_is_bounded_no_pii_capture(self) -> None:
        text = "Liên hệ 0987654321. Vui lòng nộp phí hồ sơ trước."
        result = check_content(text)
        assert result.flagged
        for finding in result.findings:
            assert "0987654321" not in finding.matched_phrase

    def test_uppercase_evasion_still_caught(self) -> None:
        assert check_content("NỘP PHÍ GIỮ CHỖ NGAY").policy_violation
