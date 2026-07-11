"""Unit tests for vision-tier output normalisation into the STRUCTURED shape.

Pure/offline — no network, no real model calls. They lock the contract that the
model's raw output is never trusted verbatim and is coerced into clean, structured
CV data: entry sections become ``{"entries": [{heading, subheading, timeframe,
location, note, highlights[]}]}`` with NO bullet characters, skills become
``{"items": [{name, level}]}`` with integer levels, and only allowlisted keys/text
survive.
"""

from __future__ import annotations

from app.ai.extraction.adapters import vision


def _cv() -> dict:
    return {
        "is_cv": True,
        "detected_language": "vi",
        "contact": {
            "name": "Trần Anh Huy",
            "headline": "Security Operation",
            "email": "huytran@gmail.com",
            "phone": "(+84) 869 663 449",
            "ssn": "drop-me",  # not allowlisted
        },
        "summary": ["Chuyên gia IT.", "Hiểu biết chuyên sâu."],
        "experience": [
            {
                "role": "Security Operation",
                "organization": "FreeC Asia",
                "location": "Hồ Chí Minh",
                "start": "2018",
                "end": "2021",
                "highlights": ["• Theo dõi hệ thống", "- Điều tra sự cố"],
            }
        ],
        "education": [
            {
                "degree": "Cử nhân CNTT",
                "school": "Đại học FPT",
                "start": "2014",
                "end": "2018",
                "gpa": "3,64",
            }
        ],
        "skills": [
            {"name": "McAfee SIEM", "level": 85},
            {"name": "FireEye", "level": "80%"},
            {"name": "Linux", "level": None},
        ],
        "interests": ["Đọc sách"],
        "junk_section": [{"whatever": 1}],
    }


def test_normalize_builds_structured_entries() -> None:
    result = vision._normalize(_cv())
    assert result is not None
    d = result["extracted_data"]

    # Contact keeps headline; drops non-allowlisted keys.
    assert d["contact"] == {
        "name": "Trần Anh Huy",
        "headline": "Security Operation",
        "email": "huytran@gmail.com",
        "phone": "(+84) 869 663 449",
    }

    # Experience is a structured entry with separate fields and NO bullet chars.
    exp = d["experience"]["entries"][0]
    assert exp["heading"] == "Security Operation"
    assert exp["subheading"] == "FreeC Asia"
    assert exp["timeframe"] == "2018 - 2021"
    assert exp["location"] == "Hồ Chí Minh"
    assert exp["highlights"] == ["Theo dõi hệ thống", "Điều tra sự cố"]
    assert all("•" not in h and not h.startswith("-") for h in exp["highlights"])

    # Education carries GPA in its own note field.
    edu = d["education"]["entries"][0]
    assert edu["heading"] == "Cử nhân CNTT"
    assert edu["subheading"] == "Đại học FPT"
    assert edu["timeframe"] == "2014 - 2018"
    assert edu["note"] == "GPA: 3,64"

    # Skills carry integer levels (percent as-is; "80%" -> 80; missing -> None).
    assert d["skills"]["items"] == [
        {"name": "McAfee SIEM", "level": 85},
        {"name": "FireEye", "level": 80},
        {"name": "Linux", "level": None},
    ]

    # Summary + interests are text items; unknown sections are dropped.
    assert [i["text"] for i in d["summary"]["items"]] == ["Chuyên gia IT.", "Hiểu biết chuyên sâu."]
    assert d["interests"]["items"] == [{"text": "Đọc sách"}]
    assert "junk_section" not in d

    # No manual review step -> no review_fields emitted.
    assert result["review_fields"] == []
    assert result["detected_language"] == "vi"


def test_normalize_rejects_non_cv() -> None:
    assert vision._normalize({"is_cv": False, "contact": {"name": "X"}}) is None


def test_normalize_rejects_empty_result() -> None:
    assert vision._normalize({"contact": {}, "summary": [], "experience": []}) is None


def test_normalize_infers_language_when_missing() -> None:
    parsed = {
        "contact": {"name": "Trần Văn A"},
        "experience": [
            {"role": "Kỹ sư", "organization": "Công ty", "highlights": ["Giao tiếp tốt"]}
        ],
    }
    result = vision._normalize(parsed)
    assert result is not None
    assert result["detected_language"] == "vi"


def test_normalize_drops_entry_with_no_signal() -> None:
    # An entry with no heading and no highlights is dropped, not stored empty.
    parsed = {"contact": {"name": "A"}, "experience": [{"location": "HN"}]}
    result = vision._normalize(parsed)
    assert result is not None
    assert "experience" not in result["extracted_data"]


def test_extract_json_handles_fenced_and_loose() -> None:
    assert vision._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert vision._extract_json('prefix {"a": 2} suffix') == {"a": 2}
    assert vision._extract_json("no json here") is None
