"""render_cv_pdf must honor canvas block order/visibility over raw sort_order.

Covers the render-consistency gap flagged in ADR-0015: canvas blocks can be
reordered/hidden independently of a section's own sort_order/is_visible, and
the exported PDF must reflect what the student arranged on the canvas.
"""

from __future__ import annotations

from app.modules.documents.infrastructure.pdf_render import _ordered_visible_sections


def _section(section_id: str, *, sort_order: int, visible: bool = True, title: str) -> dict:
    return {
        "id": section_id,
        "section_type": "custom",
        "title": title,
        "sort_order": sort_order,
        "content_json": {},
        "is_visible": visible,
    }


def test_canvas_block_order_overrides_section_sort_order() -> None:
    snapshot = {
        "sections": [
            _section("s1", sort_order=0, title="First by sort_order"),
            _section("s2", sort_order=1, title="Second by sort_order"),
        ],
        "canvas": {
            "blocks": [
                {"id": "b1", "section_id": "s1", "order": 5, "visible": True},
                {"id": "b2", "section_id": "s2", "order": 0, "visible": True},
            ]
        },
    }

    ordered = _ordered_visible_sections(snapshot)

    assert [s["title"] for s in ordered] == ["Second by sort_order", "First by sort_order"]


def test_canvas_block_visibility_overrides_section_is_visible() -> None:
    snapshot = {
        "sections": [
            _section("s1", sort_order=0, visible=True, title="Hidden via canvas"),
            _section("s2", sort_order=1, visible=False, title="Shown via canvas"),
        ],
        "canvas": {
            "blocks": [
                {"id": "b1", "section_id": "s1", "order": 0, "visible": False},
                {"id": "b2", "section_id": "s2", "order": 1, "visible": True},
            ]
        },
    }

    ordered = _ordered_visible_sections(snapshot)

    assert [s["title"] for s in ordered] == ["Shown via canvas"]


def test_section_without_matching_block_falls_back_to_its_own_fields() -> None:
    snapshot = {
        "sections": [
            _section("s1", sort_order=0, title="No block"),
            _section("s2", sort_order=1, visible=False, title="Hidden, no block"),
        ],
        "canvas": {"blocks": []},
    }

    ordered = _ordered_visible_sections(snapshot)

    assert [s["title"] for s in ordered] == ["No block"]


def test_empty_canvas_json_matches_legacy_behavior() -> None:
    snapshot = {
        "sections": [
            _section("s1", sort_order=1, title="Second"),
            _section("s2", sort_order=0, title="First"),
        ],
        "canvas": {},
    }

    ordered = _ordered_visible_sections(snapshot)

    assert [s["title"] for s in ordered] == ["First", "Second"]
