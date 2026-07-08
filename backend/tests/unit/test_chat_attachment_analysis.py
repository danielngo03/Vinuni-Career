"""Offline unit tests for the university chat-attachment data-analysis contract.

Pure/deterministic — no DB, no network, no real LLM. Locks:

- the cost-tiered cascade never fabricates for blank / unsupported / junk files
  and marks them non-chargeable (energy is only debited on a genuine analysis);
- the leakage-safe DATA-ANALYSIS shape the frontend renders (``tables`` +
  render-ready ``charts`` + ``insights``), including the exact chart-spec keys and
  the column-vs-line default that matches the owner's "vẽ cột" ask.
"""

from __future__ import annotations

from app.ai.extraction import attachment as a
from app.ai.extraction import data_analysis as da

_VALID_CHART_TYPES = {"bar", "column", "line", "pie"}


def _analyze(filename: str, data: bytes):
    return a.analyze_document(filename, data, policy=a.resolve_policy())


def test_csv_produces_tables_charts_insights() -> None:
    csv = b"Month,Applications,Hires\nJan,120,8\nFeb,150,11\nMar,98,6\nApr,175,14"
    outcome = _analyze("cohort.csv", csv)
    assert outcome.status == "analyzed"
    assert outcome.analyzed is True
    assert outcome.chargeable is True
    assert outcome.vision_used is False  # native text tier, cheap

    derived = da.build_data_analysis(outcome)

    # One detected table with header + rows.
    assert derived["tables"], "expected a detected table"
    table = derived["tables"][0]
    assert table["columns"] == ["Month", "Applications", "Hires"]
    assert len(table["rows"]) == 4

    # Two numeric columns -> two charts; insights summarise each.
    assert len(derived["charts"]) == 2
    assert any("Applications: total 543" in s for s in derived["insights"])


def test_chart_spec_shape_is_render_ready() -> None:
    csv = b"Department,Headcount\nEngineering,42\nSales,17\nMarketing,9\nOps,23"
    derived = da.build_data_analysis(_analyze("dept.csv", csv))
    assert derived["charts"]
    for chart in derived["charts"]:
        assert chart["type"] in _VALID_CHART_TYPES
        assert isinstance(chart["title"], str) and chart["title"]
        assert chart["x_label"] and chart["y_label"]
        assert chart["series"], "chart must carry at least one series"
        for series in chart["series"]:
            assert isinstance(series["label"], str)
            assert series["points"], "series must carry points"
            for point in series["points"]:
                assert set(point.keys()) == {"x", "y"}
                assert isinstance(point["y"], int | float)


def test_categorical_axis_defaults_to_column_plus_pie() -> None:
    # Category labels (department names) -> a column chart, and because it is a
    # single non-negative value series over a small set, also a pie.
    csv = b"Department,Headcount\nEngineering,42\nSales,17\nMarketing,9\nOps,23"
    types = [c["type"] for c in da.build_data_analysis(_analyze("d.csv", csv))["charts"]]
    assert types[0] == "column"
    assert "pie" in types


def test_numeric_sequence_axis_uses_line() -> None:
    csv = b"Year,Placements\n2020,110\n2021,140\n2022,175\n2023,210"
    types = [c["type"] for c in da.build_data_analysis(_analyze("yr.csv", csv))["charts"]]
    assert types and all(t == "line" for t in types)


def test_table_without_numeric_column_yields_no_chart() -> None:
    # A non-numeric table must never be coerced into a fabricated chart.
    csv = b"Name,Role\nAn,Advisor\nBinh,Counselor\nChi,Coordinator"
    derived = da.build_data_analysis(_analyze("people.csv", csv))
    assert derived["tables"], "table should still be detected"
    assert derived["charts"] == []


def test_blank_file_not_analyzable_and_not_chargeable() -> None:
    outcome = _analyze("empty.txt", b"   \n  ")
    assert outcome.status == "not_analyzable"
    assert outcome.chargeable is False
    derived = da.build_data_analysis(outcome)
    assert derived == {"tables": [], "charts": [], "insights": []}


def test_empty_bytes_not_chargeable() -> None:
    outcome = _analyze("x.pdf", b"")
    assert outcome.chargeable is False


def test_unsupported_type_not_chargeable() -> None:
    outcome = _analyze("archive.zip", b"PK\x03\x04 not a real archive")
    assert outcome.analyzed is False
    assert outcome.chargeable is False


def test_key_values_surface_as_a_details_table() -> None:
    txt = b"Report: Q1 Outcomes\nOwner: Career Services\nStatus: Final\nPrepared: 2026-01"
    derived = da.build_data_analysis(_analyze("meta.txt", txt))
    titles = [t["title"] for t in derived["tables"]]
    assert "Key details" in titles
