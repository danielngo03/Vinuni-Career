"""Text extraction helpers for uploaded JD files."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".docx", ".docs"}:
        return _extract_docx(path)
    raise ValueError("Supported JD files: .txt, .pdf, .docx")


def extract_text_from_bytes(file_name: str, content: bytes) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".txt":
        return content.decode("utf-8")
    if suffix == ".pdf":
        return _extract_pdf_bytes(content)
    if suffix in {".docx", ".docs"}:
        return _extract_docx_bytes(content)
    raise ValueError("Supported JD files: .txt, .pdf, .docx")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf to read PDF files.") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_pdf_bytes(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf to read PDF files.") from exc

    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install python-docx to read DOCX files.") from exc

    doc = Document(str(path))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()


def _extract_docx_bytes(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Install python-docx to read DOCX files.") from exc

    doc = Document(BytesIO(content))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
