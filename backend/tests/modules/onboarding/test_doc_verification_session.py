"""Regression: doc_verification imports + opens a worker session (WS-6, Task K).

The employer document-verification worker imported a non-existent
``async_session_factory`` from ``app.core.db`` (the module exports
``get_sessionmaker``), so ``run_verification`` crashed with an ImportError the
first time a real verification task ran — and mypy flagged the bad attribute.

These tests lock in the fix: the module imports cleanly, and the worker can open
a session and idempotently no-op when the target request is gone.

Run:
    cd backend && uv run pytest tests/modules/onboarding/test_doc_verification_session.py -q
"""

from __future__ import annotations

import uuid

import pytest


def test_doc_verification_imports_correct_session_factory() -> None:
    """Module imports and the fixed name resolves (no async_session_factory)."""
    from app.core import db as core_db
    from app.modules.onboarding.application import doc_verification

    # The bug: the module imported ``async_session_factory`` which does not exist.
    assert not hasattr(core_db, "async_session_factory")
    assert hasattr(core_db, "get_sessionmaker")
    # The worker handler is importable and callable.
    assert callable(doc_verification.run_verification)


@pytest.mark.asyncio
async def test_run_verification_opens_session_and_noops_when_missing() -> None:
    """The worker opens a real session and idempotently returns when the
    registration request does not exist (no ImportError, no exception)."""
    from app.modules.onboarding.application import doc_verification

    # A random request id => facade returns None => idempotent early return.
    # This exercises get_sessionmaker() opening a session outside a request.
    await doc_verification.run_verification({"request_id": str(uuid.uuid4())})
