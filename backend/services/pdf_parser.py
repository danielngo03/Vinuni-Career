"""
PDF Parsing Service - Extract text from PDF files
"""
import io
from pathlib import Path

import pdfplumber


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text content from a PDF file.

    Args:
        file_bytes: Raw bytes of the PDF file

    Returns:
        Extracted text as a single string
    """
    text_parts = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {page_num} ---\n{page_text}")

    if not text_parts:
        raise ValueError(
            "Không thể extract text từ PDF này. "
            "PDF có thể bị scan dưới dạng ảnh (image-based PDF)."
        )

    return "\n\n".join(text_parts)


def extract_text_from_path(pdf_path: str | Path) -> str:
    """Extract text from PDF at a given file path."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {pdf_path}")

    with open(path, "rb") as f:
        return extract_text_from_pdf(f.read())
