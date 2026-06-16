from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start_char: int
    end_char: int


def chunk_text(text: str, *, chunk_size: int = 1_200, overlap: int = 180) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        boundary = text.rfind("\n", start, end)
        if boundary > start + chunk_size // 2:
            end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(TextChunk(index=index, text=chunk, start_char=start, end_char=end))
            index += 1
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks
