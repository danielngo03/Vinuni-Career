"""Unit tests for the deterministic JD bias/discrimination checker."""

from __future__ import annotations

from app.ai.safety.bias_detection import (
    CATEGORY_AGE,
    CATEGORY_APPEARANCE,
    CATEGORY_DISABILITY,
    CATEGORY_GENDER,
    RISK_HIGH,
    check_bias,
)


def test_clean_jd_has_no_findings():
    jd = (
        "We are hiring a Backend Engineer with 2+ years of experience in "
        "Python and PostgreSQL. Remote-friendly, competitive salary."
    )
    result = check_bias(jd)
    assert result.flagged is False
    assert result.requires_human_review is False
    assert result.findings == []


def test_empty_text_has_no_findings():
    result = check_bias("")
    assert result.flagged is False
    assert result.requires_human_review is False


def test_whitespace_only_text_has_no_findings():
    result = check_bias("   \n\t  ")
    assert result.flagged is False


def test_age_ceiling_vietnamese_flagged_medium():
    result = check_bias("Yêu cầu ứng viên dưới 30 tuổi, năng động.")
    categories = [f.category for f in result.findings]
    assert CATEGORY_AGE in categories
    assert result.requires_human_review is False  # medium risk, not high


def test_age_range_vietnamese_flagged():
    result = check_bias("Độ tuổi từ 22 đến 28 tuổi.")
    assert any(f.category == CATEGORY_AGE for f in result.findings)


def test_age_ceiling_english_flagged():
    result = check_bias("Candidates must be under the age of 30.")
    assert any(f.category == CATEGORY_AGE for f in result.findings)


def test_gender_only_vietnamese_flagged_high_and_requires_review():
    result = check_bias("Công ty chỉ tuyển nam cho vị trí kỹ sư.")
    genders = [f for f in result.findings if f.category == CATEGORY_GENDER]
    assert genders
    assert genders[0].risk_level == RISK_HIGH
    assert result.requires_human_review is True


def test_gender_only_english_flagged_high():
    result = check_bias("This role is open to males only.")
    assert any(
        f.category == CATEGORY_GENDER and f.risk_level == RISK_HIGH for f in result.findings
    )
    assert result.requires_human_review is True


def test_disability_exclusion_vietnamese_flagged_high():
    result = check_bias("Ứng viên phải không khuyết tật.")
    findings = [f for f in result.findings if f.category == CATEGORY_DISABILITY]
    assert findings
    assert findings[0].risk_level == RISK_HIGH
    assert result.requires_human_review is True


def test_disability_exclusion_english_flagged_high():
    result = check_bias("We require able-bodied only candidates for this warehouse role.")
    assert any(
        f.category == CATEGORY_DISABILITY and f.risk_level == RISK_HIGH for f in result.findings
    )


def test_marital_status_vietnamese_flagged_high():
    result = check_bias("Ưu tiên ứng viên chưa lập gia đình.")
    findings = [f for f in result.findings if f.category == CATEGORY_APPEARANCE]
    assert findings
    assert findings[0].risk_level == RISK_HIGH
    assert result.requires_human_review is True


def test_appearance_requirement_vietnamese_flagged_medium():
    result = check_bias("Ứng viên cần có ngoại hình ưa nhìn.")
    findings = [f for f in result.findings if f.category == CATEGORY_APPEARANCE]
    assert findings


def test_multiple_findings_are_all_reported():
    jd = "Chỉ tuyển nam, dưới 30 tuổi, không khuyết tật, ngoại hình ưa nhìn."
    result = check_bias(jd)
    categories = {f.category for f in result.findings}
    assert categories == {
        CATEGORY_GENDER,
        CATEGORY_AGE,
        CATEGORY_DISABILITY,
        CATEGORY_APPEARANCE,
    }
    assert result.requires_human_review is True


def test_as_dict_shape_is_json_serializable():
    import json

    result = check_bias("Chỉ tuyển nam.")
    payload = result.as_dict()
    # Must round-trip through json.dumps without error (API response contract).
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "flagged" in serialized
    assert payload["requires_human_review"] is True
    assert payload["findings"][0]["category"] == CATEGORY_GENDER


def test_advisory_only_never_raises_or_blocks():
    """check_bias must never raise — it's advisory, called on every JD save."""
    weird_inputs = [None, 12345, {"not": "a string"}]
    for bad_input in weird_inputs:
        try:
            result = check_bias(bad_input)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"check_bias must not raise on {bad_input!r}") from exc
        assert result.flagged is False
