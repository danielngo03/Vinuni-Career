from app.ai.extraction.jd.schema import (
    EXPECTED_KEYS,
    default_candidate_requirements,
    validate_and_score,
)


def test_defaults_requirement_groups_to_not_required():
    cr = default_candidate_requirements()
    assert cr["gender"]["mode"] == "not_required"
    assert cr["age"]["mode"] == "not_required"
    assert cr["marital_status"]["mode"] == "not_required"
    assert cr["languages"] == []
    assert cr["certifications"] == []


def test_extracts_new_structured_fields():
    structured = {
        "title": "Kỹ sư phần mềm",
        "salary_mode": "range",
        "salary_min": 20000000,
        "salary_max": 30000000,
        "salary_period": "monthly",
        "salary_gross_net": "gross",
        "experience_mode": "min",
        "experience_min_years": 2,
        "seniority_level": "junior",
        "application_deadline": "2026-08-31",
        "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}},
    }
    raw = "Kỹ sư phần mềm, lương 20-30 triệu gross/tháng, tối thiểu 2 năm, chỉ tuyển nữ."
    validated, conf = validate_and_score(structured, raw)
    assert validated["salary_mode"] == "range"
    assert validated["experience_mode"] == "min"
    assert validated["candidate_requirements"]["gender"]["mode"] == "required"
    # absent groups defaulted to not_required
    assert validated["candidate_requirements"]["marital_status"]["mode"] == "not_required"
    # normalized/interpreted fields always flagged for review
    assert conf["salary_min"]["needs_review"] is True
    assert conf["candidate_requirements"]["needs_review"] is True


def test_invalid_enum_field_is_dropped_not_fatal():
    structured = {"title": "X", "employment_type": "banana", "required_skills": ["Python"]}
    validated, conf = validate_and_score(structured, "X Python full time")
    assert validated.get("employment_type") in (None, "")
    assert "Python" in validated["required_skills"]


def test_expected_keys_include_new_fields():
    for k in (
        "salary_mode",
        "experience_mode",
        "seniority_level",
        "industry",
        "application_deadline",
        "candidate_requirements",
    ):
        assert k in EXPECTED_KEYS
