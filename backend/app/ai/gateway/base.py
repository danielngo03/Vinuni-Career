"""Abstract AI provider interface and gateway value objects.

Callers work only with **function-slot handles** (``chat_default``,
``reasoning_default``, ...).
Provider names, model names, token counts, and latency are gateway internals and
must never be surfaced to end users (``docs/SECURITY_PRIVACY.md``).
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class AIMessage:
    role: Role
    content: str
    #: Native function-calling metadata (OpenAI tools protocol). Optional and
    #: default-empty so every existing ``AIMessage(role=, content=)`` caller is
    #: byte-for-byte unchanged.
    #: - ``tool_calls``: set on an ``assistant`` turn that requested tools; each
    #:   item is the raw provider tool_call dict ``{id, type, function{name,
    #:   arguments}}`` echoed straight back on the next request.
    #: - ``tool_call_id`` / ``name``: set on a ``tool`` role message carrying a
    #:   tool's result back to the model.
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(slots=True)
class AICompletion:
    """Result of a completion call.

    ``text`` is user-safe. ``usage`` and ``model_alias`` are internal-only
    metadata for cost tracking and must be scrubbed before any client response.
    ``tool_calls`` holds any native function-calls the model requested (empty for
    a plain text answer).
    """

    text: str
    model_alias: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    tool_calls: list[dict] = field(default_factory=list)


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
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
    ) -> AICompletion:
        """Return a completion for ``messages`` using the resolved alias model.

        When ``tools`` is supplied, the provider offers them via the native
        function-calling interface and any requested calls are returned on
        ``AICompletion.tool_calls``. ``tools`` defaults to ``None`` so plain
        text callers are unaffected.
        """
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
