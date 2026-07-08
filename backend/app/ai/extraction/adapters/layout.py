"""Layout-aware extraction adapter (dependency-gated, no-op by default).

Layout re-flow runs only when native text looks disordered/column-merged AND a
layout engine is both configured (``cv_layout_engine``) and importable. The
preferred local candidates (``pymupdf4llm``/``docling``) and the heavy
``marker`` engine are NOT installed by default, so this stage is a safe no-op
that simply records that no layout engine was available
(``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3.3 / §4).

The interface is kept clean so a real layout engine can be slotted in later
without touching the cascade logic.
"""

from __future__ import annotations

from app.ai.extraction.adapters.base import ExtractionSignals


def layout_engine_available(engine: str) -> bool:
    """True when the configured layout engine can be imported."""

    if engine in ("", "none"):
        return False
    try:
        if engine == "pymupdf4llm":
            import pymupdf4llm  # noqa: F401

            return True
        if engine == "docling":
            import docling  # noqa: F401

            return True
        if engine == "marker":
            import marker  # noqa: F401

            return True
    except Exception:  # noqa: BLE001
        return False
    return False


class LayoutAdapter:
    """Re-extract a column-heavy document with a layout-aware engine.

    Default ``engine='none'`` -> :meth:`improve` returns ``None`` (skip).
    """

    engine_family = "layout"

    def __init__(self, engine: str = "none") -> None:
        self.engine = engine if layout_engine_available(engine) else "none"

    @property
    def available(self) -> bool:
        return self.engine != "none"

    def improve(
        self, filename: str, data: bytes, native: ExtractionSignals
    ) -> ExtractionSignals | None:
        """Return improved signals, or ``None`` when no layout engine is wired."""

        if not self.available:
            return None
        # A real engine would re-extract here; the importable-engine branch is the
        # integration seam. No default engine ships, so this stays None in v1.
        return None


__all__ = ["LayoutAdapter", "layout_engine_available"]
