from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start_char: int
    end_char: int
    chunk_id: str = ""
    token_count: int = 0
    section: str | None = None


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1_200,
    overlap: int = 180,
    document_id: str = "document",
) -> list[TextChunk]:
    """Split text on useful semantic boundaries while preserving source offsets.

    ``chunk_size`` remains character based so it is deterministic without a
    provider tokenizer. Token counts are conservative estimates used for
    budgeting, not billing.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        end = _best_boundary(text, start, end, chunk_size)
        raw_chunk = text[start:end]
        left_trim = len(raw_chunk) - len(raw_chunk.lstrip())
        right_trim = len(raw_chunk.rstrip())
        chunk_start = start + left_trim
        chunk_end = start + right_trim
        chunk = text[chunk_start:chunk_end]
        if chunk:
            digest = sha256(
                f"{document_id}:{index}:{chunk_start}:{chunk_end}:{chunk}".encode()
            ).hexdigest()[:24]
            chunks.append(
                TextChunk(
                    index=index,
                    text=chunk,
                    start_char=chunk_start,
                    end_char=chunk_end,
                    chunk_id=f"{document_id}:{digest}",
                    token_count=_estimate_tokens(chunk),
                    section=_nearest_heading(text, chunk_start),
                )
            )
            index += 1
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _best_boundary(text: str, start: int, end: int, chunk_size: int) -> int:
    minimum = start + chunk_size // 2
    window = text[start:end]
    for pattern in (r"\n\s*\n", r"\n", r"(?<=[.!?])\s+"):
        matches = list(re.finditer(pattern, window))
        if matches:
            candidate = start + matches[-1].end()
            if candidate >= minimum:
                return candidate
    return end


def _nearest_heading(text: str, position: int) -> str | None:
    lines = text[:position].splitlines()
    for line in reversed(lines[-20:]):
        candidate = line.strip().strip(":")
        if 2 <= len(candidate) <= 80 and (
            candidate.isupper()
            or candidate.lower()
            in {
                "education",
                "experience",
                "skills",
                "projects",
                "summary",
                "requirements",
                "responsibilities",
            }
        ):
            return candidate
    return None


def _estimate_tokens(text: str) -> int:
    words = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
    return max(1, int(len(words) * 1.3))
