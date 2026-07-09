"""Document chunking pipeline for the Knowledge Base RAG pipeline (§6.1).

Two chunking strategies:
- **Sliding window** (Mode A): fixed 512-token target with 64-token overlap.
  Safe default for most documents.
- **Semantic split** (Mode B): splits on embedding cosine similarity drops
  below a threshold. Gives higher-quality chunk boundaries but is slower.
  Used for documents > 50 pages or documents with clear section headings.

Chunk selection rule: choose Mode B automatically when the document has
multi-section structure (detected by heading patterns) or a high page count.
Callers may override with the ``mode`` parameter.

All returned chunks are dicts conforming to the schema expected by
``knowledge_base_chunks`` (content, token_count, section_heading, chunk_index).
Provider names, model IDs, and embedding vectors are NEVER stored in chunk
records — only the text and structural metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ChunkMode = Literal["sliding_window", "semantic"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TARGET_TOKENS = 512  # soft target for chunk size
_OVERLAP_TOKENS = 64  # overlap between consecutive sliding-window chunks
_SEMANTIC_SIM_THRESHOLD = 0.65  # split when similarity drops below this
_SEMANTIC_MIN_CHUNK_WORDS = 40  # never split below this word count
_LARGE_DOC_HEADING_PATTERN = re.compile(
    r"^(#{1,4}\s+.+|[A-Z][A-Z\s]{5,}$|\d+\.\s+[A-Z])", re.MULTILINE
)

# Rough 1-token ≈ 4-char approximation (conservative, avoids large over-splits)
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _estimate_pages(text: str) -> float:
    """Very rough estimate: ~3000 chars ≈ 1 A4 page of dense text."""
    return len(text) / 3000


def _has_structured_headings(text: str) -> bool:
    return bool(_LARGE_DOC_HEADING_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Chunk:
    content: str
    chunk_index: int
    section_heading: str
    token_count: int


# ---------------------------------------------------------------------------
# Heading extraction helpers
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(
    r"(?m)^(#{1,4}\s+.+|[A-Z][A-Z\s]{4,}:?\s*$|\d+\.\d*\s+[A-Z].{0,60})\s*\n",
)


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split text into (heading, body) pairs by Markdown/plain headings.

    Falls back to a single section with an empty heading when no headings are
    detected.
    """
    sections: list[tuple[str, str]] = []
    last_end = 0
    current_heading = ""

    for m in _HEADING_RE.finditer(text):
        body = text[last_end : m.start()].strip()
        if body:
            sections.append((current_heading, body))
        current_heading = m.group(1).strip().lstrip("#").strip()
        last_end = m.end()

    tail = text[last_end:].strip()
    if tail:
        sections.append((current_heading, tail))

    if not sections:
        sections = [("", text.strip())]

    return sections


# ---------------------------------------------------------------------------
# Mode A: Sliding window chunking
# ---------------------------------------------------------------------------


def _sliding_window_chunks(
    text: str,
    *,
    target_tokens: int = _TARGET_TOKENS,
    overlap_tokens: int = _OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split text into overlapping fixed-size chunks by character approximation."""
    target_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _CHARS_PER_TOKEN
    stride = max(1, target_chars - overlap_chars)

    # Split into sections first to carry heading context
    sections = _split_by_headings(text)
    chunks: list[Chunk] = []
    idx = 0

    for heading, body in sections:
        start = 0
        while start < len(body):
            end = start + target_chars
            window = body[start:end].strip()
            if window:
                chunks.append(
                    Chunk(
                        content=window,
                        chunk_index=idx,
                        section_heading=heading,
                        token_count=_estimate_tokens(window),
                    )
                )
                idx += 1
            start += stride

    if chunks:
        return chunks
    fallback_content = text[:target_chars]
    return [
        Chunk(
            content=fallback_content,
            chunk_index=0,
            section_heading="",
            token_count=_estimate_tokens(fallback_content),
        )
    ]


# ---------------------------------------------------------------------------
# Mode B: Semantic similarity chunking
# ---------------------------------------------------------------------------


async def _semantic_chunks(
    text: str,
    *,
    sim_threshold: float = _SEMANTIC_SIM_THRESHOLD,
    min_words: int = _SEMANTIC_MIN_CHUNK_WORDS,
) -> list[Chunk]:
    """Split text by embedding cosine similarity drops between paragraphs.

    Groups consecutive paragraphs until the similarity between the accumulated
    group embedding and the next paragraph drops below ``sim_threshold``.
    Falls back to sliding window on embedding failure.
    """
    from app.ai.retrieval.embeddings import cosine_sim, embed_texts

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) <= 1:
        # Single paragraph or no clear structure — use sliding window
        return _sliding_window_chunks(text)

    # Embed all paragraphs in one batched call
    try:
        embeddings = await embed_texts(paragraphs)
        vectors = [e.vector for e in embeddings]
    except Exception:
        # Embedding unavailable — fall through to sliding window
        return _sliding_window_chunks(text)

    # Greedy merge: accumulate paragraphs while similarity remains high
    chunks: list[Chunk] = []
    idx = 0
    group: list[str] = [paragraphs[0]]
    group_vec: list[float] = vectors[0]

    def _avg_vec(vecs: list[list[float]]) -> list[float]:
        if not vecs:
            return []
        dim = len(vecs[0])
        avg = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        norm = sum(x * x for x in avg) ** 0.5 or 1.0
        return [x / norm for x in avg]

    group_vecs: list[list[float]] = [vectors[0]]

    sections = _split_by_headings(text)
    # Map paragraph index to section heading (best-effort)
    para_to_heading: dict[int, str] = {}
    for heading, body in sections:
        body_paras = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
        for para in body_paras:
            for pi, p in enumerate(paragraphs):
                if p.startswith(para[:50]):
                    para_to_heading.setdefault(pi, heading)

    for i in range(1, len(paragraphs)):
        sim = cosine_sim(group_vec, vectors[i])
        word_count = sum(len(p.split()) for p in group)

        if sim < sim_threshold and word_count >= min_words:
            content = "\n\n".join(group)
            heading = para_to_heading.get(i - len(group), "")
            chunks.append(
                Chunk(
                    content=content,
                    chunk_index=idx,
                    section_heading=heading,
                    token_count=_estimate_tokens(content),
                )
            )
            idx += 1
            group = [paragraphs[i]]
            group_vecs = [vectors[i]]
        else:
            group.append(paragraphs[i])
            group_vecs.append(vectors[i])
        group_vec = _avg_vec(group_vecs)

    # Flush remaining paragraphs
    if group:
        content = "\n\n".join(group)
        heading = para_to_heading.get(len(paragraphs) - len(group), "")
        chunks.append(
            Chunk(
                content=content,
                chunk_index=idx,
                section_heading=heading,
                token_count=_estimate_tokens(content),
            )
        )

    return chunks if chunks else _sliding_window_chunks(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def chunk_document(
    text: str,
    *,
    mode: ChunkMode | None = None,
    page_count: int = 0,
) -> list[Chunk]:
    """Chunk a document's text into a list of ``Chunk`` objects.

    Auto-selects the chunking strategy when ``mode`` is not specified:
    - Use semantic chunking for multi-section documents or documents > 50 pages.
    - Use sliding-window otherwise.

    Args:
        text:        Full extracted text of the document.
        mode:        Override auto-selection with ``"sliding_window"`` or
                     ``"semantic"``.
        page_count:  Optional page count; if > 50, semantic mode is selected.

    Returns:
        Ordered list of ``Chunk`` objects; empty list when ``text`` is blank.
    """
    text = text.strip()
    if not text:
        return []

    if mode is None:
        estimated_pages = page_count or _estimate_pages(text)
        use_semantic = estimated_pages > 50 or _has_structured_headings(text)
        mode = "semantic" if use_semantic else "sliding_window"

    if mode == "semantic":
        return await _semantic_chunks(text)

    return _sliding_window_chunks(text)
