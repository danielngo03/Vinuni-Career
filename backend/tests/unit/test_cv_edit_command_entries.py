"""Deterministic entry-section ops for the natural-language CV edit command (B-595).

``edit_command._apply_operations`` must let a student edit ENTRY-based sections
(experience/education/projects — one entry per role/degree with separate
heading/subheading/timeframe/highlights) via the same validated, pending-diff
pipeline as item sections. These unit tests drive the deterministic applier
directly (the model layer is validated separately) and assert:

- entry field / highlight edits, reorder, and highlight add/remove all produce a
  correct before/after diff against the ``entries`` shape;
- the source sections are NEVER mutated (before == original);
- malformed / out-of-range ops are silently dropped (no crash, non-applicable).
"""

from __future__ import annotations

from app.ai.cv.edit_command import _apply_operations


def _sections() -> list[dict]:
    return [
        {
            "section_id": "s1",
            "section_type": "experience",
            "title": "Experience",
            "sort_order": 30,
            "content": {
                "entries": [
                    {
                        "heading": "Intern",
                        "subheading": "Acme",
                        "timeframe": "2023",
                        "location": "",
                        "note": "",
                        "highlights": ["Did X", "Did Y"],
                    },
                    {
                        "heading": "Analyst",
                        "subheading": "Beta",
                        "timeframe": "2022",
                        "location": "",
                        "note": "",
                        "highlights": ["Did Z"],
                    },
                ]
            },
        },
    ]


def _after_entries(after: dict) -> list[dict]:
    return after["sections"][0]["content"]["entries"]


def test_update_highlight_produces_entry_diff() -> None:
    before, after, has_text = _apply_operations(
        _sections(),
        [
            {
                "op": "update_highlight",
                "section_type": "experience",
                "entry_index": 0,
                "highlight_index": 1,
                "text": "Improved Y by 20%",
            }
        ],
    )
    assert has_text is True
    entries = _after_entries(after)
    assert entries[0]["highlights"] == ["Did X", "Improved Y by 20%"]
    assert entries[1]["highlights"] == ["Did Z"]  # untouched
    # The source is never mutated before accept.
    assert before["sections"][0]["content"]["entries"][0]["highlights"] == ["Did X", "Did Y"]


def test_update_entry_field_preserves_other_fields() -> None:
    _before, after, has_text = _apply_operations(
        _sections(),
        [
            {
                "op": "update_entry_field",
                "section_type": "experience",
                "entry_index": 0,
                "field": "heading",
                "text": "Software Engineer Intern",
            }
        ],
    )
    assert has_text is True
    entry = _after_entries(after)[0]
    assert entry["heading"] == "Software Engineer Intern"
    assert entry["subheading"] == "Acme" and entry["timeframe"] == "2023"
    assert entry["highlights"] == ["Did X", "Did Y"]


def test_add_and_remove_highlight() -> None:
    _b, after_add, has_text = _apply_operations(
        _sections(),
        [
            {
                "op": "add_highlight",
                "section_type": "experience",
                "entry_index": 1,
                "text": "Led a data project",
            }
        ],
    )
    assert has_text is True
    assert _after_entries(after_add)[1]["highlights"] == ["Did Z", "Led a data project"]

    _b2, after_rm, has_text2 = _apply_operations(
        _sections(),
        [
            {
                "op": "remove_highlight",
                "section_type": "experience",
                "entry_index": 0,
                "highlight_index": 0,
            }
        ],
    )
    # Structural change (no new prose) -> not flagged for the fabrication check.
    assert has_text2 is False
    assert _after_entries(after_rm)[0]["highlights"] == ["Did Y"]


def test_reorder_entries() -> None:
    _b, after, has_text = _apply_operations(
        _sections(),
        [{"op": "reorder_entries", "section_type": "experience", "order": [1, 0]}],
    )
    assert has_text is False
    headings = [e["heading"] for e in _after_entries(after)]
    assert headings == ["Analyst", "Intern"]


def test_malformed_entry_ops_are_dropped() -> None:
    before, after, has_text = _apply_operations(
        _sections(),
        [
            # entry index out of range
            {
                "op": "update_highlight",
                "section_type": "experience",
                "entry_index": 9,
                "highlight_index": 0,
                "text": "x",
            },
            # highlights is not an updatable field
            {
                "op": "update_entry_field",
                "section_type": "experience",
                "entry_index": 0,
                "field": "highlights",
                "text": "x",
            },
            # duplicate index in reorder
            {"op": "reorder_entries", "section_type": "experience", "order": [0, 0]},
            # empty text
            {"op": "add_highlight", "section_type": "experience", "entry_index": 0, "text": "   "},
        ],
    )
    assert after["sections"] == []
    assert before["sections"] == []
    assert has_text is False


def test_entry_op_on_missing_section_is_dropped() -> None:
    _b, after, has_text = _apply_operations(
        _sections(),
        [{"op": "add_highlight", "section_type": "projects", "entry_index": 0, "text": "injected"}],
    )
    assert after["sections"] == []
    assert has_text is False
