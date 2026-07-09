"""render_cv_pdf must render the real structured CV content model.

Regression for the broken exporter that only understood ``{"items": [...]}`` /
flat dicts: it dropped ``entries``-shaped experience/education entirely, printed
the contact header as ``name: X`` key:value lines, and rendered skills as
``level: 85``. These tests assert the pure ``build_render_model`` step binds the
same content the frontend ``<CvDocument/>`` renders, plus a render smoke test.
"""

from __future__ import annotations

from app.modules.documents.infrastructure.pdf_render import (
    build_render_model,
    render_cv_pdf,
)


def _rich_snapshot() -> dict:
    return {
        "title": "My Backend CV",
        "canvas": {},
        "sections": [
            {
                "id": "h",
                "section_type": "header",
                "title": "Header",
                "sort_order": 5,
                "is_visible": True,
                "content_json": {
                    "name": "Nguyen Van A",
                    "headline": "Backend Engineer",
                    "email": "a@vinuni.edu.vn",
                    "phone": "0324xx0898",
                    "location": "Hanoi",
                    "links": [{"label": "github.com/a", "url": "https://github.com/a"}],
                },
            },
            {
                "id": "sm",
                "section_type": "summary",
                "title": "Summary",
                "sort_order": 8,
                "is_visible": True,
                "content_json": {"items": [{"text": "Backend-focused CS student."}]},
            },
            {
                "id": "e",
                "section_type": "experience",
                "title": "Experience",
                "sort_order": 10,
                "is_visible": True,
                "content_json": {
                    "entries": [
                        {
                            "heading": "Backend Intern",
                            "subheading": "Acme Co.",
                            "timeframe": "2024 - 2025",
                            "location": "Remote",
                            "highlights": [
                                "Built a FastAPI service handling 1k rps",
                                "Cut p95 latency 30%",
                            ],
                        }
                    ]
                },
            },
            {
                "id": "ed",
                "section_type": "education",
                "title": "Education",
                "sort_order": 20,
                "is_visible": True,
                "content_json": {
                    "entries": [
                        {
                            "heading": "BSc Computer Science",
                            "subheading": "VinUniversity",
                            "timeframe": "2021 - 2025",
                        }
                    ]
                },
            },
            {
                "id": "sk",
                "section_type": "skills",
                "title": "Skills",
                "sort_order": 30,
                "is_visible": True,
                "content_json": {
                    "items": [{"name": "Python", "level": 90}, {"name": "FastAPI", "level": 80}]
                },
            },
            {
                "id": "lg",
                "section_type": "languages",
                "title": "Languages",
                "sort_order": 40,
                "is_visible": True,
                "content_json": {
                    "items": [
                        {"name": "English", "level": "Fluent"},
                        {"name": "Vietnamese", "level": "Native"},
                    ]
                },
            },
            {
                "id": "empty",
                "section_type": "awards",
                "title": "Awards",
                "sort_order": 50,
                "is_visible": True,
                "content_json": {},
            },
            {
                "id": "div",
                "section_type": "custom",
                "title": "",
                "sort_order": 60,
                "is_visible": True,
                "content_json": {"divider": True},
            },
        ],
    }


def _headings(model: list[dict]) -> list[str]:
    return [b["text"] for b in model if b["type"] == "heading"]


def _first(model: list[dict], kind: str) -> dict:
    return next(b for b in model if b["type"] == kind)


def test_header_binds_name_headline_and_contact() -> None:
    model = build_render_model(_rich_snapshot())
    header = model[0]
    assert header["type"] == "header"
    assert header["name"] == "Nguyen Van A"
    assert header["headline"] == "Backend Engineer"
    # Contact is a clean list of values — NOT "email: ..." key:value lines.
    assert "a@vinuni.edu.vn" in header["contact"]
    assert "0324xx0898" in header["contact"]
    assert "Hanoi" in header["contact"]
    assert "github.com/a" in header["contact"]


def test_experience_and_education_entries_are_not_dropped() -> None:
    """The core regression: entries-shaped sections used to render blank."""
    model = build_render_model(_rich_snapshot())
    assert "Experience" in _headings(model)
    assert "Education" in _headings(model)

    entries_blocks = [b for b in model if b["type"] == "entries"]
    all_headings = [e["heading"] for b in entries_blocks for e in b["entries"]]
    assert "Backend Intern" in all_headings
    assert "BSc Computer Science" in all_headings

    highlights = [h for b in entries_blocks for e in b["entries"] for h in e["highlights"]]
    assert "Built a FastAPI service handling 1k rps" in highlights
    assert "Cut p95 latency 30%" in highlights


def test_skills_carry_numeric_levels_and_languages_carry_string_levels() -> None:
    model = build_render_model(_rich_snapshot())
    skills = _first(model, "skills")["items"]
    assert {s["name"] for s in skills} == {"Python", "FastAPI"}
    assert all(isinstance(s["level"], int) for s in skills)

    languages = _first(model, "languages")["items"]
    assert {lang["name"] for lang in languages} == {"English", "Vietnamese"}
    assert {lang["level"] for lang in languages} == {"Fluent", "Native"}


def test_summary_text_and_divider_render() -> None:
    model = build_render_model(_rich_snapshot())
    assert "Summary" in _headings(model)
    text_block = _first(model, "text")
    assert "Backend-focused CS student." in text_block["bullets"]
    assert any(b["type"] == "divider" for b in model)


def test_empty_section_is_dropped_no_orphan_heading() -> None:
    model = build_render_model(_rich_snapshot())
    # "Awards" section had empty content_json -> no heading, no body.
    assert "Awards" not in _headings(model)


def test_header_name_falls_back_to_cv_title_when_no_header_section() -> None:
    snapshot = {
        "title": "Data Analyst CV",
        "canvas": {},
        "sections": [
            {
                "id": "sk",
                "section_type": "skills",
                "title": "Skills",
                "sort_order": 10,
                "is_visible": True,
                "content_json": {"items": [{"name": "SQL", "level": 70}]},
            }
        ],
    }
    model = build_render_model(snapshot)
    assert model[0]["type"] == "header"
    assert model[0]["name"] == "Data Analyst CV"


def test_render_produces_valid_pdf_bytes() -> None:
    pdf = render_cv_pdf(_rich_snapshot())
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 800


def test_render_watermarked_pdf_bytes() -> None:
    pdf = render_cv_pdf(_rich_snapshot(), watermark="VinUni · partner@acme.co")
    assert pdf[:4] == b"%PDF"


def test_render_minimal_snapshot_does_not_crash() -> None:
    pdf = render_cv_pdf({"title": "Empty", "sections": [], "canvas": {}})
    assert pdf[:4] == b"%PDF"
