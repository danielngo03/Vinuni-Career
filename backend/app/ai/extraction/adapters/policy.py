"""Engine-policy resolution: configured engine -> EFFECTIVE engine.

Resolves the lightweight, availability-gated engine set for the ingestion cascade
(``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §4). The effective engine is the
configured one when its dependency is importable, otherwise the documented
fallback:

- native PDF: ``pymupdf4llm`` if importable, else ``pdfplumber``;
- layout: configured engine if importable, else ``none``;
- OCR: configured engine if its binding is present, else ``none`` (cascade then
  records ``LOW_QUALITY_SCAN``);
- LLM structuring: enabled only when the flag is on AND an adapter is available.

All values here are INTERNAL — engine names never reach a user-facing response.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.extraction.adapters.layout import layout_engine_available
from app.ai.extraction.adapters.native_text import pymupdf_available
from app.ai.extraction.adapters.ocr import get_ocr_adapter
from app.ai.extraction.adapters.structuring import get_llm_structuring_adapter
from app.ai.extraction.adapters.vision import get_vision_adapter
from app.ai.gateway import runtime_config
from app.core.config import Settings, get_settings


@dataclass(slots=True)
class EnginePolicy:
    native_pdf: str
    layout: str
    ocr: str
    ocr_langs: str
    llm_enabled: bool
    llm_provider_alias: str
    async_enabled: bool
    vision_enabled: bool = False
    vision_provider_alias: str = "vision_default"
    vision_max_image_px: int = 2200
    vision_max_pages: int = 4


def _resolve_native_pdf(configured: str) -> str:
    if configured == "pymupdf4llm" and pymupdf_available():
        return "pymupdf4llm"
    return "pdfplumber"


def _resolve_layout(configured: str) -> str:
    return configured if layout_engine_available(configured) else "none"


def _resolve_ocr(configured: str) -> str:
    if configured in ("", "none"):
        return "none"
    if configured == "tesseract":
        return "tesseract" if get_ocr_adapter().available else "none"
    # docling/marker OCR engines are not installed by default.
    return "none"


def resolve_policy(settings: Settings | None = None) -> EnginePolicy:
    s = settings or get_settings()
    # The cv-llm structuring flag is read from the resolved runtime snapshot so an
    # admin PATCH (or the startup resolver) governs it, not just static env
    # (ADR-0011 §2). In bootstrap mode the snapshot mirrors env, so behaviour is
    # preserved for env-driven callers.
    llm_enabled = (
        runtime_config.current().cv_llm_structuring_enabled
        and get_llm_structuring_adapter().available
    )
    # Vision extraction is gated on the env/admin flag AND a usable multimodal
    # route (real calls active + key). In offline/test runs the adapter reports
    # unavailable, so this resolves to False and the cascade never sends images.
    vision_enabled = s.cv_vision_extraction_enabled and get_vision_adapter().available
    return EnginePolicy(
        native_pdf=_resolve_native_pdf(s.cv_native_pdf_engine),
        layout=_resolve_layout(s.cv_layout_engine),
        ocr=_resolve_ocr(s.cv_ocr_engine),
        ocr_langs=s.cv_ocr_langs,
        llm_enabled=llm_enabled,
        llm_provider_alias=s.cv_llm_structuring_provider_alias,
        async_enabled=bool(s.cv_ingestion_async),
        vision_enabled=vision_enabled,
        vision_provider_alias=s.cv_vision_provider_alias,
        vision_max_image_px=s.cv_vision_max_image_px,
        vision_max_pages=s.cv_vision_max_pages,
    )


__all__ = ["EnginePolicy", "resolve_policy"]
