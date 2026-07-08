"""Extraction pipeline test: CV (all tiers, deterministic) + JD (native text tier).

Tests:
  - CV: native text (pdfplumber), OCR tier (Tesseract, if available), structuring,
    name/email/phone extraction, section detection, tier routing.
  - JD: native text extraction + `classify_jd_content` gate (deterministic).
    LLM structuring is skipped because AI_REAL_CALLS_ENABLED=False.

Usage:
    cd backend && uv run python scripts/test_extraction.py
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
os.chdir(BACKEND_ROOT)
# ---------------------------------------------------------------------------

from app.ai.extraction.adapters.base import (  # noqa: E402
    OCR_TRIGGER_THRESHOLD,
    ExtractionSignals,
    is_cid_corrupted,
)
from app.ai.extraction.adapters.native_text import NativeTextAdapter  # noqa: E402
from app.ai.extraction.adapters.ocr import get_ocr_adapter  # noqa: E402
from app.ai.extraction.cv_structuring import structure_cv_text  # noqa: E402
from app.ai.extraction.jd.validation import classify_jd_content  # noqa: E402
from app.ai.extraction.text_extraction import (  # noqa: E402
    ExtractionError,
    FileKind,
    extract_text,
    sniff_kind,
)

CV_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/CV")
JD_DIR = Path("/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/example/JD")

# ---- ANSI colours ----------------------------------------------------------

BOLD = "\033[1m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


def _color_verdict(verdict: str) -> str:
    if "OK" in verdict or "REVIEW" in verdict:
        return GREEN + verdict + RESET
    if "SCAN" in verdict or "BLANK" in verdict or "IMAGE" in verdict or "SPARSE" in verdict:
        return YELLOW + verdict + RESET
    return RED + verdict + RESET


# ---- helpers ----------------------------------------------------------------


def _section_summary(extracted: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, val in extracted.items():
        if key == "contact" or not isinstance(val, dict):
            continue
        entries = val.get("entries") or val.get("items") or []
        if isinstance(entries, list) and entries:
            counts[key] = len(entries)
    return counts


def _quality_verdict(kind: FileKind, text: str, ocr_unavailable: bool) -> str:
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


# ============================================================================
# CV extraction
# ============================================================================

ocr_adapter = get_ocr_adapter()
ocr_available = ocr_adapter.available


def extract_cv_file(filepath: Path) -> dict:
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

    verdict = _quality_verdict(kind, text, ocr_unavailable)
    cid_corrupted = kind is FileKind.PDF and is_cid_corrupted(text)
    needs_vision = (
        kind is FileKind.IMAGE
        or cid_corrupted
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
        "cid_corrupted": cid_corrupted,
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


def run_cv_tests() -> list[dict]:
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}CV EXTRACTION TEST{RESET}")
    print(f"Directory: {CV_DIR}")
    print(f"OCR available: {ocr_available}")
    print("=" * 80)

    files = sorted(CV_DIR.iterdir())
    results: list[dict] = []

    for f in files:
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png"):
            continue

        r = extract_cv_file(f)
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
            print("  Sections:  (none found)")
        if r.get("cid_corrupted"):
            print(f"  CID:       {RED}CORRUPTED — routed to vision{RESET}")
        if r["needs_vision"]:
            print(f"  Vision:    {YELLOW}NEEDED (skipped — real calls disabled){RESET}")
        if r["error"]:
            print(f"  Error:     {RED}{r['error']}{RESET}")
        print(f"  Verdict:   {_color_verdict(r['verdict'])}  ({r['elapsed_ms']:.0f} ms)")

    # Summary table
    print(f"\n{'=' * 80}")
    print(f"{BOLD}CV SUMMARY{RESET}")
    print(f"{'File':<20} {'Kind':<6} {'Tier':<8} {'Chars':>6} {'Lang':<6} "
          f"{'Name':<28} {'Verdict'}")
    print("-" * 100)
    for r in results:
        name_trunc = (r["contact_name"] or "(none)")[:28]
        print(
            f"{r['filename']:<20} {r['kind']:<6} {r['tier']:<8} "
            f"{r['text_chars']:>6} {r['detected_language']:<6} {name_trunc:<28} {r['verdict']}"
        )

    # Tier distribution
    tier_counts: dict[str, int] = {}
    vision_needed = 0
    total = len(results)
    for r in results:
        tier_counts[r["tier"]] = tier_counts.get(r["tier"], 0) + 1
        if r["needs_vision"]:
            vision_needed += 1

    print(f"\n{BOLD}Tier distribution ({total} CVs):{RESET}")
    for tier, count in sorted(tier_counts.items()):
        print(f"  {tier}: {count}")
    print(f"  Would use vision LLM: {vision_needed}")

    # Name quality
    no_name = [r["filename"] for r in results if not r["contact_name"] and r["text_chars"] > 40]
    if no_name:
        print(f"\n{YELLOW}{BOLD}Name extraction failures (text found, name empty):{RESET}")
        for fn in no_name:
            print(f"  {fn}")
    else:
        print(f"\n{GREEN}Name extraction: all text-bearing CVs have a name.{RESET}")

    return results


# ============================================================================
# JD extraction (deterministic tier only — LLM structuring requires real calls)
# ============================================================================

def extract_jd_file(filepath: Path) -> dict:
    filename = filepath.name
    data = filepath.read_bytes()
    size_kb = len(data) / 1024
    kind = sniff_kind(filename, data)

    start = time.perf_counter()

    text = ""
    page_count = 0
    has_images = False
    ocr_used = False
    engine_version = "pdfplumber"
    error = None

    if kind is FileKind.IMAGE:
        has_images = True
        if ocr_available:
            try:
                text = ocr_adapter.recognize(data, "vie+eng")
                ocr_used = True
            except Exception as exc:
                error = str(exc)
    elif kind in (FileKind.PDF, FileKind.DOCX, FileKind.TXT):
        try:
            result = extract_text(filename, data)
            text = result.text
            page_count = result.page_count
            engine_version = result.engine
            ocr_used = result.ocr_used
            # detect if PDF has images (for vision routing signal)
            if kind is FileKind.PDF:
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(data)) as pdf:
                        has_images = any(bool(page.images) for page in pdf.pages)
                except Exception:
                    pass
        except ExtractionError as exc:
            error = exc.code

    elapsed = time.perf_counter() - start

    # Deterministic JD gate (no AI)
    gate_status = classify_jd_content(text, kind=kind, ocr_used=ocr_used)

    # Simple description preview (first 200 chars of body text)
    stripped = text.strip()
    description_preview = stripped[:200].replace("\n", " ") if stripped else ""

    # Bullet quality: count lines that start with "-" or "•"
    body_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    bullet_lines = sum(1 for ln in body_lines if ln.startswith(("-", "•", "*")))
    bullet_ratio = bullet_lines / len(body_lines) if body_lines else 0.0

    cid_corrupted = kind is FileKind.PDF and is_cid_corrupted(text)
    needs_vision = (
        kind is FileKind.IMAGE
        or cid_corrupted
        or (kind is FileKind.PDF and len(stripped) < 40 and has_images)
    )

    return {
        "filename": filename,
        "size_kb": size_kb,
        "kind": kind.value,
        "text_chars": len(stripped),
        "page_count": page_count,
        "has_images": has_images,
        "ocr_used": ocr_used,
        "cid_corrupted": cid_corrupted,
        "needs_vision": needs_vision,
        "engine": engine_version,
        "gate_status": gate_status,
        "description_preview": description_preview,
        "bullet_lines": bullet_lines,
        "total_lines": len(body_lines),
        "bullet_ratio": bullet_ratio,
        "elapsed_ms": elapsed * 1000,
        "error": error,
    }


def run_jd_tests() -> list[dict]:
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}JD EXTRACTION TEST  (deterministic tier; LLM structuring skipped){RESET}")
    print(f"Directory: {JD_DIR}")
    print("=" * 80)

    if not JD_DIR.exists():
        print(f"{RED}JD directory not found: {JD_DIR}{RESET}")
        return []

    files = sorted(JD_DIR.iterdir())
    results: list[dict] = []

    for f in files:
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png", ".docx", ".txt"):
            continue

        r = extract_jd_file(f)
        results.append(r)

        gate_color = GREEN if r["gate_status"] == "ok" else YELLOW
        tag = MAGENTA + f"[{r['kind'].upper()}]" + RESET
        print(f"\n{BOLD}{r['filename']}{RESET}  {tag}  {r['size_kb']:.1f} KB")
        print(f"  Chars:      {r['text_chars']}  |  Pages: {r['page_count']}  "
              f"|  Has images: {r['has_images']}")
        print(f"  JD gate:    {gate_color}{r['gate_status']}{RESET}")
        print(f"  Bullets:    {r['bullet_lines']}/{r['total_lines']} lines  "
              f"({r['bullet_ratio']:.0%})")
        if r["description_preview"]:
            print(f"  Preview:    {r['description_preview'][:120]}…")
        if r.get("cid_corrupted"):
            print(f"  CID:        {RED}CORRUPTED — routed to vision{RESET}")
        if r["needs_vision"]:
            print(f"  Vision:     {YELLOW}NEEDED (skipped — real calls disabled){RESET}")
        if r["error"]:
            print(f"  Error:      {RED}{r['error']}{RESET}")
        if r["gate_status"] not in ("ok", "insufficient"):
            print(f"  LLM:        {YELLOW}SKIPPED (gate rejected){RESET}")
        else:
            print(f"  LLM:        {YELLOW}SKIPPED (AI_REAL_CALLS_ENABLED=False){RESET}")
        print(f"  Time:       {r['elapsed_ms']:.0f} ms")

    # Summary table
    print(f"\n{'=' * 80}")
    print(f"{BOLD}JD SUMMARY{RESET}")
    print(f"{'File':<20} {'Kind':<6} {'Chars':>6} {'Gate status':<22} {'Bullets':>7}  "
          f"{'Preview (60 chars)'}")
    print("-" * 110)
    for r in results:
        preview = r["description_preview"][:60].replace("\n", " ")
        print(
            f"{r['filename']:<20} {r['kind']:<6} {r['text_chars']:>6} "
            f"{r['gate_status']:<22} {r['bullet_lines']:>4}/{r['total_lines']:<3}  {preview}"
        )

    ok_count = sum(1 for r in results if r["gate_status"] == "ok")
    fail_count = len(results) - ok_count
    print(f"\n{BOLD}Gate results:{RESET}  {GREEN}{ok_count} ok{RESET}  /  "
          f"{RED}{fail_count} rejected{RESET}  of {len(results)} JDs")

    return results


# ============================================================================
# main
# ============================================================================

def main() -> None:
    cv_results = run_cv_tests()
    jd_results = run_jd_tests()

    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}COMBINED REPORT{RESET}")

    cv_ok = sum(1 for r in cv_results if "OK" in r["verdict"])
    cv_vision = sum(1 for r in cv_results if r["needs_vision"])
    jd_ok = sum(1 for r in jd_results if r["gate_status"] == "ok")

    print(f"  CVs processed:   {len(cv_results)}")
    print(f"  CVs text-OK:     {cv_ok}")
    print(f"  CVs need vision: {cv_vision}  (will use gemini-2.5-flash in production)")
    print(f"  JDs processed:   {len(jd_results)}")
    print(f"  JDs gate-ok:     {jd_ok}  (will go to LLM structuring in production)")
    print()


if __name__ == "__main__":
    main()
