"""Generic chat-attachment analysis — a cost-tiered document/image reader.

Reuses the platform's existing extraction primitives (it is NOT a new parser):

1. security + size + type gate (``cv_validation.security_gate`` / ``sniff_kind``).
2. native text (``text_extraction.extract_text`` — pdfplumber/python-docx/UTF-8).
3. OCR fallback (``adapters.ocr.get_ocr_adapter``) for images / scanned PDFs when
   native text is sparse.
4. a cheap vision-LLM tier (owner-approved downscaled-image path) that transcribes
   AND summarises an image / scanned PDF in one call. Off by default (offline /
   tests) and injectable via ``set_attachment_vision_adapter`` — it degrades to
   the deterministic text/OCR result, never crashing.

Unlike the CV/JD cascades this produces a GENERIC analysis (``summary`` +
``extracted_text_preview`` + optional ``table`` + ``key_values``), not a
CV/JD-specific structure, because a user may attach any document or image. The
university data-analysis layer (``app.ai.extraction.data_analysis``) turns the
detected table + numeric columns into render-ready tables + charts. Nothing the
model returns is trusted verbatim: text is scrubbed and lengths are capped, and a
non-analyzable/blank/junk file yields a clean "couldn't analyse" result — never a
fabricated one. Provider/model/token/OCR internals never appear in the output.

Merge-reconciliation note: this module mirrors the partner-ai-overhaul worktree's
``app/ai/extraction/attachment.py`` so the eventual merge dedups. The only
divergence is the additive ``AttachmentAnalysis.vision_used`` flag (used by the
university attachment service to charge the pricier vision tier weight); keep the
superset at merge.
"""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import httpx

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters.base import redact_secrets
from app.ai.extraction.adapters.ocr import get_ocr_adapter
from app.ai.extraction.text_extraction import (
    ExtractionError,
    FileKind,
    extract_text,
    sniff_kind,
)
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.ai.observability.usage import log_ai_usage
from app.core.config import Settings, get_settings

# A PDF with fewer readable native-text chars than this is treated as scanned and
# routed to the OCR / vision tier.
_NATIVE_TEXT_MIN = 40
_PREVIEW_CHARS = 1500
_SUMMARY_CHARS = 320
_MAX_TABLE_ROWS = 20
_MAX_TABLE_COLS = 12
_MAX_KEY_VALUES = 20

_SUPPORTED_KINDS = {FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE}

# text_extraction ExtractionError.code -> user-safe outcome status
_EXTRACTION_ERROR_STATUS = {
    "PASSWORD_PROTECTED_FILE": "password_protected_file",
    "CORRUPT_FILE": "corrupt_file",
    "UNSUPPORTED_FILE_TYPE": "unsupported_file_type",
}

_KIND_LABEL = {
    FileKind.PDF: "pdf",
    FileKind.DOCX: "docx",
    FileKind.TXT: "text",
    FileKind.IMAGE: "image",
    FileKind.UNKNOWN: "unknown",
}

_KEY_VALUE_RE = re.compile(r"^\s*([^\n:]{1,40}?)\s*:\s*(\S.{0,200}?)\s*$")
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_NO_KEY_PROVIDERS = {"ollama-local", "ollama"}
_VISION_MAX_OUTPUT_TOKENS = 3000
_VISION_MAX_NATIVE_TEXT_CHARS = 8000

_VISION_NATIVE_TEXT_PREFIX = (
    "For reference, here is the raw text embedded in the document. Reading ORDER "
    "may be scrambled; rely on the image(s) for structure but use this text for the "
    "EXACT spelling of numbers, emails, and dates. RAW TEXT:\n"
)

_VISION_SYSTEM_PROMPT = """You are a precise document/image analyst for a career platform.
You are given one or more images of a document a user attached (and possibly its
raw embedded text). Transcribe and analyse ONLY what is visibly present.

Strict rules:
- Transcribe only visible text. NEVER invent, translate, or autocomplete anything.
- Preserve the original language and Vietnamese diacritics exactly as shown.
- If the document contains a table, put it in "tables" as columns + rows of cells.
- If it has clear label/value pairs (e.g. "Ngày: 01/2026"), put them in "key_values".
- "summary" is a 1-3 sentence neutral description of what the document is and its key
  content — no opinions, no invented facts.
- Return ONLY one JSON object, no prose, no markdown fences.

JSON schema:
{
  "transcript": "full readable text, in reading order",
  "summary": "1-3 sentence neutral description",
  "tables": [{"columns": ["",""], "rows": [["",""]]}],
  "key_values": {"label": "value"}
}
Omit "tables"/"key_values" when none are present. If the image has no readable
content, return {"transcript": "", "summary": ""}."""

_VISION_USER_PROMPT = (
    "Transcribe, summarise, and extract any table / key-value data from this "
    "document into the JSON schema. Return only the JSON object."
)


@dataclass(slots=True)
class AttachmentPolicy:
    """Effective knobs for one analysis run (reuses the CV vision settings)."""

    max_bytes: int
    ocr_langs: str
    vision_enabled: bool
    vision_max_image_px: int
    vision_max_pages: int


def resolve_policy(settings: Settings | None = None) -> AttachmentPolicy:
    s = settings or get_settings()
    return AttachmentPolicy(
        max_bytes=s.max_upload_bytes,
        ocr_langs=s.tesseract_ocr_langs,
        vision_enabled=s.cv_vision_extraction_enabled,
        vision_max_image_px=s.cv_vision_max_image_px,
        vision_max_pages=s.cv_vision_max_pages,
    )


@dataclass(slots=True)
class AttachmentAnalysis:
    """Leakage-safe analysis outcome the assistant turns into prose / a table."""

    status: str
    kind: str
    analyzed: bool = False
    degraded: bool = False
    # True when the vision-LLM tier produced the content (used by the caller to
    # charge the pricier vision energy weight). Additive vs partner.
    vision_used: bool = False
    summary: str = ""
    extracted_text_preview: str = ""
    table: dict | None = None
    key_values: dict | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def chargeable(self) -> bool:
        """Only a real, user-visible analysis debits energy (§3.2)."""

        return self.status == "analyzed" and self.analyzed

    def to_public(self) -> dict:
        out: dict = {
            "status": self.status,
            "kind": self.kind,
            "analyzed": self.analyzed,
            "degraded": self.degraded,
            "summary": self.summary,
            "extracted_text_preview": self.extracted_text_preview,
        }
        if self.table is not None:
            out["table"] = self.table
        if self.key_values:
            out["key_values"] = self.key_values
        return out


# --------------------------------------------------------------------------- #
# Vision tier seam (Disabled by default; a gateway adapter is wired in prod).  #
# --------------------------------------------------------------------------- #


@runtime_checkable
class AttachmentVisionEngine(Protocol):
    """A multimodal engine that reads a document/image into a generic analysis."""

    @property
    def available(self) -> bool: ...

    def analyze(
        self,
        data: bytes,
        kind: FileKind,
        *,
        max_image_px: int,
        max_pages: int,
        native_text: str | None = None,
    ) -> dict | None: ...


class DisabledAttachmentVisionAdapter:
    """An explicitly-off adapter (vision analysis disabled → degrade to text)."""

    engine_family = "attachment_vision"
    engine_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def analyze(
        self,
        data: bytes,
        kind: FileKind,
        *,
        max_image_px: int,
        max_pages: int,
        native_text: str | None = None,
    ) -> dict | None:
        return None


class GatewayAttachmentVisionAdapter:
    """Production vision analysis through the configured AI gateway route.

    Reuses the platform's gateway plumbing (``runtime_config`` provider routes,
    ``_get_api_key``, ``real_provider_active``, ``output_guard.scrub_text``,
    ``log_ai_usage``) with a GENERIC analysis prompt — it is not a new parser.
    ``available`` is False offline / in tests (no real provider) so the cascade
    degrades to deterministic text/OCR. Synchronous (the caller offloads via
    ``asyncio.to_thread``); best-effort — a failure returns ``None``.
    """

    engine_family = "attachment_vision_gateway"
    engine_version = "v1"

    def _alias(self, cfg: runtime_config.EffectiveAiConfig) -> str:
        configured = get_settings().cv_vision_provider_alias
        if configured in cfg.provider_routes:
            return configured
        return "vision_default" if "vision_default" in cfg.provider_routes else configured

    @property
    def available(self) -> bool:
        cfg = runtime_config.current()
        route = cfg.provider_routes.get(self._alias(cfg))
        if not real_provider_active() or route is None:
            return False
        provider_name = route[0]
        if provider_name in _NO_KEY_PROVIDERS:
            return True
        return bool(_get_api_key(provider_name))

    def analyze(
        self,
        data: bytes,
        kind: FileKind,
        *,
        max_image_px: int,
        max_pages: int,
        native_text: str | None = None,
    ) -> dict | None:
        cfg = runtime_config.current()
        alias = self._alias(cfg)
        route = cfg.provider_routes.get(alias)
        if route is None:
            return None
        provider_name, base_url, model_id = route
        api_key = _get_api_key(provider_name)
        if not api_key and provider_name not in _NO_KEY_PROVIDERS:
            return None

        images = _prepare_images(data, kind, max_px=max_image_px, max_pages=max_pages)
        if not images:
            return None

        content: list[dict] = [{"type": "text", "text": _VISION_USER_PROMPT}]
        if native_text and native_text.strip():
            redacted = redact_secrets(native_text)[:_VISION_MAX_NATIVE_TEXT_CHARS]
            content.append({"type": "text", "text": _VISION_NATIVE_TEXT_PREFIX + redacted})
        for jpeg in images:
            b64 = base64.b64encode(jpeg).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": _VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.0,
            "max_tokens": _VISION_MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }
        prompt_chars = (
            len(_VISION_SYSTEM_PROMPT) + len(_VISION_USER_PROMPT) + len(native_text or "")
        )
        try:
            with httpx.Client(timeout=float(get_settings().cv_extraction_max_seconds)) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError):
            log_ai_usage(
                task_type="attachment_vision_analysis", alias=alias, success=False,
                prompt_chars=prompt_chars,
            )
            return None

        choice = (body.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content", "")
        if isinstance(raw, list):  # some providers return content as parts
            raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
        log_ai_usage(
            task_type="attachment_vision_analysis", alias=alias, success=True,
            prompt_chars=prompt_chars, completion_chars=len(raw or ""),
        )
        return _extract_json(scrub_text(raw or ""))


# ---- image prep (kept local, mirroring the JD vision adapter's copy) ----------


def _prepare_images(data: bytes, kind: FileKind, *, max_px: int, max_pages: int) -> list[bytes]:
    if kind is FileKind.IMAGE:
        jpeg = _downscale_to_jpeg(data, max_px)
        return [jpeg] if jpeg else []
    if kind is FileKind.PDF:
        return _pdf_pages_to_jpeg(data, max_pages=max_pages, max_px=max_px)
    return []


def _downscale_to_jpeg(data: bytes, max_px: int) -> bytes | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as opened:
            img = opened.convert("RGB")
            longest = max(img.size)
            if longest > max_px:
                scale = max_px / float(longest)
                img = img.resize(
                    (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
                )
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:  # noqa: BLE001 — unreadable image → no vision input
        return None


def _pdf_pages_to_jpeg(data: bytes, *, max_pages: int, max_px: int) -> list[bytes]:
    pages: list[bytes] = []
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            for index, page in enumerate(doc):
                if index >= max_pages:
                    break
                pix = page.get_pixmap(dpi=150)
                jpeg = _downscale_to_jpeg(pix.tobytes("png"), max_px)
                if jpeg:
                    pages.append(jpeg)
    except ImportError:
        return []
    except Exception:  # noqa: BLE001 — corrupt PDF → no vision input
        return pages
    return pages


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


_vision_adapter: AttachmentVisionEngine | None = None


def get_attachment_vision_adapter() -> AttachmentVisionEngine:
    """Process-wide vision adapter. Gateway-backed by default; overridable in tests.

    The gateway adapter reports ``available=False`` offline / in tests (no real
    provider), so the cascade degrades to deterministic text/OCR without any real
    call. Tests inject a fake via ``set_attachment_vision_adapter``.
    """

    global _vision_adapter
    if _vision_adapter is None:
        _vision_adapter = GatewayAttachmentVisionAdapter()
    return _vision_adapter


def set_attachment_vision_adapter(adapter: AttachmentVisionEngine | None) -> None:
    """Override the vision adapter (test seam / prod wiring). ``None`` resets."""

    global _vision_adapter
    _vision_adapter = adapter


def run_attachment_vision(
    data: bytes,
    kind: FileKind,
    *,
    enabled: bool,
    max_image_px: int,
    max_pages: int,
    native_text: str | None = None,
) -> dict | None:
    """Run the vision tier if enabled + available. Best-effort; never raises."""

    if not enabled:
        return None
    adapter = get_attachment_vision_adapter()
    if not adapter.available:
        return None
    try:
        return adapter.analyze(
            data,
            kind,
            max_image_px=max_image_px,
            max_pages=max_pages,
            native_text=native_text,
        )
    except Exception:  # noqa: BLE001 — vision is a best-effort fallback tier
        return None


# --------------------------------------------------------------------------- #
# Deterministic structuring helpers (offline-safe; never fabricate).           #
# --------------------------------------------------------------------------- #


def _clean_cell(value: object, limit: int = 200) -> str:
    text = value if isinstance(value, str) else str(value or "")
    return text.strip()[:limit]


def _detect_table(text: str) -> dict | None:
    """Detect a simple delimited table (CSV/TSV/pipe) in ``text``.

    Deterministic: a table needs ≥2 rows that agree on a ≥2 column count under one
    delimiter. Returns ``{"columns": [...], "rows": [[...]]}`` or ``None``.
    """

    lines = [ln for ln in text.splitlines() if ln.strip()][: _MAX_TABLE_ROWS + 5]
    if len(lines) < 2:
        return None
    for delim in ("\t", "|", ","):
        rows = [[c.strip() for c in ln.split(delim)] for ln in lines]
        counts = [len(r) for r in rows if len(r) >= 2]
        if len(counts) < 2:
            continue
        # Majority column count (the consistent shape of the table body).
        width = max(set(counts), key=counts.count)
        if width < 2:
            continue
        shaped = [r for r in rows if len(r) == width]
        if len(shaped) < 2:
            continue
        header = [_clean_cell(c, 80) for c in shaped[0][:_MAX_TABLE_COLS]]
        body = [
            [_clean_cell(c) for c in r[:_MAX_TABLE_COLS]]
            for r in shaped[1 : _MAX_TABLE_ROWS + 1]
        ]
        if not body:
            continue
        return {"columns": header, "rows": body}
    return None


def _detect_key_values(text: str) -> dict | None:
    """Extract ``Label: value`` pairs (deterministic). ≥2 pairs or ``None``."""

    pairs: dict[str, str] = {}
    for line in text.splitlines():
        m = _KEY_VALUE_RE.match(line)
        if not m:
            continue
        label = _clean_cell(m.group(1), 40)
        value = _clean_cell(m.group(2), 200)
        if label and value and label not in pairs:
            pairs[label] = value
        if len(pairs) >= _MAX_KEY_VALUES:
            break
    return pairs if len(pairs) >= 2 else None


def _deterministic_summary(kind_label: str, text: str) -> str:
    """First readable lines as a plain summary (no LLM, never invented)."""

    snippet = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())[:_SUMMARY_CHARS]
    if not snippet:
        return ""
    return snippet


def _normalize_vision(raw: dict) -> dict:
    """Coerce the vision model's output into safe transcript/summary/table/kv."""

    transcript = scrub_text(_clean_cell(raw.get("transcript"), 20_000))
    summary = scrub_text(_clean_cell(raw.get("summary"), _SUMMARY_CHARS))

    table = None
    raw_table = raw.get("tables") or raw.get("table")
    if isinstance(raw_table, list) and raw_table:
        raw_table = raw_table[0]
    if isinstance(raw_table, dict):
        cols = raw_table.get("columns")
        rows = raw_table.get("rows")
        if isinstance(cols, list) and isinstance(rows, list) and rows:
            table = {
                "columns": [_clean_cell(c, 80) for c in cols[:_MAX_TABLE_COLS]],
                "rows": [
                    [_clean_cell(c) for c in r[:_MAX_TABLE_COLS]]
                    for r in rows[:_MAX_TABLE_ROWS]
                    if isinstance(r, list)
                ],
            }
            if not table["rows"]:
                table = None

    key_values = None
    raw_kv = raw.get("key_values")
    if isinstance(raw_kv, dict) and raw_kv:
        kv: dict[str, str] = {}
        for k, v in list(raw_kv.items())[:_MAX_KEY_VALUES]:
            label = _clean_cell(k, 40)
            value = _clean_cell(v, 200)
            if label and value:
                kv[label] = value
        key_values = kv or None

    return {
        "transcript": transcript,
        "summary": summary,
        "table": table,
        "key_values": key_values,
    }


# --------------------------------------------------------------------------- #
# Entry point (synchronous — caller offloads via asyncio.to_thread)            #
# --------------------------------------------------------------------------- #


def analyze_document(
    filename: str,
    data: bytes,
    *,
    policy: AttachmentPolicy | None = None,
    vision_runner=run_attachment_vision,
) -> AttachmentAnalysis:
    """Analyse an attachment through the cost-tiered cascade. Never raises.

    Returns an :class:`AttachmentAnalysis`. ``chargeable`` is True only for a
    genuine ``analyzed`` result; every gate/failure/blank outcome is 0-cost.
    """

    pol = policy or resolve_policy()

    # Tier 0 — size + type + security gate (cheap, fail fast; never stores here).
    if not data:
        return AttachmentAnalysis(status="not_analyzable", kind="unknown")
    if len(data) > pol.max_bytes:
        return AttachmentAnalysis(status="file_too_large", kind="unknown")
    kind = sniff_kind(filename, data)
    if kind not in _SUPPORTED_KINDS:
        return AttachmentAnalysis(status="unsupported_file_type", kind=_KIND_LABEL[kind])
    if cv_validation.security_gate(data, filename) is not None:
        return AttachmentAnalysis(status="file_rejected_security", kind=_KIND_LABEL[kind])

    kind_label = _KIND_LABEL[kind]

    # Tier 1 — native text (pdfplumber / python-docx / UTF-8; OCR hook for images).
    try:
        extraction = extract_text(filename, data)
    except ExtractionError as exc:
        status = _EXTRACTION_ERROR_STATUS.get(exc.code, "corrupt_file")
        return AttachmentAnalysis(status=status, kind=kind_label)
    native_text = (extraction.text or "").strip()
    ocr_used = extraction.ocr_used

    is_image = kind is FileKind.IMAGE
    scanned_pdf = kind is FileKind.PDF and len(native_text) < _NATIVE_TEXT_MIN

    vision: dict | None = None
    degraded = False

    # Tier 2 — vision (images / scanned PDFs). Owner-approved downscaled-image path.
    if is_image or scanned_pdf:
        raw_vision = vision_runner(
            data,
            kind,
            enabled=pol.vision_enabled,
            max_image_px=pol.vision_max_image_px,
            max_pages=pol.vision_max_pages,
            native_text=native_text or None,
        )
        if isinstance(raw_vision, dict):
            vision = _normalize_vision(raw_vision)
        else:
            # Vision unavailable/off for an image path → degrade to OCR/text.
            degraded = is_image or scanned_pdf

        # Tier 3 — OCR fallback when vision produced nothing and text is sparse.
        if vision is None and not native_text:
            adapter = get_ocr_adapter()
            if getattr(adapter, "available", False):
                try:
                    recognized = adapter.recognize(data, pol.ocr_langs)
                    native_text = (recognized or "").strip()
                    ocr_used = True
                    degraded = True
                except Exception:  # noqa: BLE001 — OCR is best-effort
                    native_text = ""

    # Assemble the analysis from whichever tier produced content.
    text_for_struct = ""
    summary = ""
    if vision is not None:
        text_for_struct = vision["transcript"] or native_text
        summary = vision["summary"]
    else:
        text_for_struct = native_text

    text_for_struct = text_for_struct.strip()
    if not text_for_struct and (vision is None or not summary):
        # Nothing readable at all — a blank/junk/unreadable file. Never fabricate.
        return AttachmentAnalysis(
            status="not_analyzable", kind=kind_label, degraded=degraded
        )

    preview = scrub_text(text_for_struct)[:_PREVIEW_CHARS]
    if not summary:
        summary = _deterministic_summary(kind_label, text_for_struct)

    table = (vision or {}).get("table") if vision else None
    if table is None:
        table = _detect_table(text_for_struct)
    key_values = (vision or {}).get("key_values") if vision else None
    if key_values is None:
        key_values = _detect_key_values(text_for_struct)

    warnings: list[str] = []
    if ocr_used:
        warnings.append("ocr")

    return AttachmentAnalysis(
        status="analyzed",
        kind=kind_label,
        analyzed=True,
        degraded=degraded,
        vision_used=vision is not None,
        summary=summary,
        extracted_text_preview=preview,
        table=table,
        key_values=key_values,
        warnings=warnings,
    )


__all__ = [
    "AttachmentPolicy",
    "AttachmentAnalysis",
    "AttachmentVisionEngine",
    "DisabledAttachmentVisionAdapter",
    "GatewayAttachmentVisionAdapter",
    "resolve_policy",
    "analyze_document",
    "run_attachment_vision",
    "get_attachment_vision_adapter",
    "set_attachment_vision_adapter",
]
