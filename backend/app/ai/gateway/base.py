"""Abstract AI provider interface and gateway value objects.

Callers work only with **aliases** (``chat_cheap``, ``reasoning_cheap``, ...).
Provider names, model names, token counts, and latency are gateway internals and
must never be surfaced to end users (``docs/SECURITY_PRIVACY.md``).
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class AIMessage:
    role: Role
    content: str


@dataclass(slots=True)
class AICompletion:
    """Result of a completion call.

    ``text`` is user-safe. ``usage`` and ``model_alias`` are internal-only
    metadata for cost tracking and must be scrubbed before any client response.
    """

    text: str
    model_alias: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"


@dataclass(slots=True)
class AIEmbedding:
    """Result of an embedding call.

    ``vector`` is a list of floats (the embedding); ``model_alias`` is
    internal-only metadata for cost tracking. Dimensionality depends on the
    alias/model — callers must not assume a fixed size.
    """

    vector: list[float]
    model_alias: str
    usage: dict[str, int] = field(default_factory=dict)


class AIProvider(abc.ABC):
    """Abstract provider adapter. Concrete adapters live behind the factory."""

    #: Internal provider identifier — never exposed to end users.
    name: str = "abstract"

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AICompletion:
        """Return a completion for ``messages`` using the resolved alias model."""
        raise NotImplementedError

    async def stream(
        self,
        messages: list[AIMessage],
        *,
        alias: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Stream completion tokens one chunk at a time.

        Default implementation calls ``complete()`` and yields the full text as
        a single chunk — subclasses override for true token-level streaming.
        Callers must handle both the streaming and single-chunk cases identically.
        """
        completion = await self.complete(
            messages, alias=alias, temperature=temperature, max_tokens=max_tokens
        )
        yield completion.text

    @abc.abstractmethod
    async def embed(
        self,
        texts: list[str],
        *,
        alias: str,
    ) -> list[AIEmbedding]:
        """Return one embedding per text string.

        Each element of the returned list corresponds to the same-index element
        of ``texts``. The embedding dimensionality is determined by the resolved
        alias/model and must not be assumed by callers (store alongside the
        vector).
        """
        raise NotImplementedError
