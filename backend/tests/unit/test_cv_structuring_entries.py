"""Deterministic (vision-OFF) structuring emits entries + numeric skill levels.

B-599: when the vision tier is off, ``cv_structuring.structure_cv_text`` must still
produce the structured, matching-ready shape that ``vision._normalize`` produces —
career sections grouped into ``entries`` and skills/languages parsed into
``{name, level}`` items — WITHOUT dropping any content. These tests exercise
realistic Vietnamese + English CV text.
"""

from __future__ import annotations

from app.ai.extraction.cv_structuring import structure_cv_text

_CV_EN = (
    "Nguyen Van A\n"
    "Email: a@example.com | Phone: +84 900 111 222\n"
    "\n"
    "Summary\n"
    "Backend engineer intern focused on APIs.\n"
    "\n"
    "Experience\n"
    "Software Engineer Intern, Acme Corp (03/2023 - 08/2023)\n"
    "- Built REST APIs with FastAPI and PostgreSQL.\n"
    "- Reduced latency by 30%.\n"
    "Data Analyst, Beta Ltd (2021 - 2022)\n"
    "- Analysed sales data with Python and SQL.\n"
    "\n"
    "Education\n"
    "Bachelor of Computer Science, VinUniversity, 2020 - 2024\n"
    "\n"
    "Skills\n"
    "Python - 4/5\n"
    "FastAPI: 85%\n"
    "SQL ●●●○○\n"
    "\n"
    "Languages\n"
    "English - Fluent\n"
    "Vietnamese: Native\n"
)

_CV_VI = (
    "Trần Thị B\n"
    "Email: b@example.com\n"
    "\n"
    "Kinh nghiệm\n"
    "Điều dưỡng viên, Bệnh viện Nhi (04/2020 - Nay)\n"
    "- Chăm sóc bệnh nhân nhi khoa.\n"
    "- Hỗ trợ bác sĩ trong ca trực.\n"
    "\n"
    "Học vấn\n"
    "Cử nhân Điều dưỡng, Đại học Y Hà Nội, 2016 - 2020\n"
    "\n"
    "Kỹ năng\n"
    "Giao tiếp - 5/5\n"
    "Chăm sóc bệnh nhân ★★★★☆\n"
    "\n"
    "Ngoại ngữ\n"
    "Tiếng Anh: Khá\n"
)


def _all_text(extracted: dict) -> str:
    """Every human-readable string in the extraction, for content-loss checks."""
    parts: list[str] = []
    for value in extracted.values():
        if not isinstance(value, dict):
            continue
        for entry in value.get("entries", []) or []:
            parts += [str(entry.get(k) or "") for k in
                      ("heading", "subheading", "timeframe", "location", "note")]
            parts += [str(h) for h in entry.get("highlights", []) or []]
        for item in value.get("items", []) or []:
            parts += [str(item.get(k) or "") for k in ("text", "name", "level")]
        parts += [str(v) for v in value.values() if isinstance(v, str)]
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# English: entries + numeric skill levels                                     #
# --------------------------------------------------------------------------- #


def test_english_experience_grouped_into_entries() -> None:
    extracted = structure_cv_text(_CV_EN)["extracted_data"]
    entries = extracted["experience"]["entries"]
    assert len(entries) == 2

    first = entries[0]
    assert first["heading"] == "Software Engineer Intern"
    assert first["subheading"] == "Acme Corp"
    assert first["timeframe"] == "03/2023 - 08/2023"
    assert first["highlights"] == [
        "Built REST APIs with FastAPI and PostgreSQL.",
        "Reduced latency by 30%.",
    ]

    second = entries[1]
    assert second["heading"] == "Data Analyst"
    assert second["subheading"] == "Beta Ltd"
    assert second["timeframe"] == "2021 - 2022"
    assert second["highlights"] == ["Analysed sales data with Python and SQL."]


def test_english_education_is_one_entry_with_timeframe() -> None:
    extracted = structure_cv_text(_CV_EN)["extracted_data"]
    entries = extracted["education"]["entries"]
    assert len(entries) == 1
    assert entries[0]["timeframe"] == "2020 - 2024"
    # No bullet chars leak into any field.
    joined = entries[0]["heading"] + entries[0]["subheading"]
    assert "•" not in joined and "-" not in entries[0]["heading"][:1]
    assert "Computer Science" in joined and "VinUniversity" in joined


def test_english_skill_levels_are_numeric_0_100() -> None:
    extracted = structure_cv_text(_CV_EN)["extracted_data"]
    by_name = {it["name"]: it["level"] for it in extracted["skills"]["items"]}
    assert by_name == {"Python": 80, "FastAPI": 85, "SQL": 60}
    for level in by_name.values():
        assert isinstance(level, int) and 0 <= level <= 100


def test_english_languages_have_string_levels() -> None:
    extracted = structure_cv_text(_CV_EN)["extracted_data"]
    langs = {it["name"]: it["level"] for it in extracted["languages"]["items"]}
    assert langs == {"English": "Fluent", "Vietnamese": "Native"}


def test_english_no_content_dropped() -> None:
    extracted = structure_cv_text(_CV_EN)["extracted_data"]
    blob = _all_text(extracted)
    for token in (
        "Software Engineer Intern", "Acme Corp", "Reduced latency",
        "Data Analyst", "Beta Ltd", "Analysed sales data",
        "Computer Science", "VinUniversity", "Python", "FastAPI", "SQL",
        "English", "Vietnamese",
    ):
        assert token in blob, f"lost content: {token}"


# --------------------------------------------------------------------------- #
# Vietnamese: entries + levels (stars, ratio, ongoing "Nay")                   #
# --------------------------------------------------------------------------- #


def test_vietnamese_experience_entry_with_ongoing_timeframe() -> None:
    extracted = structure_cv_text(_CV_VI)["extracted_data"]
    entries = extracted["experience"]["entries"]
    assert len(entries) == 1
    e = entries[0]
    assert e["heading"] == "Điều dưỡng viên"
    assert e["subheading"] == "Bệnh viện Nhi"
    assert e["timeframe"] == "04/2020 - Nay"
    assert e["highlights"] == [
        "Chăm sóc bệnh nhân nhi khoa.",
        "Hỗ trợ bác sĩ trong ca trực.",
    ]


def test_vietnamese_skill_levels_ratio_and_stars() -> None:
    extracted = structure_cv_text(_CV_VI)["extracted_data"]
    by_name = {it["name"]: it["level"] for it in extracted["skills"]["items"]}
    assert by_name["Giao tiếp"] == 100  # 5/5
    assert by_name["Chăm sóc bệnh nhân"] == 80  # 4 of 5 stars
    for level in by_name.values():
        assert isinstance(level, int) and 0 <= level <= 100


def test_vietnamese_no_content_dropped() -> None:
    extracted = structure_cv_text(_CV_VI)["extracted_data"]
    blob = _all_text(extracted)
    for token in (
        "Điều dưỡng viên", "Bệnh viện Nhi", "Chăm sóc bệnh nhân nhi khoa",
        "Hỗ trợ bác sĩ", "Điều dưỡng", "Đại học Y Hà Nội", "Giao tiếp", "Tiếng Anh",
    ):
        assert token in blob, f"lost content: {token}"


# --------------------------------------------------------------------------- #
# Percent + bar variants                                                       #
# --------------------------------------------------------------------------- #


def test_skill_level_percent_and_bar_variants() -> None:
    text = (
        "Skills\n"
        "Docker: 90%\n"
        "Kubernetes ●●●●●\n"
        "Terraform ▮▮▯▯▯\n"
        "Go, Rust, C++\n"
    )
    items = structure_cv_text(text)["extracted_data"]["skills"]["items"]
    by_name = {it["name"]: it["level"] for it in items}
    assert by_name["Docker"] == 90
    assert by_name["Kubernetes"] == 100
    assert by_name["Terraform"] == 40  # 2 of 5 filled bars
    # A level-less comma list is split into individual named skills (level None).
    assert by_name["Go"] is None and by_name["Rust"] is None and by_name["C++"] is None
