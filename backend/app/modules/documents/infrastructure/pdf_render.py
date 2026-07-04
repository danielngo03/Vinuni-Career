"""Deterministic A4 PDF rendering for CV versions (lightweight, pure-Python).

Uses ``fpdf2`` (no system libraries). A Unicode TTF is registered when available
so Vietnamese renders correctly (macOS Arial Unicode, common Linux DejaVu, or an
explicit ``CV_PDF_FONT_PATH``). When no Unicode font is present (e.g. a minimal CI
box) text is transliterated to a latin-1-safe form so rendering never fails — this
is a documented local fallback, not the production path.

``render_cv_pdf`` reads a CV version ``snapshot_json`` and renders title +
sections + items. ``watermark`` draws a diagonal partner-identity overlay on every
page; student self-downloads pass ``watermark=None`` (``docs/SECURITY_PRIVACY.md``:
partner downloads are watermarked, the student's own download is not).

When the snapshot's ``canvas.blocks`` reference a section (``section_id``), the
block's ``order``/``visible`` override that section's ``sort_order``/``is_visible``
for render purposes, so the PDF matches what the student arranged on the canvas.
Sections with no matching block keep their own ``sort_order``/``is_visible``
(legacy CVs with empty ``canvas_json``, or sections added after the last canvas
edit). This is a targeted ordering/visibility fix only — block-level style
(font/color/emphasis) and free-form layout are intentionally not rendered here
pending the render-pipeline unification tracked in ADR-0015.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.core.config import get_settings

# Candidate Unicode fonts, in order of preference.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _font_path() -> str | None:
    configured = get_settings().cv_pdf_font_path
    if configured and Path(configured).is_file():
        return configured
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _latin1_safe(text: str) -> str:
    """Best-effort transliteration so the core (latin-1) font can render text."""

    return unicodedata.normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")


def _items_lines(content: Any) -> list[str]:
    """Flatten a section's ``content_json`` into printable lines (no raw markup)."""

    lines: list[str] = []
    if content is None:
        return lines
    if isinstance(content, str):
        return [content] if content.strip() else []
    if isinstance(content, dict):
        items = content.get("items")
        if isinstance(items, list):
            for item in items:
                lines.extend(_items_lines(item))
        else:
            # Render a flat key: value block for simple dict content.
            for key, value in content.items():
                if isinstance(value, (str, int, float)) and str(value).strip():
                    lines.append(f"{key}: {value}")
        return lines
    if isinstance(content, list):
        for item in content:
            lines.extend(_items_lines(item))
        return lines
    return [str(content)]


class _CvPdf(FPDF):
    def __init__(self, *, unicode_font: str | None, watermark: str | None) -> None:
        super().__init__(format="A4", unit="mm")
        self._watermark = watermark
        self.set_auto_page_break(auto=True, margin=18)
        if unicode_font:
            self.add_font("cv", "", unicode_font)
            self.add_font("cv", "B", unicode_font)
            self._family = "cv"
            self._unicode = True
        else:
            self._family = "helvetica"
            self._unicode = False

    def text_for(self, value: str) -> str:
        return value if self._unicode else _latin1_safe(value)

    def footer(self) -> None:  # noqa: D401 - fpdf hook
        if not self._watermark:
            return
        self.set_font(self._family, "", 30)
        self.set_text_color(220, 220, 220)
        with self.rotation(45, x=self.w / 2, y=self.h / 2):
            self.text(x=self.w / 2 - 60, y=self.h / 2, text=self.text_for(self._watermark))
        self.set_text_color(0, 0, 0)


def _ordered_visible_sections(snapshot_json: dict) -> list[dict]:
    """Sections in canvas order/visibility where a block exists, else their own."""

    sections = [s for s in (snapshot_json.get("sections") or []) if isinstance(s, dict)]
    blocks = (snapshot_json.get("canvas") or {}).get("blocks") or []
    block_by_section: dict[str, dict] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        section_id = block.get("section_id")
        if section_id is not None:
            block_by_section[str(section_id)] = block

    def sort_key(section: dict) -> tuple[int, int]:
        block = block_by_section.get(str(section.get("id"))) if section.get("id") else None
        order = block.get("order") if block is not None else section.get("sort_order")
        return (0, order if isinstance(order, int) else 0)

    visible = []
    for section in sections:
        block = block_by_section.get(str(section.get("id"))) if section.get("id") else None
        is_visible = block.get("visible") if block is not None else section.get("is_visible")
        if is_visible is False:
            continue
        visible.append(section)
    return sorted(visible, key=sort_key)


def render_cv_pdf(snapshot_json: dict, *, watermark: str | None = None) -> bytes:
    """Render a CV version snapshot to a deterministic A4 PDF (bytes)."""

    font = _font_path()
    pdf = _CvPdf(unicode_font=font, watermark=watermark)
    pdf.add_page()
    family = pdf._family

    def _line(height: float, text: str) -> None:
        # new_x/new_y keep the cursor at the left margin on the next row so the
        # following multi_cell always has the full page width available.
        pdf.multi_cell(0, height, pdf.text_for(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    title = str(snapshot_json.get("title") or "Curriculum Vitae")
    pdf.set_font(family, "B", 18)
    _line(10, title)
    pdf.ln(2)

    sections = _ordered_visible_sections(snapshot_json)
    for section in sections:
        heading = str(section.get("title") or section.get("section_type") or "")
        if heading:
            pdf.set_font(family, "B", 13)
            _line(8, heading)
        pdf.set_font(family, "", 11)
        content = section.get("content_json") if isinstance(section, dict) else None
        for line in _items_lines(content):
            _line(6, f"- {line}")
        pdf.ln(2)

    out = pdf.output()
    return bytes(out)
