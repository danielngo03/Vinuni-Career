"""Deterministic offline AI provider.

Default provider for unit tests and CI (no network, no keys). Output is a stable
function of the input so tests are reproducible. Used as the safe fallback when
real calls are disabled (``docs/LOCAL_DEV_STACK.md`` §5).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncGenerator

from app.ai.gateway.base import AICompletion, AIEmbedding, AIMessage, AIProvider

# Fake embedding dimensionality — matches text-embedding-3-small for test compat.
_OFFLINE_EMBED_DIM = 1536


class OfflineProvider(AIProvider):
    """Returns deterministic, non-network responses."""

    name = "offline"

    async def complete(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        seed = "\n".join(f"{m.role}:{m.content}" for m in messages)
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        text = (
            "[offline] Đây là phản hồi mô phỏng để kiểm thử. "
            f"(ref:{digest[:12]}) "
            f"Yêu cầu: {last_user[:160]}"
        ).strip()
        return AICompletion(
            text=text,
            model_alias=alias,
            usage={"prompt_tokens": len(seed), "completion_tokens": len(text)},
            finish_reason="stop",
        )

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Fake token-by-token streaming: yield one word at a time for test realism."""
        completion = await self.complete(
            messages, alias=alias, temperature=temperature, max_tokens=max_tokens
        )
        words = completion.text.split(" ")
        for i, word in enumerate(words):
            yield word if i == len(words) - 1 else word + " "

    async def embed(
        self,
        texts: list[str],
        *,
        alias: str,
    ) -> list[AIEmbedding]:
        """Return deterministic, unit-length fake embeddings from SHA-256.

        Each text maps to a stable vector derived from its SHA-256 digest so
        tests that compare embeddings for identical inputs get the same result.
        The vector is L2-normalised so cosine similarity works correctly in unit
        tests. NOT suitable as a real semantic signal — offline only.
        """
        results: list[AIEmbedding] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Build DIM floats by tiling the 32-byte digest and interpreting as ints
            raw: list[float] = []
            for i in range(_OFFLINE_EMBED_DIM):
                byte = digest[i % 32]
                # Map 0-255 → centred float with slight variation per position
                raw.append((byte - 128.0) / 128.0 + math.sin(i * 0.1) * 0.01)
            # L2-normalize
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            vector = [x / norm for x in raw]
            results.append(AIEmbedding(vector=vector, model_alias=alias))
        return results
