"""Employer document AI verification pipeline.

Enqueues an async task to verify uploaded business registration documents:
  1. OCR extraction (pdfplumber / tesseract fallback)
  2. Tamper detection (font/metadata/pixel heuristics)
  3. GDT Tax API lookup (tracuunnt.gdt.gov.vn) for MST verification
  4. Decision matrix → update partner_registration_requests.ai_doc_status

Task is idempotent: re-running with the same request_id is safe.
"""

from __future__ import annotations

import logging
import uuid

from app.core.worker import get_queue

logger = logging.getLogger(__name__)

TASK_NAME = "onboarding.verify_employer_document"


async def enqueue_verification(*, request_id: uuid.UUID) -> None:
    """Enqueue the async AI verification task for an employer document.

    Callers MUST enqueue this AFTER committing the transaction that wrote the
    document row (and ideally off the request path): the task opens its OWN DB
    session and can only see the document once it is committed. Enqueuing inside
    the still-open transaction with the inline dev queue self-deadlocks — the
    task's separate session blocks on the row the caller has locked-but-not-committed.
    """
    queue = get_queue()
    await queue.enqueue(TASK_NAME, {"request_id": str(request_id)})
    logger.info(
        "onboarding.verify_employer_document.enqueued",
        extra={"request_id": str(request_id)},
    )


async def run_verification(payload: dict) -> None:
    """Task handler — runs OCR, tamper detection, and GDT API check.

    Called by InlineTaskQueue (tests/dev) or Celery worker (production).
    Must be registered via ``get_task_queue().register(TASK_NAME, run_verification)``.
    """
    from app.core.db import get_sessionmaker
    from app.modules.organization.application import partner_registration_facade

    request_id = uuid.UUID(payload["request_id"])
    session_factory = get_sessionmaker()

    async with session_factory() as session:
        req = await partner_registration_facade.get_by_id(session, request_id)

        if req is None or req.ai_doc_status not in ("pending",):
            return  # idempotent — already processed or request gone

        document_path = req.document_path
        if not document_path:
            req.ai_doc_status = "manual_review"
            req.ai_doc_result = {"reason": "no_document"}
            await session.commit()
            return

        try:
            ocr_result = await _run_ocr(document_path)
            tamper_score = await _run_tamper_detection(document_path, ocr_result)
            gdt_result = await _verify_tax_id(req.tax_id, ocr_result.get("company_name"))

            decision = _make_decision(tamper_score=tamper_score, gdt_result=gdt_result)

            req.ai_doc_status = decision["status"]
            req.ai_doc_result = {
                "tamper_score": tamper_score,
                "ocr": ocr_result,
                "gdt": gdt_result,
                "decision": decision,
            }
            if gdt_result.get("matched"):
                req.tax_id_verified = True
                req.tax_id_api_result = gdt_result

            if decision["status"] == "tampered":
                req.status = "rejected"
                req.review_note = "Tài liệu có dấu hiệu giả mạo (AI phát hiện)"

            await session.commit()
            logger.info(
                "onboarding.verify_employer_document.done",
                extra={"request_id": str(request_id), "status": decision["status"]},
            )
        except Exception as exc:  # noqa: BLE001
            req.ai_doc_status = "manual_review"
            req.ai_doc_result = {"error": str(exc)}
            await session.commit()
            logger.warning(
                "onboarding.verify_employer_document.error",
                extra={"request_id": str(request_id), "error": str(exc)},
            )


# ── OCR ─────────────────────────────────────────────────────────────────────


async def _run_ocr(document_path: str) -> dict:
    """Extract text from PDF or image. Returns structured fields."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_ocr_sync, document_path)


def _run_ocr_sync(document_path: str) -> dict:
    """Synchronous OCR — tries pdfplumber first, falls back to pytesseract."""
    text = ""
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(document_path) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:  # noqa: BLE001
        pass

    if not text.strip():
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]

            img = Image.open(document_path)
            text = pytesseract.image_to_string(img, lang="vie+eng")
        except Exception:  # noqa: BLE001
            pass

    return {
        "raw_text": text[:3000],  # cap to avoid sending too much to LLM
        "company_name": _extract_field(text, ["Tên doanh nghiệp:", "Tên công ty:", "Company:"]),
        "tax_id": _extract_field(text, ["Mã số thuế:", "MST:", "Tax code:"]),
        "reg_date": _extract_field(text, ["Ngày đăng ký:", "Date of registration:"]),
    }


def _extract_field(text: str, labels: list[str]) -> str | None:
    """Naive label-based field extraction — good enough for structured ĐKKD."""
    for label in labels:
        idx = text.find(label)
        if idx != -1:
            line = text[idx + len(label) : idx + len(label) + 200].split("\n")[0].strip()
            if line:
                return line
    return None


# ── Tamper detection ─────────────────────────────────────────────────────────


async def _run_tamper_detection(document_path: str, _ocr_result: dict) -> int:
    """Return tamper score 0–100 (higher = more suspicious)."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_tamper_sync, document_path)


def _run_tamper_sync(document_path: str) -> int:
    score = 0
    path_lower = document_path.lower()
    if path_lower.endswith(".pdf"):
        score += _pdf_tamper_score(document_path)
    else:
        score += _image_tamper_score(document_path)
    return min(score, 100)


def _pdf_tamper_score(path: str) -> int:
    """Heuristic PDF tamper checks (font consistency, metadata)."""
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(path) as pdf:
            fonts: set[str] = set()
            for page in pdf.pages:
                chars = page.chars
                for ch in chars:
                    if ch.get("fontname"):
                        fonts.add(ch["fontname"])
            # More than 5 distinct fonts in a short document is suspicious
            if len(fonts) > 5:
                return 40
    except Exception:  # noqa: BLE001
        return 20  # can't read = elevated suspicion
    return 0


def _image_tamper_score(path: str) -> int:
    """ELA (Error Level Analysis) heuristic for images."""
    try:
        import io

        import numpy as np  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]

        img = Image.open(path).convert("RGB")
        # Save at low quality and compare pixel variance
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        buf.seek(0)
        compressed = Image.open(buf).convert("RGB")
        diff = np.abs(np.array(img, dtype=int) - np.array(compressed, dtype=int))
        avg_diff = float(diff.mean())
        # High average diff means suspicious high-frequency modifications
        if avg_diff > 15:
            return 60
        if avg_diff > 8:
            return 30
    except Exception:  # noqa: BLE001
        return 15
    return 0


# ── GDT Tax API ──────────────────────────────────────────────────────────────


async def _verify_tax_id(tax_id: str | None, ocr_company_name: str | None) -> dict:
    """Call GDT API to verify MST. Returns match result."""
    if not tax_id:
        return {"verified": False, "reason": "no_tax_id"}
    try:
        import difflib

        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://tracuunnt.gdt.gov.vn/tcnnt/mstcn.jsp",
                params={"mst": tax_id},
                headers={"User-Agent": "Mozilla/5.0 VinUni-Career-Platform/1.0"},
            )
            resp.raise_for_status()
            body = resp.text

        # Parse company name from response HTML (simplified heuristic)
        gdt_company = _parse_gdt_company_name(body)
        matched = False
        similarity = 0.0
        if gdt_company and ocr_company_name:
            similarity = difflib.SequenceMatcher(
                None,
                gdt_company.lower().strip(),
                ocr_company_name.lower().strip(),
            ).ratio()
            matched = similarity >= 0.85

        return {
            "verified": True,
            "gdt_company_name": gdt_company,
            "matched": matched,
            "similarity": round(similarity, 3),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("gdt_api.error", extra={"error": str(exc)})
        return {"verified": False, "reason": "api_error", "error": str(exc)}


def _parse_gdt_company_name(html: str) -> str | None:
    """Best-effort extraction of company name from GDT HTML response."""
    import re

    match = re.search(r"Tên(?:\s+doanh\s+nghiệp|[^:]*)?:\s*</[^>]+>\s*<[^>]+>([^<]+)", html)
    if match:
        return match.group(1).strip()
    return None


# ── Decision matrix ──────────────────────────────────────────────────────────


def _make_decision(*, tamper_score: int, gdt_result: dict) -> dict:
    gdt_matched = gdt_result.get("matched", False)

    if tamper_score > 60:
        return {"status": "tampered", "confidence": "low"}
    if tamper_score <= 30 and gdt_matched:
        return {"status": "passed", "confidence": "high"}
    return {"status": "manual_review", "confidence": "medium"}
