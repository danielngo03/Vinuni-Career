from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import cast
from xml.etree import ElementTree

from app.ai.ingestion.types import FileKind, IngestionDecision

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

CONTENT_TYPE_KIND = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "text",
    "image/png": "image",
    "image/jpeg": "image",
}


def inspect_upload(
    content: bytes,
    *,
    declared_content_type: str | None = None,
    filename: str | None = None,
    min_text_chars: int = 40,
) -> IngestionDecision:
    reasons: list[str] = []
    if not content:
        return IngestionDecision(
            route="reject",
            detected_kind="unknown",
            declared_content_type=declared_content_type,
            byte_size=0,
            reasons=["File is empty."],
        )

    detected = detect_file_kind(content)
    declared_kind = CONTENT_TYPE_KIND.get((declared_content_type or "").lower())
    extension_kind = _kind_from_extension(filename)
    if declared_kind and detected != "unknown" and declared_kind != detected:
        reasons.append(f"Declared content type is {declared_kind}, but bytes look like {detected}.")
    if extension_kind and detected != "unknown" and extension_kind != detected:
        reasons.append(f"Filename extension is {extension_kind}, but bytes look like {detected}.")
    if reasons:
        return IngestionDecision(
            route="reject",
            detected_kind=detected,
            declared_content_type=declared_content_type,
            byte_size=len(content),
            reasons=[*reasons, "Rejected because file signature does not match declaration."],
        )

    if detected == "unknown":
        return IngestionDecision(
            route="reject",
            detected_kind=detected,
            declared_content_type=declared_content_type,
            byte_size=len(content),
            reasons=[*reasons, "Unsupported or spoofed file signature."],
        )

    text = extract_text_for_gatekeeping(content, detected)
    metadata: dict[str, int | str | bool] = {"text_chars": len(text)}
    if detected == "pdf":
        metadata["estimated_pages"] = _estimate_pdf_pages(content)
    if detected == "image":
        return IngestionDecision(
            route="vision_extraction",
            detected_kind=detected,
            declared_content_type=declared_content_type,
            byte_size=len(content),
            reasons=[*reasons, "Image input requires a vision-language extraction path."],
            extracted_text_preview="",
            metadata=metadata,
        )
    if detected in {"pdf", "docx"} and len(text.strip()) < min_text_chars:
        return IngestionDecision(
            route="vision_extraction",
            detected_kind=detected,
            declared_content_type=declared_content_type,
            byte_size=len(content),
            reasons=[
                *reasons,
                "Text layer is missing or too short; route to OCR/VLM document extraction.",
            ],
            extracted_text_preview=text[:500],
            metadata=metadata,
        )

    return IngestionDecision(
        route="text_extraction",
        detected_kind=detected,
        declared_content_type=declared_content_type,
        byte_size=len(content),
        reasons=reasons or ["Passed deterministic file gatekeeper."],
        extracted_text_preview=text[:500],
        metadata=metadata,
    )


def detect_file_kind(content: bytes) -> FileKind:
    if b"%PDF-" in content[:1024]:
        return "pdf"
    if content.startswith(PNG_MAGIC) or content.startswith(JPEG_MAGIC):
        return "image"
    if content.startswith(ZIP_MAGIC) and _looks_like_docx(content):
        return "docx"
    if _looks_like_text(content):
        return "text"
    return "unknown"


def extract_text_for_gatekeeping(content: bytes, kind: FileKind) -> str:
    if kind == "text":
        return content.decode("utf-8", errors="ignore")
    if kind == "docx":
        return _extract_docx_text(content)
    if kind == "pdf":
        return _extract_pdf_text_fallback(content)
    return ""


def _kind_from_extension(filename: str | None) -> FileKind | None:
    if not filename or "." not in filename:
        return None
    suffix = filename.rsplit(".", 1)[-1].lower()
    return cast(FileKind | None, {
        "pdf": "pdf",
        "docx": "docx",
        "txt": "text",
        "md": "text",
        "png": "image",
        "jpg": "image",
        "jpeg": "image",
    }.get(suffix))


def _looks_like_text(content: bytes) -> bool:
    sample = content[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(byte in b"\n\r\t" or 32 <= byte <= 126 for byte in sample)
    return printable / max(1, len(sample)) > 0.85


def _looks_like_docx(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        return ""
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError:
        return ""
    chunks = [node.text for node in root.iter() if node.text and node.text.strip()]
    return "\n".join(chunks)


def _extract_pdf_text_fallback(content: bytes) -> str:
    # Cheap gatekeeper extraction only. Full parsing/OCR belongs in worker pipelines.
    decoded = content.decode("latin-1", errors="ignore")
    literal_strings = re.findall(r"\(([^()\r\n]{3,})\)", decoded)
    cleaned = [re.sub(r"\\[()\\]", "", item).strip() for item in literal_strings]
    return "\n".join(item for item in cleaned if item)


def _estimate_pdf_pages(content: bytes) -> int:
    decoded = content.decode("latin-1", errors="ignore")
    return max(0, len(re.findall(r"/Type\s*/Page\b", decoded)))
