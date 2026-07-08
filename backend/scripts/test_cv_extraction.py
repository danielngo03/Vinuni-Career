"""CV extraction pipeline test against the example CV files.

Runs purely deterministic tiers (native text + structuring). Vision and OCR are
disabled by default because AI_REAL_CALLS_ENABLED=False and Tesseract may be
absent. For each file reports tier, char count, language, contact name, section
counts, and quality verdict.

Usage:
    cd backend && uv run python scripts/test_cv_extraction.py
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

# ---- bootstrap: ensure backend/app is importable ---------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# Silence pydantic-settings noise from loading .env before we set cwd.
os.chdir(BACKEND_ROOT)

# ---------------------------------------------------------------------------

from app.ai.extraction.adapters.base import ExtractionSignals, OCR_TRIGGER_THRESHOLD
from app.ai.extraction.adapters.native_text import NativeTextAdapter
from app.ai.extraction.adapters.ocr import get_ocr_adapter
from app.ai.extraction.cv_structuring import structure_cv_text
from app.ai.extraction.text_extraction import ExtractionError, FileKind, sniff_kind

CV_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/CV")

# ---- helpers ---------------------------------------------------------------

_VI_DIACRITICS = (
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩị"
    "óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


def _color_verdict(verdict: str) -> str:
    if "OK" in verdict or "REVIEW" in verdict:
        return GREEN + verdict + RESET
    if "SCAN" in verdict or "BLANK" in verdict or "IMAGE" in verdict:
        return YELLOW + verdict + RESET
    return RED + verdict + RESET


def _section_summary(extracted: dict) -> dict[str, int]:
    """Count entries or items in each extracted section."""
    counts: dict[str, int] = {}
    for key, val in extracted.items():
        if key == "contact" or not isinstance(val, dict):
            continue
        entries = val.get("entries") or val.get("items") or []
        if isinstance(entries, list) and entries:
            counts[key] = len(entries)
    return counts


def _quality_verdict(
    kind: FileKind,
    text: str,
    tier: str,
    ocr_unavailable: bool,
) -> str:
    stripped = text.strip()
    if kind is FileKind.IMAGE and not stripped:
        if ocr_unavailable:
            return "LOW_QUALITY_SCAN (no OCR/vision)"
        return "IMAGE_NO_TEXT"
    if len(stripped) < OCR_TRIGGER_THRESHOLD:
        return "BLANK_OR_SPARSE"
    if len(stripped) < 120:
        return "INSUFFICIENT_CONTENT"
    return "REVIEW_REQUIRED (OK)"


# ---- OCR availability check ------------------------------------------------

ocr_adapter = get_ocr_adapter()
ocr_available = ocr_adapter.available

# ---- per-file extraction ---------------------------------------------------

def extract_file(filepath: Path) -> dict:
    filename = filepath.name
    data = filepath.read_bytes()
    size_kb = len(data) / 1024
    kind = sniff_kind(filename, data)

    start = time.perf_counter()

    tier = "native"
    text = ""
    page_count = 0
    has_images = False
    ocr_used = False
    ocr_unavailable = False
    engine_version = "pdfplumber"
    error = None

    if kind is FileKind.IMAGE:
        tier = "image"
        # Images go straight to vision/OCR - no native text. Try OCR if available.
        has_images = True
        if ocr_available:
            try:
                text = ocr_adapter.recognize(data, "vie+eng")
                ocr_used = True
                tier = "ocr"
            except Exception as exc:
                ocr_unavailable = True
                error = str(exc)
        else:
            ocr_unavailable = True

    elif kind is FileKind.PDF:
        adapter = NativeTextAdapter("pdfplumber")
        try:
            signals: ExtractionSignals = adapter.extract(filename, data)
            text = signals.text
            page_count = signals.page_count
            has_images = signals.has_images
            engine_version = signals.engine_version
        except ExtractionError as exc:
            error = exc.code
            text = ""

    elapsed = time.perf_counter() - start

    # Structuring (only for text-bearing results)
    structured = None
    contact_name = ""
    contact_email = ""
    contact_phone = ""
    sections: dict[str, int] = {}
    detected_language = "?"

    if text.strip():
        structured = structure_cv_text(text)
        extracted = structured["extracted_data"]
        contact = extracted.get("contact", {})
        contact_name = contact.get("name", "")
        contact_email = contact.get("email", "")
        contact_phone = contact.get("phone", "")
        sections = _section_summary(extracted)
        detected_language = structured.get("detected_language", "?")

    verdict = _quality_verdict(kind, text, tier, ocr_unavailable)
    needs_vision = (
        kind is FileKind.IMAGE
        or (kind is FileKind.PDF and len(text.strip()) < OCR_TRIGGER_THRESHOLD and has_images)
    )

    return {
        "filename": filename,
        "size_kb": size_kb,
        "kind": kind.value,
        "tier": tier,
        "text_chars": len(text.strip()),
        "page_count": page_count,
        "has_images": has_images,
        "ocr_used": ocr_used,
        "ocr_unavailable": ocr_unavailable,
        "needs_vision": needs_vision,
        "engine": engine_version,
        "detected_language": detected_language,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "sections": sections,
        "verdict": verdict,
        "elapsed_ms": elapsed * 1000,
        "error": error,
    }


# ---- main ------------------------------------------------------------------

def main() -> None:
    print(f"\n{BOLD}CV Extraction Pipeline Test{RESET}")
    print(f"CV directory: {CV_DIR}")
    print(f"OCR available: {ocr_available}")
    print("=" * 80)

    files = sorted(CV_DIR.iterdir())
    results: list[dict] = []

    for f in files:
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png"):
            continue

        r = extract_file(f)
        results.append(r)

        tag = CYAN + f"[{r['kind'].upper()}]" + RESET
        print(f"\n{BOLD}{r['filename']}{RESET}  {tag}  {r['size_kb']:.1f} KB")
        print(f"  Tier:      {r['tier']}  |  Engine: {r['engine']}")
        print(f"  Chars:     {r['text_chars']}  |  Pages: {r['page_count']}  "
              f"|  Has images: {r['has_images']}")
        print(f"  Language:  {r['detected_language']}")
        print(f"  Name:      '{r['contact_name']}' | Email: '{r['contact_email']}' "
              f"| Phone: '{r['contact_phone']}'")
        if r["sections"]:
            sec_str = "  ".join(f"{k}:{v}" for k, v in sorted(r["sections"].items()))
            print(f"  Sections:  {sec_str}")
        else:
            print(f"  Sections:  (none found)")
        if r["needs_vision"]:
            print(f"  Vision:    {YELLOW}NEEDED (skipped — real calls disabled){RESET}")
        if r["error"]:
            print(f"  Error:     {RED}{r['error']}{RESET}")
        print(f"  Verdict:   {_color_verdict(r['verdict'])}  ({r['elapsed_ms']:.0f} ms)")

    # ---- summary table -------------------------------------------------
    print(f"\n{'=' * 80}")
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"{'File':<20} {'Kind':<6} {'Tier':<8} {'Chars':>6} {'Lang':<6} {'Name':<25} {'Verdict'}")
    print("-" * 100)
    for r in results:
        name_trunc = (r["contact_name"] or "(none)")[:25]
        lang = r["detected_language"]
        print(
            f"{r['filename']:<20} {r['kind']:<6} {r['tier']:<8} "
            f"{r['text_chars']:>6} {lang:<6} {name_trunc:<25} {r['verdict']}"
        )

    # ---- tier distribution ---------------------------------------------
    tier_counts: dict[str, int] = {}
    vision_needed = 0
    total = len(results)
    for r in results:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
        if r["needs_vision"]:
            vision_needed += 1

    print(f"\n{BOLD}Tier distribution ({total} files):{RESET}")
    for tier, count in sorted(tier_counts.items()):
        print(f"  {tier}: {count}")
    print(f"  Would use vision LLM: {vision_needed}")

    # ---- name extraction quality ---------------------------------------
    no_name = [r["filename"] for r in results if not r["contact_name"] and r["text_chars"] > 40]
    if no_name:
        print(f"\n{YELLOW}{BOLD}Name extraction failures (text found but name empty):{RESET}")
        for fn in no_name:
            print(f"  {fn}")
    else:
        print(f"\n{GREEN}Name extraction: all text-bearing CVs have a name extracted.{RESET}")

    # ---- language check ------------------------------------------------
    print(f"\n{BOLD}Language detection:{RESET}")
    for r in results:
        if r["text_chars"] > 40:
            print(f"  {r['filename']:<20}  detected={r['detected_language']}")


if __name__ == "__main__":
    main()
