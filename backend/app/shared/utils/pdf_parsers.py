from __future__ import annotations


def extract_text_best_effort(content: bytes, *, fallback_encoding: str = "utf-8") -> str:
    try:
        return content.decode(fallback_encoding)
    except UnicodeDecodeError:
        return content.decode(fallback_encoding, errors="ignore")
