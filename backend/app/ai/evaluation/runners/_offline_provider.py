"""Shared "provider unavailable" simulation for eval cases in the ``fallback``
category. Used by any runner whose task makes a real LLM call
(``cv_ai_suggestions``, ``jd_generation``) to deterministically exercise the
``AIUnavailableError`` degrade path without touching the network.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest import mock


class DownProvider:
    """Provider that always fails — drives the offline AI-unavailable path."""

    name = "offline"

    async def complete(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("provider unavailable (eval fallback case)")


@contextmanager
def maybe_provider_down(unavailable: bool) -> Any:
    if unavailable:
        with mock.patch("app.ai.cv.llm.get_provider", lambda: DownProvider()):
            yield
    else:
        yield
