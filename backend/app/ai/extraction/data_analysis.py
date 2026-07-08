"""Deterministic data-analysis layer over a chat-attachment analysis.

Turns the generic :class:`~app.ai.extraction.attachment.AttachmentAnalysis`
(``table`` + ``key_values`` + ``summary`` + preview) into a compact,
render-ready result the university assistant can present as the owner asked —
"upload file/ảnh → vẽ bảng, vẽ cột, phân tích" (draw tables, draw columns,
analyse):

- ``tables``  — a list of ``{title, columns, rows}`` tables (the detected/vision
  table, plus a key/value table when present).
- ``charts``  — a list of compact chart SPECS the frontend draws itself (no chart
  library on the backend). Each spec is
  ``{type, title, series:[{label, points:[{x, y}]}], x_label, y_label}`` with
  ``type`` in ``{"bar", "column", "line", "pie"}``.
- ``insights`` — deterministic, factual bullets (row count, and per numeric
  column: total / min / max / average).

Everything here is OFFLINE and deterministic: it never calls a model, never
fabricates data, and only ever derives from cells that are actually present. A
non-tabular / blank analysis simply yields empty ``tables``/``charts`` and the
assistant falls back to the text summary.
"""

from __future__ import annotations

import re
from typing import Any

# Caps so a hostile/huge attachment can never blow up the chat payload.
_MAX_TABLES = 3
_MAX_CHARTS = 4
_MAX_POINTS = 24
_MAX_NUMERIC_SERIES = 3
_MAX_INSIGHTS = 6
_NUMERIC_COLUMN_MIN_RATIO = 0.6  # ≥60% of a column's cells must parse as numbers
_PIE_MAX_SLICES = 8

_NUMBER_RE = re.compile(r"^[+-]?\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?%?$|^[+-]?\d+(?:\.\d+)?%?$")
_CURRENCY_STRIP = str.maketrans({"$": "", "₫": "", "€": "", "£": "", ",": "", " ": ""})


def _to_number(cell: str) -> float | None:
    """Parse a cell into a number, or ``None``. Never fabricates.

    Handles thousands separators, a trailing ``%`` (kept as the bare value), and a
    leading currency symbol. Rejects anything else (returns ``None``).
    """

    if not isinstance(cell, str):
        return None
    raw = cell.strip()
    if not raw or not _NUMBER_RE.match(raw):
        return None
    cleaned = raw.translate(_CURRENCY_STRIP).rstrip("%")
    if cleaned in ("", "+", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _num_out(value: float) -> float | int:
    """Render a number compactly: an int when integral, else rounded float."""

    if value == int(value):
        return int(value)
    return round(value, 4)


def _looks_numeric_sequence(labels: list[str]) -> bool:
    """Whether the label axis is a strictly-increasing numeric sequence (→ line).

    A continuous numeric x-axis (e.g. 2019, 2020, 2021 or 1..N) reads better as a
    line/trend. Everything categorical — including month/quarter NAMES — stays a
    column chart, matching the owner's "vẽ cột" (draw columns) default.
    """

    non_empty = [x for x in labels if x.strip()]
    if len(non_empty) < 3:
        return False
    nums = [_to_number(x) for x in non_empty]
    clean = [n for n in nums if n is not None]
    if len(clean) != len(nums):
        return False
    return all(clean[i] < clean[i + 1] for i in range(len(clean) - 1))


def _column_cells(rows: list[list[str]], idx: int) -> list[str]:
    return [row[idx] if idx < len(row) else "" for row in rows]


def _is_numeric_column(cells: list[str]) -> bool:
    non_empty = [c for c in cells if isinstance(c, str) and c.strip()]
    if len(non_empty) < 2:
        return False
    parsed = sum(1 for c in non_empty if _to_number(c) is not None)
    return parsed / len(non_empty) >= _NUMERIC_COLUMN_MIN_RATIO


def _clip_table(table: dict) -> dict:
    columns = [str(c) for c in (table.get("columns") or [])]
    rows = [
        [str(c) for c in row]
        for row in (table.get("rows") or [])
        if isinstance(row, list)
    ]
    return {"columns": columns, "rows": rows}


def _charts_from_table(columns: list[str], rows: list[list[str]]) -> tuple[list[dict], list[str]]:
    """Build render-ready chart specs + factual insights from one table.

    Picks the first non-numeric column as the category/label axis and each
    subsequent numeric column as a value series. No numeric column → no chart.
    """

    if not columns or not rows:
        return [], []

    # Identify numeric columns vs the label (category) column.
    numeric_idx = [i for i in range(len(columns)) if _is_numeric_column(_column_cells(rows, i))]
    if not numeric_idx:
        return [], []
    label_idx = next((i for i in range(len(columns)) if i not in numeric_idx), None)
    if label_idx is None:
        # All columns numeric: use the row index as the category axis.
        labels = [str(i + 1) for i in range(len(rows))]
        label_name = "Row"
    else:
        labels = [str(c).strip() for c in _column_cells(rows, label_idx)]
        label_name = columns[label_idx] or "Category"

    base_type = "line" if _looks_numeric_sequence(labels) else "column"

    charts: list[dict] = []
    insights: list[str] = []
    for order, ci in enumerate(numeric_idx[:_MAX_NUMERIC_SERIES]):
        y_name = columns[ci] or f"Value {order + 1}"
        points: list[dict] = []
        values: list[float] = []
        for lbl, raw in zip(labels, _column_cells(rows, ci), strict=False):
            num = _to_number(raw)
            if num is None or not lbl:
                continue
            points.append({"x": lbl, "y": _num_out(num)})
            values.append(num)
            if len(points) >= _MAX_POINTS:
                break
        if not points:
            continue
        charts.append(
            {
                "type": base_type,
                "title": f"{y_name} by {label_name}",
                "series": [{"label": y_name, "points": points}],
                "x_label": label_name,
                "y_label": y_name,
            }
        )
        total = sum(values)
        insights.append(
            f"{y_name}: total {_num_out(total)}, min {_num_out(min(values))}, "
            f"max {_num_out(max(values))}, average {_num_out(round(total / len(values), 2))} "
            f"across {len(values)} rows."
        )

    # A single non-negative value series over a small category set also reads as a
    # parts-of-whole pie (owner asked for column charts primarily; pie is a bonus).
    if len(numeric_idx) == 1 and charts:
        pie_points = charts[0]["series"][0]["points"]
        if 2 <= len(pie_points) <= _PIE_MAX_SLICES and all(
            isinstance(p["y"], int | float) and p["y"] >= 0 for p in pie_points
        ):
            charts.append(
                {
                    "type": "pie",
                    "title": f"{charts[0]['y_label']} share by {label_name}",
                    "series": [{"label": charts[0]["y_label"], "points": list(pie_points)}],
                    "x_label": label_name,
                    "y_label": charts[0]["y_label"],
                }
            )

    return charts, insights


def _table_from_key_values(key_values: dict[str, str]) -> dict | None:
    rows = [[str(k), str(v)] for k, v in key_values.items() if str(k).strip()]
    if not rows:
        return None
    return {"title": "Key details", "columns": ["Field", "Value"], "rows": rows}


def build_data_analysis(analysis: Any) -> dict:
    """Derive ``tables`` + ``charts`` + ``insights`` from an ``AttachmentAnalysis``.

    ``analysis`` is duck-typed (``.table``, ``.key_values``) so this stays free of
    an import cycle with ``attachment``. Deterministic + offline: a non-tabular
    input yields empty ``tables``/``charts`` and the caller falls back to the
    text summary.
    """

    tables: list[dict] = []
    charts: list[dict] = []
    insights: list[str] = []

    raw_table = getattr(analysis, "table", None)
    if isinstance(raw_table, dict) and raw_table.get("rows"):
        clipped = _clip_table(raw_table)
        columns, rows = clipped["columns"], clipped["rows"]
        tables.append({"title": "Detected table", **clipped})
        chart_specs, chart_insights = _charts_from_table(columns, rows)
        charts.extend(chart_specs[:_MAX_CHARTS])
        insights.append(f"Table with {len(rows)} data rows and {len(columns)} columns.")
        insights.extend(chart_insights)

    key_values = getattr(analysis, "key_values", None)
    if isinstance(key_values, dict) and key_values and len(tables) < _MAX_TABLES:
        kv_table = _table_from_key_values(key_values)
        if kv_table is not None:
            tables.append(kv_table)

    return {
        "tables": tables[:_MAX_TABLES],
        "charts": charts[:_MAX_CHARTS],
        "insights": insights[:_MAX_INSIGHTS],
    }


__all__ = ["build_data_analysis"]
