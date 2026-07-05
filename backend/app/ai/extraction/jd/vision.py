"""Vision-LLM tier for JD extraction: image / scanned-PDF JD -> structured JSON.

Runs ONLY when native text is insufficient (never on digital text PDFs). Images
are downscaled and scanned PDFs send at most ``max_pages`` rasterized pages. The
model id is resolved via an alias and never exposed. Gateway-backed by default;
a disabled adapter is used offline/in tests. Best-effort — never raises.

Image-prep helpers are copied JD-local (kept independent from the CV vision
adapter so a concurrent CV session can evolve that file freely).
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Protocol, runtime_checkable

import httpx

from app.ai.extraction.adapters.base import redact_secrets
from app.ai.extraction.text_extraction import FileKind
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.ai.prompts.jd_extraction import v2 as prompt
from app.core.config import get_settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_MAX_OUTPUT_TOKENS = 3000
_MAX_NATIVE_TEXT_CHARS = 8000
_NO_KEY_PROVIDERS = {"ollama-local", "ollama"}
_NATIVE_TEXT_PREFIX = (
    "For reference, here is the raw text embedded in the document. Reading ORDER "
    "may be scrambled; rely on the image(s) for structure but use this text for the "
    "EXACT spelling of numbers, emails, and dates. RAW TEXT:\n"
)


@runtime_checkable
class JdVisionEngine(Protocol):
    @property
    def available(self) -> bool: ...

    def extract(self, data: bytes, kind: FileKind, *, max_image_px: int,
                max_pages: int, native_text: str | None = None) -> dict | None: ...


class DisabledJdVisionAdapter:
    engine_family = "jd_vision_llm"
    engine_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        return None


class GatewayJdVisionAdapter:
    engine_family = "jd_vision_llm_gateway"
    engine_version = "v2"

    def _alias(self, cfg: runtime_config.EffectiveAiConfig) -> str:
        configured = get_settings().jd_vision_provider_alias
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

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        cfg = runtime_config.current()
        route = cfg.provider_routes.get(self._alias(cfg))
        if route is None:
            return None
        provider_name, base_url, model_id = route
        api_key = _get_api_key(provider_name)
        if not api_key and provider_name not in _NO_KEY_PROVIDERS:
            return None

        images = _prepare_images(data, kind, max_px=max_image_px, max_pages=max_pages)
        if not images:
            return None

        content: list[dict] = [{"type": "text", "text": prompt.VISION_USER_PROMPT}]
        if native_text and native_text.strip():
            redacted = redact_secrets(native_text)[:_MAX_NATIVE_TEXT_CHARS]
            content.append({"type": "text", "text": _NATIVE_TEXT_PREFIX + redacted})
        for jpeg in images:
            b64 = base64.b64encode(jpeg).decode("ascii")
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": prompt.VISION_SYSTEM_PROMPT},
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
        try:
            with httpx.Client(timeout=float(get_settings().jd_extraction_max_seconds)) as client:
                resp = client.post(f"{base_url.rstrip('/')}/chat/completions",
                                   json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        choice = (body.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content", "")
        if isinstance(raw, list):
            raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
        return _extract_json(scrub_text(raw or ""))


# ---- JD-local image prep (independent copy; do not import from CV vision) ----

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
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
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
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# ---- process-wide seam (mirrors OCR/vision adapter seams) --------------------

_adapter: JdVisionEngine | None = None


def get_jd_vision_adapter() -> JdVisionEngine:
    global _adapter
    if _adapter is None:
        _adapter = GatewayJdVisionAdapter()
    return _adapter


def set_jd_vision_adapter(adapter: JdVisionEngine | None) -> None:
    global _adapter
    _adapter = adapter


def run_jd_vision_extraction(data: bytes, kind: FileKind, *, enabled: bool,
                             max_image_px: int, max_pages: int,
                             native_text: str | None = None) -> dict | None:
    """Run the JD vision tier if enabled + available. Best-effort; never raises."""
    if not enabled:
        return None
    adapter = get_jd_vision_adapter()
    if not adapter.available:
        return None
    try:
        return adapter.extract(data, kind, max_image_px=max_image_px,
                               max_pages=max_pages, native_text=native_text)
    except Exception:  # noqa: BLE001 - vision is best-effort
        return None


__all__ = [
    "JdVisionEngine", "DisabledJdVisionAdapter", "GatewayJdVisionAdapter",
    "get_jd_vision_adapter", "set_jd_vision_adapter", "run_jd_vision_extraction",
]
