"""Vision-LLM extraction adapter: image / scanned-PDF CV -> structured JSON.

This is the third extraction tier (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3.5).
Local Tesseract OCR is unreliable on the styled, multi-column CV templates that
students actually upload (TopCV-style two-column layouts, skill bars, coloured
sidebars), so a cheap multimodal model performs OCR **and** structuring in a
single call and returns the same ``extracted_data``/``review_fields`` shape as the
deterministic path — a drop-in, higher-accuracy structuring for images.

Cost discipline (the reason this is a *tier*, not the default):
- It runs ONLY when native text and local OCR fail to yield a reliable parse.
  Text PDFs never reach it.
- Images are downscaled to a long-edge cap before upload and scanned PDFs send at
  most ``cv_vision_max_pages`` rasterised pages.
- The concrete model id is resolved via an alias and NEVER exposed to end users;
  provider/model/token internals stay inside this layer.

PRIVACY: unlike the text LLM structuring adapter, this tier intentionally sends
downscaled document images to the model. That is an explicit, owner-approved
product decision recorded in ``config.cv_vision_extraction_enabled`` and gated on
``real_calls_active`` — it is off by default in offline/test runs. The model
output is scrubbed and re-validated locally; nothing the model returns is trusted
as-is.
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Protocol, runtime_checkable

import httpx

from app.ai.extraction import cv_structuring
from app.ai.extraction.adapters.base import redact_secrets
from app.ai.extraction.text_extraction import FileKind
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.ai.observability.usage import log_ai_usage
from app.core.config import get_settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_OUTPUT_TOKENS = 4000
_MAX_NATIVE_TEXT_CHARS = 12_000
_NO_KEY_PROVIDERS = {"ollama-local", "ollama"}

_NATIVE_TEXT_PREFIX = (
    "For reference, here is the raw text embedded in the document. Its reading "
    "ORDER may be scrambled (multi-column layouts flatten badly), so rely on the "
    "image(s) for structure and section grouping — but use this text to get the "
    "EXACT spelling of emails, phone numbers, names, dates and numbers, which are "
    "more reliable here than reading them off the image. Do not invent anything "
    "not present in both. RAW TEXT:\n"
)

_SYSTEM_PROMPT = """You are a precise CV/resume parser for a career platform.
You are given one or more images of a single candidate's CV (and possibly its raw
embedded text) and must transcribe and STRUCTURE it into clean JSON with separate
fields — never blobs.

Strict rules:
- Transcribe ONLY what is visibly written. Never invent, translate, or autocomplete
  names, employers, schools, dates, GPAs, skills, or contact details. Omit anything
  not present.
- Preserve the original language and Vietnamese diacritics exactly as shown.
- Read multi-column layouts in natural reading order; keep sidebar content
  (contact, skills, hobbies) with the correct section; do not interleave columns.
- Return SEPARATE FIELDS. Put NO bullet characters ("•", "-", "*") inside any
  value — each responsibility/achievement/detail is its own string in "highlights".
- Dates: put start and end in the separate "start"/"end" fields (never merge them
  into another field). Use "Present"/"Nay" for ongoing. Keep the format shown
  (e.g. "2018", "04/2020"). GPA/classification goes in its own field, not in a bullet.
- Proficiency levels: if a skill/language shows a level (a %, a filled bar, stars,
  or a word), set "level". For SKILLS use an INTEGER 0-100 (a percentage as-is; a
  bar by its fill; N of 5 stars -> N*20). For LANGUAGES use the word or score
  string (e.g. "TOEIC 940", "Thành thạo"). Use null when no level is shown. Read the
  bar/star fill from the IMAGE. Never invent a level.
- "headline" is the professional title/subtitle under the name (e.g. "Security
  Operation", "Điều dưỡng viên"). Map hobbies->interests, volunteering->activities,
  referees->references.
- detected_language is "vi" or "en" (dominant language).
- Return ONLY one JSON object — no prose, no markdown fences. Omit empty fields and
  absent sections.

JSON schema:
{
  "is_cv": true|false,
  "detected_language": "vi"|"en",
  "contact": {"name":"", "headline":"", "email":"", "phone":"", "location":"", "links":""},
  "summary": ["paragraph", "..."],
  "experience": [{"role":"","organization":"","location":"","start":"","end":"","highlights":[]}],
  "education": [{"degree":"","school":"","start":"","end":"","gpa":"","highlights":[]}],
  "projects": [{"name":"", "role":"", "start":"", "end":"", "highlights":[""]}],
  "skills": [{"name":"", "level":85}],
  "languages": [{"name":"", "level":""}],
  "certifications": [{"name":"", "issuer":"", "date":""}],
  "awards": [{"title":"", "issuer":"", "date":""}],
  "activities": [{"role":"", "organization":"", "start":"", "end":"", "highlights":[""]}],
  "interests": ["", ""],
  "publications": [{"title":"", "date":""}],
  "references": [{"name":"", "role":"", "contact":""}]
}
Set is_cv=false only if the document is clearly not a CV/resume (invoice, article,
form, receipt, or a blank page)."""

_USER_PROMPT = (
    "Transcribe and structure this CV into the JSON schema. "
    "Return only the JSON object."
)


@runtime_checkable
class VisionExtractionEngine(Protocol):
    """A multimodal engine that reads document images into structured CV JSON."""

    @property
    def available(self) -> bool: ...

    def extract(
        self,
        data: bytes,
        kind: FileKind,
        *,
        max_image_px: int,
        max_pages: int,
        native_text: str | None = None,
    ) -> dict | None: ...


class DisabledVisionExtractionAdapter:
    """Default adapter: vision extraction is off (offline / tests)."""

    engine_family = "vision_llm"
    engine_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def extract(
        self,
        data: bytes,
        kind: FileKind,
        *,
        max_image_px: int,
        max_pages: int,
        native_text: str | None = None,
    ) -> dict | None:
        return None


class GatewayVisionExtractionAdapter:
    """Production vision extraction through the configured AI gateway route.

    Synchronous (the ingestion cascade is synchronous and may run in the
    lightweight local queue), mirroring ``GatewayLlmStructuringAdapter``.
    """

    engine_family = "vision_llm_gateway"
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

    def extract(
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

        content: list[dict] = [{"type": "text", "text": _USER_PROMPT}]
        if native_text and native_text.strip():
            redacted = redact_secrets(native_text)[:_MAX_NATIVE_TEXT_CHARS]
            content.append({"type": "text", "text": _NATIVE_TEXT_PREFIX + redacted})
        for jpeg in images:
            b64 = base64.b64encode(jpeg).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }
        # GOVERNANCE (WS-2): this tier still issues its own downscaled-image HTTP
        # call rather than routing through the gateway provider abstraction, which
        # does not yet carry multimodal image parts. That refactor is a tracked
        # follow-up. Until then this call is (a) gated on ``real_provider_active``
        # (see ``available`` above), (b) preflight-gated + METERED at the service
        # layer via ``documents.application.extraction_metering`` using the
        # cascade's tier flags (charged only on a successful, user-visible result),
        # and (c) documented here. Image bytes go ONLY down this approved
        # downscaled-vision path — never anywhere else.
        # Prompt-size proxy for the usage ledger (image bytes dominate real cost
        # but the char-based estimator can't see them; the native-text + prompt
        # size is still a useful, PII-safe signal and records that a paid vision
        # call happened — spec §5.4/§15).
        prompt_chars = len(_SYSTEM_PROMPT) + len(_USER_PROMPT) + len(native_text or "")
        try:
            with httpx.Client(timeout=float(get_settings().cv_extraction_max_seconds)) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError):
            log_ai_usage(task_type="cv_vision_extraction", alias=alias, success=False,
                         prompt_chars=prompt_chars)
            return None

        choice = (body.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content", "")
        if isinstance(raw, list):  # some providers return content as parts
            raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
        log_ai_usage(task_type="cv_vision_extraction", alias=alias, success=True,
                     prompt_chars=prompt_chars, completion_chars=len(raw or ""))
        parsed = _extract_json(scrub_text(raw or ""))
        if parsed is None:
            return None
        return _normalize(parsed)


# --------------------------------------------------------------------------- #
# Image preparation (downscale to control cost; rasterize scanned PDFs)        #
# --------------------------------------------------------------------------- #


def _prepare_images(
    data: bytes, kind: FileKind, *, max_px: int, max_pages: int
) -> list[bytes]:
    if kind is FileKind.IMAGE:
        jpeg = _downscale_to_jpeg(data, max_px)
        return [jpeg] if jpeg else []
    if kind is FileKind.PDF:
        return _pdf_pages_to_jpeg(data, max_pages=max_pages, max_px=max_px)
    return []


def _downscale_to_jpeg(data: bytes, max_px: int) -> bytes | None:
    """Open an image, flatten to RGB, cap the long edge, re-encode as JPEG."""

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
    except Exception:  # noqa: BLE001 - unreadable image -> no vision input
        return None


def _pdf_pages_to_jpeg(data: bytes, *, max_pages: int, max_px: int) -> list[bytes]:
    """Rasterise the first ``max_pages`` PDF pages to downscaled JPEG bytes."""

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
    except Exception:  # noqa: BLE001 - corrupt PDF -> no vision input
        return pages
    return pages


# --------------------------------------------------------------------------- #
# Output parsing + normalisation (never trust the model's shape verbatim)      #
# --------------------------------------------------------------------------- #


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else str(value or "")
    text = _CONTROL_CHARS_RE.sub("", text)
    return text.strip()[:limit]


def _short(value: object, limit: int = 300) -> str:
    return _clean(value, limit)


def _timeframe(entry: dict) -> str:
    start, end = _short(entry.get("start"), 60), _short(entry.get("end"), 60)
    if start and end:
        return f"{start} - {end}"
    return start or end


def _highlights(entry: dict) -> list[str]:
    raw = entry.get("highlights")
    out: list[str] = []
    if isinstance(raw, list):
        for h in raw[:25]:
            text = _clean(h.get("text") if isinstance(h, dict) else h, 1200).lstrip("•-*● ")
            if text:
                out.append(text)
    return out


def _entry(
    *,
    heading: str,
    subheading: str = "",
    timeframe: str = "",
    location: str = "",
    note: str = "",
    highlights: list[str] | None = None,
) -> dict:
    """A uniform, render-ready CV entry (no bullet chars; fields are separate)."""

    return {
        "heading": heading,
        "subheading": subheading,
        "timeframe": timeframe,
        "location": location,
        "note": note,
        "highlights": highlights or [],
    }


def _entries(raw: object, mapper) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:40]:
        if not isinstance(item, dict):
            continue
        entry = mapper(item)
        # Keep an entry only if it carries a heading or any highlight.
        if entry["heading"] or entry["highlights"]:
            out.append(entry)
    return out


def _skill_items(raw: object, *, numeric: bool) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:60]:
        if isinstance(item, dict):
            name = _short(item.get("name"), 200)
            level_raw = item.get("level")
        else:
            name, level_raw = _short(item, 200), None
        if not name:
            continue
        if numeric:
            level: object = None
            if isinstance(level_raw, bool):
                level = None
            elif isinstance(level_raw, (int, float)):
                level = max(0, min(100, int(level_raw)))
            elif isinstance(level_raw, str) and level_raw.strip().rstrip("%").isdigit():
                level = max(0, min(100, int(level_raw.strip().rstrip("%"))))
            out.append({"name": name, "level": level})
        else:
            out.append({"name": name, "level": _short(level_raw, 60) or None})
    return out


def _text_items(raw: object, limit: int) -> list[dict]:
    out: list[dict] = []
    if isinstance(raw, list):
        for value in raw[:40]:
            text = _clean(value.get("text") if isinstance(value, dict) else value, limit)
            if text:
                out.append({"text": text})
    elif isinstance(raw, str):
        text = _clean(raw, limit)
        if text:
            out.append({"text": text})
    return out


# section_type -> a mapper turning the model's raw entry dict into a uniform entry.
_ENTRY_MAPPERS = {
    "experience": lambda e: _entry(
        heading=_short(e.get("role")),
        subheading=_short(e.get("organization")),
        timeframe=_timeframe(e),
        location=_short(e.get("location")),
        highlights=_highlights(e),
    ),
    "education": lambda e: _entry(
        heading=_short(e.get("degree")),
        subheading=_short(e.get("school")),
        timeframe=_timeframe(e),
        location=_short(e.get("location")),
        note=(f"GPA: {_short(e.get('gpa'), 40)}" if _short(e.get("gpa"), 40) else ""),
        highlights=_highlights(e),
    ),
    "projects": lambda e: _entry(
        heading=_short(e.get("name")),
        subheading=_short(e.get("role")),
        timeframe=_timeframe(e),
        highlights=_highlights(e),
    ),
    "activities": lambda e: _entry(
        heading=_short(e.get("role")) or _short(e.get("name")),
        subheading=_short(e.get("organization")),
        timeframe=_timeframe(e),
        highlights=_highlights(e),
    ),
    "certifications": lambda e: _entry(
        heading=_short(e.get("name")),
        subheading=_short(e.get("issuer")),
        timeframe=_short(e.get("date"), 60),
    ),
    "awards": lambda e: _entry(
        heading=_short(e.get("title")) or _short(e.get("name")),
        subheading=_short(e.get("issuer")),
        timeframe=_short(e.get("date"), 60),
    ),
    "publications": lambda e: _entry(
        heading=_short(e.get("title")),
        timeframe=_short(e.get("date"), 60),
    ),
    "references": lambda e: _entry(
        heading=_short(e.get("name")),
        subheading=_short(e.get("role")),
        note=_short(e.get("contact"), 200),
    ),
}

_ALL_SECTIONS = (
    "summary", "experience", "education", "projects", "skills", "languages",
    "certifications", "awards", "activities", "interests", "publications", "references",
)


def _normalize(parsed: dict) -> dict | None:
    """Coerce the model output into the canonical STRUCTURED extracted-data shape.

    Entry sections become ``{"entries": [{heading, subheading, timeframe, location,
    note, highlights[]}]}`` (no bullet characters, fields kept separate); skills and
    languages become ``{"items": [{name, level}]}``; summary/interests become
    ``{"items": [{text}]}``. Only allowlisted keys survive and text is sanitised.
    Returns ``None`` when the result carries no usable CV signal.
    """

    if parsed.get("is_cv") is False:
        return None

    contact_in = parsed.get("contact")
    contact_in = contact_in if isinstance(contact_in, dict) else {}
    contact = {
        key: _short(contact_in.get(key), 300)
        for key in ("name", "headline", "email", "phone", "location", "links")
        if _short(contact_in.get(key), 300)
    }

    extracted: dict = {"contact": contact}

    summary = _text_items(parsed.get("summary"), 2000)
    if summary:
        extracted["summary"] = {"items": summary}
    interests = _text_items(parsed.get("interests"), 200)
    if interests:
        extracted["interests"] = {"items": interests}

    for section_type, mapper in _ENTRY_MAPPERS.items():
        entries = _entries(parsed.get(section_type), mapper)
        if entries:
            extracted[section_type] = {"entries": entries}

    skills = _skill_items(parsed.get("skills"), numeric=True)
    if skills:
        extracted["skills"] = {"items": skills}
    languages = _skill_items(parsed.get("languages"), numeric=False)
    if languages:
        extracted["languages"] = {"items": languages}

    has_contact = any(contact.get(k) for k in ("name", "email", "phone"))
    has_section = any(st in extracted for st in _ALL_SECTIONS)
    if not has_contact and not has_section:
        return None

    language = parsed.get("detected_language")
    if language not in ("vi", "en"):
        language = cv_structuring._detect_language(  # noqa: SLF001
            " ".join(
                f["heading"] + " " + " ".join(f["highlights"])
                for st in _ENTRY_MAPPERS
                for f in extracted.get(st, {}).get("entries", [])
            )
            or (summary[0]["text"] if summary else "")
        )

    return {
        "extracted_data": extracted,
        "review_fields": [],  # no manual field-review step (owner decision 2026-07-05)
        "detected_language": language,
    }


# --------------------------------------------------------------------------- #
# Process-wide adapter seam (mirrors OCR / structuring adapters)               #
# --------------------------------------------------------------------------- #

_vision_adapter: VisionExtractionEngine | None = None


def get_vision_adapter() -> VisionExtractionEngine:
    """Process-wide vision adapter. Gateway-backed by default; overridable in tests."""

    global _vision_adapter
    if _vision_adapter is None:
        _vision_adapter = GatewayVisionExtractionAdapter()
    return _vision_adapter


def set_vision_adapter(adapter: VisionExtractionEngine | None) -> None:
    """Override the vision adapter (test seam). ``None`` resets to the default."""

    global _vision_adapter
    _vision_adapter = adapter


def run_vision_extraction(
    data: bytes,
    kind: FileKind,
    *,
    enabled: bool,
    max_image_px: int,
    max_pages: int,
    native_text: str | None = None,
) -> dict | None:
    """Run the vision tier if enabled and available. Best-effort; never raises.

    ``native_text`` (PDF only) is passed to the model as reference so it uses the
    exact embedded characters for emails/phones/dates while reading structure from
    the page image; it is redacted for secrets before the call.
    """

    if not enabled:
        return None
    adapter = get_vision_adapter()
    if not adapter.available:
        return None
    try:
        return adapter.extract(
            data,
            kind,
            max_image_px=max_image_px,
            max_pages=max_pages,
            native_text=native_text,
        )
    except Exception:  # noqa: BLE001 - vision is a best-effort fallback tier
        return None


__all__ = [
    "VisionExtractionEngine",
    "DisabledVisionExtractionAdapter",
    "GatewayVisionExtractionAdapter",
    "get_vision_adapter",
    "set_vision_adapter",
    "run_vision_extraction",
]
