"""Deterministic A4 PDF rendering for CV versions (lightweight, pure-Python).

Uses ``fpdf2`` (no system libraries). A Unicode TTF is registered when available
so Vietnamese renders correctly (macOS Arial Unicode, common Linux DejaVu, or an
explicit ``CV_PDF_FONT_PATH``). When no Unicode font is present (e.g. a minimal CI
box) text is transliterated to a latin-1-safe form so rendering never fails — this
is a documented local fallback, not the production path.

``render_cv_pdf`` reads a CV version ``snapshot_json`` and renders it through the
SAME structured content model the frontend ``<CvDocument/>`` renderer uses:

- the ``header`` section becomes the document header (name + headline + contact),
- entry sections (``{"entries": [...]}``) render as heading + meta + bullets,
- ``skills`` (``{"items": [{name, level:int}]}``) render as labelled level bars,
- ``languages`` (``{"items": [{name, level:str}]}``) render as name + proficiency,
- text sections (``{"text"}`` / ``{"items": [{text}]}``) render as paragraph/bullets,
- ``{"divider": true}`` renders a hairline.

This replaced a ``key: value`` flattener that dropped experience/education
entirely (they are ``entries``-shaped, which it did not understand), rendered the
contact header as ``name: X`` lines, and printed skills as ``level: 85`` — i.e. it
mangled exactly the CVs students upload. The build is a faithful, grayscale,
ATS-clean port; full theme-palette/column-layout parity with the React renderer
is tracked separately (ADR-0015, a headless-browser print route).

The pure ``build_render_model`` step (snapshot -> ordered typed blocks) carries
all the binding logic and is unit-testable without parsing PDF bytes; ``_CvPdf``
only draws blocks.

``watermark`` draws a diagonal partner-identity overlay on every page; student
self-downloads pass ``watermark=None`` (``docs/SECURITY_PRIVACY.md``: partner
downloads are watermarked, the student's own download is not).

Canvas ordering/visibility: when the snapshot's ``canvas.blocks`` reference a
section (``section_id``), the block's ``order``/``visible`` override that
section's ``sort_order``/``is_visible`` for render purposes, so the PDF matches
what the student arranged on the canvas (see ``_ordered_visible_sections``).
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

# Grayscale palette — monochrome-consistent; per-template colour port is deferred
# to the render-pipeline unification (ADR-0015).
_INK = (17, 17, 17)
_MUTED = (105, 105, 105)
_RULE = (208, 208, 208)
_BAR_TRACK = (226, 226, 226)
_BAR_FILL = (88, 88, 88)

_HEADER_TYPE = "header"
_SKILL_TYPES = {"skills"}
_LANGUAGE_TYPES = {"languages"}
_HEADER_CONTACT_FIELDS = ("email", "phone", "location")


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
    """Flatten unknown ``content_json`` into printable lines (legacy fallback).

    Only reached for content shapes the structured model does not recognise (very
    old/custom sections). Structured header/entries/skills/languages/text sections
    never touch this — they render through the typed model below.
    """

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
            for value in content.values():
                if isinstance(value, (str, int, float)) and str(value).strip():
                    lines.append(str(value))
        return lines
    if isinstance(content, list):
        for item in content:
            lines.extend(_items_lines(item))
        return lines
    return [str(content)]


# --------------------------------------------------------------------------- #
# Pure content-model builder (snapshot -> ordered typed blocks)               #
# --------------------------------------------------------------------------- #


def _stype(section: Any) -> str:
    return str(section.get("section_type") or "") if isinstance(section, dict) else ""


def _content(section: Any) -> dict:
    if not isinstance(section, dict):
        return {}
    content = section.get("content_json")
    return content if isinstance(content, dict) else {}


def _clean_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _humanize(section_type: str) -> str | None:
    label = section_type.replace("_", " ").strip()
    return label[:1].upper() + label[1:] if label else None


def _header_contact(content: dict) -> list[str]:
    parts: list[str] = []
    for field in _HEADER_CONTACT_FIELDS:
        value = _clean_str(content.get(field))
        if value:
            parts.append(value)
    links = content.get("links")
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict):
                label = _clean_str(link.get("label")) or _clean_str(link.get("url"))
                if label:
                    parts.append(label)
    return parts


def _visible_entries(entries: list) -> list[dict]:
    """Keep entries carrying any renderable field; drop blank highlights."""

    out: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        heading = _clean_str(entry.get("heading"))
        meta = [
            m
            for m in (
                _clean_str(entry.get("subheading")),
                _clean_str(entry.get("timeframe")),
                _clean_str(entry.get("location")),
            )
            if m
        ]
        note = _clean_str(entry.get("note"))
        highlights = [
            h.strip()
            for h in (entry.get("highlights") or [])
            if isinstance(h, str) and h.strip()
        ]
        if heading or meta or note or highlights:
            out.append(
                {"heading": heading, "meta": meta, "note": note, "highlights": highlights}
            )
    return out


def _skill_list(items: Any, *, numeric: bool) -> list[dict]:
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        name: str | None
        level: Any = None
        if isinstance(item, dict):
            name = _clean_str(item.get("name")) or _clean_str(item.get("text"))
            raw = item.get("level")
            if numeric:
                if isinstance(raw, bool):
                    level = None
                elif isinstance(raw, (int, float)):
                    level = max(0, min(100, int(raw)))
            else:
                level = _clean_str(raw)
        else:
            name = _clean_str(item)
        if name:
            out.append({"name": name, "level": level})
    return out


def _text_content(content: dict) -> tuple[str | None, list[str]]:
    """Return ``(paragraph, bullets)`` for a text-mode section."""

    text = _clean_str(content.get("text"))
    if text:
        return text, []
    items = content.get("items")
    bullets: list[str] = []
    if isinstance(items, list):
        for item in items:
            line = item.get("text") if isinstance(item, dict) else item
            cleaned = _clean_str(line)
            if cleaned:
                bullets.append(cleaned)
    if bullets:
        return None, bullets
    # Unknown/custom shape: last-resort flatten so nothing is silently lost.
    return None, [line for line in _items_lines(content) if line.strip()]


def build_render_model(snapshot_json: dict) -> list[dict]:
    """Turn a CV version snapshot into an ordered list of typed render blocks.

    Pure (no fpdf): mirrors the frontend ``content.ts`` binding so the exported
    PDF and the on-canvas document render the same content. Empty sections are
    dropped (no orphan heading), matching the read-only ``<CvDocument/>``.
    """

    sections = _ordered_visible_sections(snapshot_json)
    header_section = next((s for s in sections if _stype(s) == _HEADER_TYPE), None)
    header_content = _content(header_section)

    fallback_title = _clean_str(snapshot_json.get("title")) or "Curriculum Vitae"
    model: list[dict] = [
        {
            "type": "header",
            "name": _clean_str(header_content.get("name")) or fallback_title,
            "headline": _clean_str(header_content.get("headline")),
            "contact": _header_contact(header_content),
        }
    ]

    for section in sections:
        if section is header_section:
            continue
        content = _content(section)
        stype = _stype(section)
        heading = _clean_str(section.get("title")) or _humanize(stype) or ""

        if content.get("divider") is True:
            model.append({"type": "divider"})
            continue

        entries = content.get("entries")
        if isinstance(entries, list):
            visible = _visible_entries(entries)
            if visible:
                model.append({"type": "heading", "text": heading})
                model.append({"type": "entries", "entries": visible})
            continue

        if stype in _SKILL_TYPES:
            items = _skill_list(content.get("items"), numeric=True)
            if items:
                model.append({"type": "heading", "text": heading})
                model.append({"type": "skills", "items": items})
            continue

        if stype in _LANGUAGE_TYPES:
            items = _skill_list(content.get("items"), numeric=False)
            if items:
                model.append({"type": "heading", "text": heading})
                model.append({"type": "languages", "items": items})
            continue

        paragraph, bullets = _text_content(content)
        if paragraph or bullets:
            model.append({"type": "heading", "text": heading})
            model.append({"type": "text", "paragraph": paragraph, "bullets": bullets})

    return model


# --------------------------------------------------------------------------- #
# fpdf drawer                                                                  #
# --------------------------------------------------------------------------- #


class _CvPdf(FPDF):
    def __init__(self, *, unicode_font: str | None, watermark: str | None) -> None:
        super().__init__(format="A4", unit="mm")
        self._watermark = watermark
        self.set_margins(left=16, top=16, right=16)
        self.set_auto_page_break(auto=True, margin=16)
        if unicode_font:
            self.add_font("cv", "", unicode_font)
            self.add_font("cv", "B", unicode_font)
            self._family = "cv"
            self._unicode = True
        else:
            self._family = "helvetica"
            self._unicode = False

    def text_for(self, value: object) -> str:
        text = str(value)
        return text if self._unicode else _latin1_safe(text)

    def footer(self) -> None:  # noqa: D401 - fpdf hook
        if not self._watermark:
            return
        self.set_font(self._family, "", 30)
        self.set_text_color(220, 220, 220)
        with self.rotation(45, x=self.w / 2, y=self.h / 2):
            self.text(x=self.w / 2 - 60, y=self.h / 2, text=self.text_for(self._watermark))
        self.set_text_color(0, 0, 0)

    # -- primitives --------------------------------------------------------- #

    def _font(self, size: float, *, bold: bool = False, color: tuple = _INK) -> None:
        self.set_font(self._family, "B" if bold else "", size)
        self.set_text_color(*color)

    def _para(
        self,
        text: str,
        *,
        size: float = 10.0,
        bold: bool = False,
        color: tuple = _INK,
        height: float = 5.2,
        indent: float = 0.0,
        bullet: bool = False,
    ) -> None:
        if not text:
            return
        self._font(size, bold=bold, color=color)
        prefix = "•  " if bullet else ""
        self.set_x(self.l_margin + indent)
        self.multi_cell(
            self.epw - indent,
            height,
            self.text_for(prefix + text),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    def _meta(self, parts: list[str]) -> None:
        text = "  ·  ".join(p for p in parts if p)
        if text:
            self._para(text, size=9.0, color=_MUTED, height=4.8)

    def _ensure_space(self, needed: float) -> None:
        if self.get_y() + needed > self.h - self.b_margin:
            self.add_page()

    def draw_rule(self, *, before: float = 1.4, after: float = 1.8) -> None:
        self.ln(before)
        self.set_draw_color(*_RULE)
        self.set_line_width(0.2)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + self.epw, y)
        self.ln(after)

    # -- blocks ------------------------------------------------------------- #

    def draw_header(self, block: dict) -> None:
        self._para(block["name"], size=20, bold=True, height=9)
        if block.get("headline"):
            self._para(block["headline"], size=11, color=_MUTED, height=6)
        if block.get("contact"):
            self._meta(block["contact"])
        self.draw_rule(before=1.8, after=2.4)

    def draw_heading(self, text: str) -> None:
        if not text:
            return
        self._ensure_space(14)
        self.ln(1.4)
        self._para(text, size=12.5, bold=True, height=6)
        self.set_draw_color(*_RULE)
        self.set_line_width(0.2)
        y = self.get_y() + 0.3
        self.line(self.l_margin, y, self.l_margin + self.epw, y)
        self.ln(2.2)

    def draw_entries(self, entries: list[dict]) -> None:
        for entry in entries:
            self._ensure_space(10)
            if entry.get("heading"):
                self._para(entry["heading"], size=10.5, bold=True, height=5.2)
            self._meta(entry.get("meta") or [])
            if entry.get("note"):
                self._para(entry["note"], size=9.0, color=_MUTED, height=4.8)
            for highlight in entry.get("highlights") or []:
                self._para(highlight, size=10.0, height=5.0, indent=3.0, bullet=True)
            self.ln(1.6)

    def draw_skills(self, items: list[dict]) -> None:
        if any(isinstance(it.get("level"), int) for it in items):
            for item in items:
                self._skill_bar(item["name"], item.get("level"))
        else:
            self._para(
                "  ·  ".join(it["name"] for it in items), size=10.0, height=5.4
            )

    def _skill_bar(self, name: str, level: object) -> None:
        row_h = 5.6
        self._ensure_space(row_h + 1)
        y0 = self.get_y()
        name_w = min(70.0, self.epw * 0.45)
        self._font(9.5)
        self.set_xy(self.l_margin, y0)
        self.cell(name_w, row_h, self.text_for(name), new_x=XPos.RIGHT, new_y=YPos.TOP)
        if isinstance(level, int):
            lvl = max(0, min(100, level))
            bar_x = self.l_margin + name_w + 2
            bar_w = (self.l_margin + self.epw) - bar_x
            if bar_w > 8:
                bar_h = 1.6
                bar_y = y0 + (row_h - bar_h) / 2
                self.set_fill_color(*_BAR_TRACK)
                self.rect(bar_x, bar_y, bar_w, bar_h, style="F")
                self.set_fill_color(*_BAR_FILL)
                self.rect(bar_x, bar_y, bar_w * lvl / 100.0, bar_h, style="F")
        self.set_xy(self.l_margin, y0)
        self.ln(row_h)

    def draw_languages(self, items: list[dict]) -> None:
        for item in items:
            name = item["name"]
            level = item.get("level")
            if isinstance(level, str) and level:
                self._para(f"{name} — {level}", size=10.0, height=5.4)
            else:
                self._para(name, size=10.0, height=5.4)

    def draw_text(self, block: dict) -> None:
        if block.get("paragraph"):
            self._para(block["paragraph"], size=10.0, height=5.6)
        for bullet in block.get("bullets") or []:
            self._para(bullet, size=10.0, height=5.0, indent=3.0, bullet=True)


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

    for block in build_render_model(snapshot_json):
        kind = block["type"]
        if kind == "header":
            pdf.draw_header(block)
        elif kind == "heading":
            pdf.draw_heading(block["text"])
        elif kind == "entries":
            pdf.draw_entries(block["entries"])
        elif kind == "skills":
            pdf.draw_skills(block["items"])
        elif kind == "languages":
            pdf.draw_languages(block["items"])
        elif kind == "text":
            pdf.draw_text(block)
        elif kind == "divider":
            pdf.draw_rule()

    out = pdf.output()
    return bytes(out)
