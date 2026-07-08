"""Adapter-based CV ingestion extraction stages.

Each stage is a swappable, availability-gated adapter so product logic never
depends on one parser library (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3).
"""

from app.ai.extraction.adapters.base import (
    OCR_TRIGGER_THRESHOLD,
    ExtractionSignals,
    is_cid_corrupted,
    is_disordered,
    redact_secrets,
)
from app.ai.extraction.adapters.layout import LayoutAdapter, layout_engine_available
from app.ai.extraction.adapters.native_text import NativeTextAdapter, pymupdf_available
from app.ai.extraction.adapters.ocr import (
    OcrEngine,
    TesseractOcrAdapter,
    get_ocr_adapter,
    set_ocr_adapter,
)
from app.ai.extraction.adapters.policy import EnginePolicy, resolve_policy
from app.ai.extraction.adapters.structuring import (
    DisabledLlmStructuringAdapter,
    GatewayLlmStructuringAdapter,
    LlmStructuringEngine,
    StructuringAdapter,
    get_llm_structuring_adapter,
    run_llm_structuring,
    set_llm_structuring_adapter,
)
from app.ai.extraction.adapters.vision import (
    DisabledVisionExtractionAdapter,
    GatewayVisionExtractionAdapter,
    VisionExtractionEngine,
    get_vision_adapter,
    run_vision_extraction,
    set_vision_adapter,
)

__all__ = [
    "OCR_TRIGGER_THRESHOLD",
    "ExtractionSignals",
    "is_cid_corrupted",
    "is_disordered",
    "redact_secrets",
    "LayoutAdapter",
    "layout_engine_available",
    "NativeTextAdapter",
    "pymupdf_available",
    "OcrEngine",
    "TesseractOcrAdapter",
    "get_ocr_adapter",
    "set_ocr_adapter",
    "EnginePolicy",
    "resolve_policy",
    "StructuringAdapter",
    "LlmStructuringEngine",
    "DisabledLlmStructuringAdapter",
    "GatewayLlmStructuringAdapter",
    "get_llm_structuring_adapter",
    "run_llm_structuring",
    "set_llm_structuring_adapter",
    "VisionExtractionEngine",
    "DisabledVisionExtractionAdapter",
    "GatewayVisionExtractionAdapter",
    "get_vision_adapter",
    "set_vision_adapter",
    "run_vision_extraction",
]
