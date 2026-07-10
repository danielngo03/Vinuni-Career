"""Gemini image-generation adapter (recruiting/employer-branding content).

Runs on a Google/Vertex GenAI credential via ``google-genai`` — the exact same
client/auth paths as the speech tier (``app.ai.gateway.speech.service``): a
Vertex *express* API key (``genai.Client(vertexai=True, api_key=...)``), an
AI-Studio developer key, or a service-account ADC bound to a Vertex project.

Offline mode is mandatory: when ``AI_REAL_CALLS_ENABLED`` is false or no
credential is configured, :func:`generate_image` returns a deterministic tiny
placeholder PNG (pure-python, zero network) so tests and local dev are free.
``ImageResult.real_call`` tells the caller whether a billable provider call
actually happened (metering must charge only real generations).

Leak-safety: callers receive only PNG bytes + dimensions. Model ids, provider
names, and raw provider errors never leave this module — failures surface as
:class:`ImageUnavailableError` with a leak-safe ``reason`` token only, and
usage is logged as metadata under the leak-safe alias.
"""

from __future__ import annotations

import asyncio
import io
import logging
import struct
import uuid
import zlib
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Leak-safe task label surfaced in usage logs (never the concrete model id).
_TASK_TYPE = "ai_image_generation"

_PLACEHOLDERS = {"", "changeme", "your-key", "placeholder", "none", "null"}

# Supported output framings. Longest side is capped by ``ai_image_max_px``.
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
}
DEFAULT_ASPECT_RATIO = "1:1"

# Hard ceiling on the provider's inline image payload (defense against a
# runaway response blowing memory / the DB row).
_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
# Wall-clock budget for one provider round-trip.
_CALL_TIMEOUT_SECONDS = 60

# English system-style framing prepended INSIDE this service call (prompt-language
# rule): the user's request is embedded after it, already sanitized by the caller.
_PROMPT_FRAME = (
    "Generate a single professional image for a university career platform's "
    "recruiting and employer-branding content (job postings, career events, "
    "company pages, campus hiring campaigns). Style: clean, modern, "
    "workplace-appropriate, suitable for a professional audience. Do NOT "
    "include any real person's likeness, any third-party logo or trademark, "
    "or any political, sexual, or violent content. Request: "
)


class ImageUnavailableError(RuntimeError):
    """Raised when the image tier is disabled, unconfigured, or the call fails.

    Carries only a leak-safe ``reason`` token — never a provider/model string.
    """

    def __init__(self, reason: str = "unavailable") -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ImageResult:
    """One generated image: PNG bytes + dimensions + whether a real call ran."""

    png: bytes
    width: int
    height: int
    real_call: bool


def _image_key() -> str:
    """Resolve the Google GenAI key (same precedence as the speech tier)."""

    import os

    s = get_settings()
    for candidate in (
        # google_api_key is the canonical field (GEMINI_API_KEY retired 2026-07-11);
        # keep the legacy attr + env names as fallbacks for older local .env files.
        getattr(s, "google_api_key", "") or "",
        getattr(s, "gemini_api_key", "") or "",
        os.environ.get("GOOGLE_API_KEY", ""),
        os.environ.get("GEMINI_API_KEY", ""),
    ):
        cand = (candidate or "").strip()
        if cand and cand.lower() not in _PLACEHOLDERS:
            return cand
    return ""


def _has_adc() -> bool:
    import os

    s = get_settings()
    project = getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    cred = getattr(s, "google_application_credentials", "") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    )
    return bool(getattr(s, "ai_image_use_vertex", True) and cred and project)


def image_enabled() -> bool:
    """True when the tier is switched on (a credential unlocks REAL calls only;
    the offline placeholder path needs no credential)."""

    return bool(getattr(get_settings(), "ai_image_enabled", False))


def _real_generation_possible() -> bool:
    s = get_settings()
    if not getattr(s, "ai_real_calls_enabled", False):
        return False
    return bool(_image_key()) or _has_adc()


_client_cache: object | None = None


def _client_candidates() -> list[object]:
    """Build the ordered GenAI client candidates (same auth setups as speech).

    Returns the cached known-good client when one is established, else every
    configured auth path in preference order: express/AI-Studio API key first,
    then service-account ADC. Image models are NOT always enabled for express
    keys (observed: 403 CONSUMER_INVALID on the express project while the same
    model works via ADC), so ``_call_provider`` tries each candidate and caches
    whichever one actually served an image.
    """

    import os

    if _client_cache is not None:
        return [_client_cache]
    try:
        from google import genai  # deferred import; heavy dep
    except Exception as exc:  # pragma: no cover - dependency missing
        raise ImageUnavailableError("sdk_missing") from exc
    s = get_settings()
    use_vertex = bool(getattr(s, "ai_image_use_vertex", True))
    project = (
        getattr(s, "google_cloud_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    ).strip()
    location = (
        getattr(s, "google_cloud_location", "")
        or os.environ.get("GOOGLE_CLOUD_LOCATION", "")
        or "global"
    ).strip()
    cred_path = (
        getattr(s, "google_application_credentials", "")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    ).strip()
    if cred_path and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
    key = _image_key()
    candidates: list[object] = []
    try:
        if key:
            # Express Vertex key (use_vertex=true) or AI-Studio developer key.
            candidates.append(genai.Client(vertexai=use_vertex, api_key=key))
        if use_vertex and cred_path and project:
            # Service-account / ADC path (full quota; also the fallback when the
            # express key's project has no access to the image model).
            candidates.append(genai.Client(vertexai=True, project=project, location=location))
    except Exception as exc:  # pragma: no cover - misconfig
        logger.warning("image.client_init_failed", exc_info=True)
        if not candidates:
            raise ImageUnavailableError("client_init") from exc
    if not candidates:
        raise ImageUnavailableError("no_key")
    return candidates


# --------------------------------------------------------------------------- #
# Deterministic offline placeholder (pure python, zero network)                #
# --------------------------------------------------------------------------- #

# Longest side of the offline placeholder — deliberately tiny (stored in the DB).
_PLACEHOLDER_LONG_SIDE = 64
_PLACEHOLDER_RGB = (79, 70, 229)  # indigo, matching the data-viz palette


def _dims_for(aspect_ratio: str, long_side: int) -> tuple[int, int]:
    w_ratio, h_ratio = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS[DEFAULT_ASPECT_RATIO])
    if w_ratio >= h_ratio:
        width = long_side
        height = max(1, round(long_side * h_ratio / w_ratio))
    else:
        height = long_side
        width = max(1, round(long_side * w_ratio / h_ratio))
    return width, height


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def placeholder_png(aspect_ratio: str = DEFAULT_ASPECT_RATIO) -> tuple[bytes, int, int]:
    """Deterministic solid-color PNG (offline mode). Returns ``(bytes, w, h)``."""

    width, height = _dims_for(aspect_ratio, _PLACEHOLDER_LONG_SIDE)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(_PLACEHOLDER_RGB) * width
    idat = zlib.compress(row * height)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    return png, width, height


# --------------------------------------------------------------------------- #
# Post-processing                                                              #
# --------------------------------------------------------------------------- #


def _normalize_png(raw: bytes, max_px: int) -> tuple[bytes, int, int]:
    """Re-encode to PNG and cap the longest side at ``max_px`` (Pillow).

    Falls back to the raw bytes (dimensions best-effort) if Pillow is somehow
    unavailable — pyproject pins pillow, so this is a belt-and-braces branch.
    """

    try:
        from PIL import Image
    except Exception:  # pragma: no cover - pillow is a hard dependency
        return raw, 0, 0

    with Image.open(io.BytesIO(raw)) as loaded:
        loaded.load()
        img: Image.Image = loaded
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        width, height = img.size
        longest = max(width, height)
        if max_px > 0 and longest > max_px:
            scale = max_px / float(longest)
            img = img.resize(
                (max(1, round(width * scale)), max(1, round(height * scale)))
            )
            width, height = img.size
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), width, height


async def _log_usage(
    session: object | None,
    *,
    success: bool,
    chars: int,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
) -> None:
    """Best-effort metadata usage log; never raises, never blocks correctness."""

    if session is None:
        return
    try:
        from app.ai.observability.usage import log_ai_usage_async

        await log_ai_usage_async(
            session,  # type: ignore[arg-type]
            task_type=_TASK_TYPE,
            alias=getattr(get_settings(), "ai_image_model_alias", "image_default"),
            success=success,
            prompt_chars=chars,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:  # pragma: no cover - observability must never break calls
        logger.debug("image.usage_log_failed", exc_info=True)


# --------------------------------------------------------------------------- #
# Generation                                                                   #
# --------------------------------------------------------------------------- #


def _extract_image_bytes(resp: object) -> bytes:
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = (getattr(inline, "mime_type", "") or "").lower()
            if data and (not mime or mime.startswith("image/")):
                return bytes(data)
    raise ImageUnavailableError("empty_image")


def _call_provider(prompt: str, aspect_ratio: str) -> bytes:
    """One blocking provider round-trip; returns raw image bytes.

    Tries every configured auth candidate (express key, then ADC) × config
    shape, and caches whichever client actually serves an image so later calls
    skip the failing path.
    """

    from google.genai import types

    global _client_cache
    model = getattr(get_settings(), "ai_image_model", "gemini-2.5-flash-image")

    configs: list[object] = []
    try:
        configs.append(
            types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            )
        )
    except Exception:  # SDK without ImageConfig — fall through to the plain config
        pass
    configs.append(types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))

    last_exc: Exception | None = None
    empty_result = False
    for client in _client_candidates():
        for cfg in configs:
            try:
                resp = client.models.generate_content(  # type: ignore[attr-defined]
                    model=model, contents=prompt, config=cfg
                )
                png = _extract_image_bytes(resp)
                _client_cache = client
                return png
            except ImageUnavailableError:
                # No image in an otherwise-successful response (e.g. safety
                # refusal) — don't burn the remaining auth candidates on it.
                empty_result = True
                break
            except Exception as exc:  # noqa: BLE001 - try the next config/candidate
                last_exc = exc
        if empty_result:
            break
    if empty_result and last_exc is None:
        raise ImageUnavailableError("empty_image")
    raise ImageUnavailableError("generation_failed") from last_exc


async def generate_image(
    prompt: str,
    *,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    style_hint: str | None = None,
    session: object | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> ImageResult:
    """Generate one PNG for a (pre-sanitized) prompt.

    Offline mode (real calls disabled / no credential) returns the deterministic
    placeholder with ``real_call=False`` — callers must NOT meter that path.
    Raises :class:`ImageUnavailableError` when the tier is disabled, the prompt
    is empty, or a real provider call fails.
    """

    s = get_settings()
    if not getattr(s, "ai_image_enabled", False):
        raise ImageUnavailableError("disabled")
    clean = (prompt or "").strip()
    if not clean:
        raise ImageUnavailableError("empty_prompt")
    max_chars = int(getattr(s, "ai_image_max_prompt_chars", 600))
    clean = clean[:max_chars]
    if aspect_ratio not in ASPECT_RATIOS:
        aspect_ratio = DEFAULT_ASPECT_RATIO

    if not _real_generation_possible():
        png, width, height = placeholder_png(aspect_ratio)
        return ImageResult(png=png, width=width, height=height, real_call=False)

    framed = _PROMPT_FRAME + clean
    if style_hint:
        framed += f" Style hint: {str(style_hint).strip()[:120]}."

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_call_provider, framed, aspect_ratio),
            timeout=_CALL_TIMEOUT_SECONDS,
        )
    except ImageUnavailableError:
        await _log_usage(
            session, success=False, chars=len(clean), user_id=user_id, session_id=session_id
        )
        raise
    except TimeoutError as exc:
        await _log_usage(
            session, success=False, chars=len(clean), user_id=user_id, session_id=session_id
        )
        raise ImageUnavailableError("timeout") from exc
    except Exception as exc:  # noqa: BLE001 - any provider/transport error
        logger.warning("image.generation_failed", exc_info=True)
        await _log_usage(
            session, success=False, chars=len(clean), user_id=user_id, session_id=session_id
        )
        raise ImageUnavailableError("generation_failed") from exc

    if len(raw) > _MAX_RESPONSE_BYTES:
        await _log_usage(
            session, success=False, chars=len(clean), user_id=user_id, session_id=session_id
        )
        raise ImageUnavailableError("response_too_large")

    try:
        png, width, height = _normalize_png(raw, int(getattr(s, "ai_image_max_px", 1024)))
    except Exception as exc:  # noqa: BLE001 - corrupt provider payload
        await _log_usage(
            session, success=False, chars=len(clean), user_id=user_id, session_id=session_id
        )
        raise ImageUnavailableError("decode_failed") from exc

    await _log_usage(
        session, success=True, chars=len(clean), user_id=user_id, session_id=session_id
    )
    return ImageResult(png=png, width=width, height=height, real_call=True)
