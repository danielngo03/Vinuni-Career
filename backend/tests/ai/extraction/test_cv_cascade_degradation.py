"""CV ingestion cascade degradation matrix (pure, no DB, no real model calls).

Verifies WS-9 resilience for the extraction cascade: with the PAID tiers off
(the default offline policy, i.e. AI disabled/unavailable) or deliberately
withheld (``ai_gated`` — student out of AI energy), the cascade

- still extracts native-text CVs OFFLINE (free, no fabrication);
- returns a user-safe ``LOW_QUALITY_SCAN`` for an unreadable scan when AI is
  simply absent, and a retryable ``ai_unavailable`` (EXTRACTION_PENDING_AI) when
  the paid tier was gated;
- rejects blank / not-CV / corrupt / password / duplicate WITHOUT fabricating a
  CV, and reports which tier ran so the service can charge only the paid tiers.

No credits are asserted here (that is the service-layer metering test); this file
proves the cascade never fabricates and reports the right diagnostics.
"""

from __future__ import annotations

import pytest
from app.ai.extraction import cv_ingestion_cascade, cv_validation
from app.ai.extraction.adapters import (
    ExtractionSignals,
    resolve_policy,
    set_vision_adapter,
)
from app.ai.extraction.cv_ingestion_cascade import run_cascade
from app.ai.extraction.cv_structuring import review_fields_for_extracted
from app.ai.extraction.text_extraction import ExtractionError

from tests.fixtures import cv as F

_MAX = 50 * 1024 * 1024


def _run(filename, data, *, ai_gated=False, existing=()):
    return run_cascade(
        filename, data, max_bytes=_MAX, existing_checksums=list(existing),
        policy=resolve_policy(), ai_gated=ai_gated,
    )


# --------------------------------------------------------------------------- #
# Native-text tiers extract OFFLINE (free) with AI disabled — no fabrication    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "builder", "language"),
    [
        ("cv.pdf", F.text_pdf_en, "en"),
        ("cv.txt", F.vietnamese_cv_txt, "vi"),
        ("two.pdf", F.two_column_pdf, "en"),
        ("cv.docx", F.docx_cv, "en"),
        ("cv-vi.docx", F.vietnamese_docx_cv, "vi"),
    ],
)
def test_native_text_extracts_offline_free(filename, builder, language) -> None:
    outcome = _run(filename, builder())
    assert outcome.accepted is True
    assert outcome.quality_code == "REVIEW_REQUIRED"
    assert outcome.detected_language == language
    assert outcome.extracted_data  # real structured data, not fabricated-empty
    # No PAID tier ran → the service charges nothing.
    assert outcome.vision_used is False
    assert outcome.llm_used is False
    assert outcome.vision_attempted is False
    assert outcome.ai_unavailable is False


def test_native_text_extracts_even_when_energy_gated() -> None:
    # Out of AI energy must NOT block a free native-text extraction — the paid
    # tier is what is withheld, not the free deterministic path.
    outcome = _run("cv.pdf", F.text_pdf_en(), ai_gated=True)
    assert outcome.accepted is True
    assert outcome.quality_code == "REVIEW_REQUIRED"
    assert outcome.ai_unavailable is False
    assert outcome.vision_used is False and outcome.llm_used is False


# --------------------------------------------------------------------------- #
# Scanned / sparse docs need a paid tier — degrade safely, never fabricate      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "builder", "content"),
    [
        ("scan.png", F.scanned_image_cv, "image/png"),
        ("sparse.pdf", F.sparse_canvas_pdf, "application/pdf"),
    ],
)
def test_scan_without_ai_is_low_quality_scan(filename, builder, content) -> None:
    # AI absent (offline default policy) + no OCR → user-safe LOW_QUALITY_SCAN,
    # never a fabricated CV, never a charge signal.
    outcome = _run(filename, builder(), ai_gated=False)
    assert outcome.accepted is False
    assert outcome.quality_code == "LOW_QUALITY_SCAN"
    assert outcome.ai_unavailable is False
    assert outcome.extracted_data is None
    assert outcome.review_fields == []
    assert outcome.vision_used is False and outcome.llm_used is False


@pytest.mark.parametrize(
    ("filename", "builder"),
    [("scan.png", F.scanned_image_cv), ("sparse.pdf", F.sparse_canvas_pdf)],
)
def test_scan_when_energy_gated_is_ai_unavailable(filename, builder) -> None:
    # Same scan, but the paid tier was WITHHELD (energy exhausted) → a retryable
    # "extraction pending" state distinct from a genuinely bad scan.
    outcome = _run(filename, builder(), ai_gated=True)
    assert outcome.accepted is False
    assert outcome.ai_unavailable is True
    assert outcome.quality_code == "EXTRACTION_PENDING_AI"
    assert outcome.extracted_data is None  # never fabricated
    assert outcome.vision_used is False and outcome.llm_used is False
    # The user-safe copy is a retry message, not a "your file is bad" message.
    _vi, _en, recover, actions = cv_validation.copy_for("EXTRACTION_PENDING_AI")
    assert recover == "retry"
    assert "retry_extraction" in actions


# --------------------------------------------------------------------------- #
# Hard rejects are never fabricated into a CV (blank / not-CV / corrupt / dup)   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filename", "builder", "expected"),
    [
        ("blank.pdf", F.blank_pdf, "BLANK_DOCUMENT"),
        ("notes.pdf", F.not_cv_pdf, "NOT_A_CV"),
        ("broken.pdf", F.corrupt_pdf, "CORRUPT_FILE"),
    ],
)
def test_hard_rejects_never_fabricate(filename, builder, expected) -> None:
    outcome = _run(filename, builder())
    assert outcome.accepted is False
    assert outcome.quality_code == expected
    assert outcome.extracted_data is None
    assert outcome.review_fields == []
    assert outcome.vision_used is False and outcome.llm_used is False


def test_duplicate_detected_before_any_extraction() -> None:
    data = F.text_pdf_en()
    checksum = cv_validation.compute_checksum(data)
    outcome = _run("cv.pdf", data, existing=(checksum,))
    assert outcome.accepted is False
    assert outcome.quality_code == "DUPLICATE_FILE"
    assert outcome.extracted_data is None


def test_password_protected_never_fabricates(monkeypatch) -> None:
    class LockedAdapter:
        def __init__(self, *_a, **_k) -> None: ...

        def extract(self, filename, data):
            raise ExtractionError("PASSWORD_PROTECTED_FILE")

    monkeypatch.setattr(cv_ingestion_cascade, "NativeTextAdapter", LockedAdapter)
    outcome = _run("locked.pdf", F.text_pdf_en())
    assert outcome.accepted is False
    assert outcome.quality_code == "PASSWORD_PROTECTED_FILE"
    assert outcome.extracted_data is None


# --------------------------------------------------------------------------- #
# LLM disabled/unavailable: the deterministic text path stays authoritative     #
# --------------------------------------------------------------------------- #


def test_llm_disabled_text_path_is_authoritative_and_free() -> None:
    policy = resolve_policy()
    # Offline default: neither the text-LLM structuring tier nor vision runs.
    assert policy.llm_enabled is False
    assert policy.vision_enabled is False
    outcome = run_cascade(
        "cv.pdf", F.text_pdf_en(), max_bytes=_MAX, policy=policy
    )
    assert outcome.accepted is True
    assert outcome.llm_used is False
    assert outcome.vision_used is False
    assert outcome.extracted_data  # deterministic structuring produced real data


# --------------------------------------------------------------------------- #
# Cost-tiered vision SELECTION (2026-07-08): a clean native-text PDF is served  #
# by the FREE tier and never invokes the paid vision model, even when vision is #
# fully enabled; only insufficient (sparse / garbled) native text escalates.    #
# --------------------------------------------------------------------------- #


class _SpyVision:
    """Vision engine that COUNTS calls (available so ``resolve_policy`` enables it).

    ``result`` is the pre-baked structured payload returned on escalation; ``None``
    mimics a model that yielded nothing.
    """

    engine_family = "vision_spy"
    engine_version = "spy-1"

    def __init__(self, result: dict | None) -> None:
        self._result = result
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        self.calls += 1
        assert isinstance(data, (bytes, bytearray))
        return self._result


def _vision_result() -> dict:
    extracted = {
        "contact": {
            "name": "Jane Engineer",
            "email": "jane.engineer@example.com",
            "phone": "+84 912 000 111",
        },
        "skills": {"items": [{"text": "Python"}, {"text": "FastAPI"}]},
    }
    return {
        "extracted_data": extracted,
        "review_fields": review_fields_for_extracted(extracted),
        "detected_language": "en",
    }


@pytest.fixture
def _spy_vision():
    """Install a call-counting vision adapter; ``resolve_policy`` then enables it."""

    def _install(result: dict | None) -> _SpyVision:
        spy = _SpyVision(result)
        set_vision_adapter(spy)
        return spy

    yield _install
    set_vision_adapter(None)


def test_clean_native_text_pdf_never_invokes_vision_and_is_free(_spy_vision) -> None:
    # Vision fully ENABLED (spy is available -> policy.vision_enabled True), yet a
    # clean, dense, single-column native-text PDF is structured entirely by the
    # FREE deterministic tier: the paid vision model is never called (0 energy),
    # and extraction is still correct.
    spy = _spy_vision(_vision_result())
    policy = resolve_policy()
    assert policy.vision_enabled is True  # the model WOULD run if selected

    outcome = run_cascade("cv.pdf", F.text_pdf_en(), max_bytes=_MAX, policy=policy)

    assert spy.calls == 0  # <-- the cost fix: clean text PDF skips the paid tier
    assert outcome.vision_used is False
    assert outcome.vision_attempted is False  # nothing to charge the student for
    assert outcome.llm_used is False
    assert outcome.accepted is True
    assert outcome.quality_code == "REVIEW_REQUIRED"
    assert outcome.detected_language == "en"
    # Accuracy holds: the deterministic tier captured the real contact + sections.
    assert outcome.extracted_data
    assert outcome.extracted_data["contact"]["email"] == "jane.engineer@example.com"


def test_two_column_native_text_pdf_stays_free_when_vision_enabled(_spy_vision) -> None:
    # A readable two-column text PDF still has adequate native coverage in reading
    # order, so it is served free too — no needless paid call.
    spy = _spy_vision(_vision_result())
    outcome = run_cascade("two.pdf", F.two_column_pdf(), max_bytes=_MAX, policy=resolve_policy())
    assert spy.calls == 0
    assert outcome.vision_used is False and outcome.vision_attempted is False
    assert outcome.accepted is True
    assert outcome.extracted_data


def test_scanned_sparse_pdf_escalates_to_vision(_spy_vision) -> None:
    # A canvas/vector PDF with an embedded image and almost no native text is
    # INSUFFICIENT for the free tier -> it escalates to the paid vision model.
    spy = _spy_vision(_vision_result())
    outcome = run_cascade(
        "sparse.pdf", F.sparse_canvas_pdf(), max_bytes=_MAX, policy=resolve_policy()
    )
    assert spy.calls == 1  # <-- the scanned/sparse path still uses vision
    assert outcome.vision_used is True
    assert outcome.vision_attempted is True
    assert outcome.accepted is True
    assert outcome.extracted_data["contact"]["email"] == "jane.engineer@example.com"


def test_image_cv_escalates_to_vision(_spy_vision) -> None:
    # An image upload has no native text at all -> always the vision tier.
    spy = _spy_vision(_vision_result())
    outcome = run_cascade(
        "scan.png", F.scanned_image_cv(), max_bytes=_MAX, policy=resolve_policy()
    )
    assert spy.calls == 1
    assert outcome.vision_used is True


def test_garbled_cid_native_text_pdf_escalates_to_vision(_spy_vision, monkeypatch) -> None:
    # A visually-rich PDF whose native text is CID-font garbage (unreadable encoded
    # glyphs) has native text present but UNUSABLE -> it must escalate to vision,
    # never stay on the free tier and structure garbage.
    spy = _spy_vision(_vision_result())

    class _CidAdapter:
        def __init__(self, *_a, **_k) -> None: ...

        def extract(self, filename, data):
            return ExtractionSignals(
                text="(cid:12)(cid:7)(cid:3)(cid:19)(cid:8)(cid:2)(cid:14)(cid:9)",
                page_count=1,
                engine_family="native_pdf",
                engine_version="pdfplumber",
                has_images=True,
                disordered=False,
            )

    monkeypatch.setattr(cv_ingestion_cascade, "NativeTextAdapter", _CidAdapter)
    outcome = run_cascade("styled.pdf", F.text_pdf_en(), max_bytes=_MAX, policy=resolve_policy())
    assert spy.calls == 1  # garbled native text is insufficient -> vision
    assert outcome.vision_used is True


def test_disordered_native_text_pdf_escalates_to_vision(_spy_vision, monkeypatch) -> None:
    # Column-flattened native text (out of reading order) is low-confidence -> the
    # vision tier re-reads structure from the page image.
    spy = _spy_vision(_vision_result())

    class _DisorderedAdapter:
        def __init__(self, *_a, **_k) -> None: ...

        def extract(self, filename, data):
            # Dense text (well above the coverage floor) but column-flattened.
            body = "\n".join(
                f"Left column text here    Right column text here for line {i:02d}"
                for i in range(12)
            )
            return ExtractionSignals(
                text=body,
                page_count=1,
                engine_family="native_pdf",
                engine_version="pdfplumber",
                has_images=False,
                disordered=True,
            )

    monkeypatch.setattr(cv_ingestion_cascade, "NativeTextAdapter", _DisorderedAdapter)
    outcome = run_cascade("cols.pdf", F.text_pdf_en(), max_bytes=_MAX, policy=resolve_policy())
    assert spy.calls == 1
    assert outcome.vision_used is True
