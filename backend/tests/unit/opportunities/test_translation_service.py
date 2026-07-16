"""Unit tests for the JD translation service.

Uses offline provider (no real AI calls). Covers:
- Returns None when target_lang is unsupported
- Returns None when source == target lang (already correct language)
- Returns None when AI is offline (default in test env)
- Cache hit path returns cached data (happy path with mock)
- No provider/model internals in returned dict
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helper: build a minimal Job-like object without a real DB
# ---------------------------------------------------------------------------


class _MockJob:
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        language_code: str = "en",
        title: str = "Backend Engineer",
        description: str = "We are looking for a backend engineer.",
        requirements: str | None = "Python, SQL",
        benefits: str | None = "Competitive salary",
    ) -> None:
        self.id = id or uuid.uuid4()
        self.language_code = language_code
        self.title = title
        self.description = description
        self.requirements = requirements
        self.benefits = benefits


# ---------------------------------------------------------------------------
# Offline provider guard: AI is disabled by default in test env
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_ai_offline() -> None:
    """Offline provider → real_provider_active() is False → service returns None."""
    from app.modules.opportunities.application.translation_service import (
        get_or_create_translation,
    )

    job = _MockJob(language_code="en")
    session = AsyncMock()
    # Simulate no cache hit
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=execute_result)

    # real_provider_active() is False in the offline env (the default)
    result = await get_or_create_translation(session, job=job, target_lang="vi")
    assert result is None


# ---------------------------------------------------------------------------
# Unsupported target language
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_for_unsupported_lang() -> None:
    from app.modules.opportunities.application.translation_service import (
        get_or_create_translation,
    )

    job = _MockJob(language_code="en")
    session = AsyncMock()
    result = await get_or_create_translation(session, job=job, target_lang="fr")
    assert result is None
    # Should return before even touching the session
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Same source and target language — no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_same_language() -> None:
    from app.modules.opportunities.application.translation_service import (
        get_or_create_translation,
    )

    job = _MockJob(language_code="vi")
    session = AsyncMock()
    result = await get_or_create_translation(session, job=job, target_lang="vi")
    assert result is None
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Cache hit path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_data() -> None:
    from app.modules.opportunities.application.translation_service import (
        get_or_create_translation,
    )

    job = _MockJob(language_code="en")
    cached_row = MagicMock()
    cached_row.title = "Kỹ sư Backend"
    cached_row.description = "Chúng tôi tìm kiếm kỹ sư backend."
    cached_row.requirements = "Python, SQL"
    cached_row.benefits = "Mức lương cạnh tranh"

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = cached_row

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    result = await get_or_create_translation(session, job=job, target_lang="vi")

    assert result is not None
    assert result["from_cache"] is True
    assert result["title"] == "Kỹ sư Backend"
    assert result["language_code"] == "en"
    assert result["target_lang"] == "vi"


# ---------------------------------------------------------------------------
# No provider/model internals in cache hit result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_does_not_expose_internals() -> None:
    from app.modules.opportunities.application.translation_service import (
        get_or_create_translation,
    )

    job = _MockJob(language_code="en")
    cached_row = MagicMock()
    cached_row.title = "T"
    cached_row.description = "D"
    cached_row.requirements = "R"
    cached_row.benefits = "B"

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = cached_row

    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)

    result = await get_or_create_translation(session, job=job, target_lang="vi")
    assert result is not None

    # Internal fields must not appear in the public payload
    forbidden_keys = {
        "translated_by",
        "model",
        "provider",
        "model_alias",
        "token_count",
        "tokens",
        "latency",
    }
    assert not forbidden_keys.intersection(result.keys()), (
        f"Internal keys leaked: {forbidden_keys.intersection(result.keys())}"
    )


# ---------------------------------------------------------------------------
# Prompt version check (prompt module is importable and has PROMPT_VERSION)
# ---------------------------------------------------------------------------


def test_prompt_version_is_integer() -> None:
    from app.ai.prompts.jd_translation.v1 import PROMPT_VERSION

    assert isinstance(PROMPT_VERSION, int)
    assert PROMPT_VERSION >= 1


def test_build_user_message_contains_target_lang() -> None:
    from app.ai.prompts.jd_translation.v1 import build_user_message

    msg = build_user_message(
        source_lang="en",
        target_lang="vi",
        title="Backend Engineer",
        description="We build great software.",
        requirements="Python",
        benefits=None,
    )
    assert "Vietnamese" in msg
    assert "English" in msg
    assert "Backend Engineer" in msg


# ---------------------------------------------------------------------------
# opposite_target_lang — the pre-warm / inline-detail direction resolver
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("vi", "en"),
        ("en", "vi"),
        ("mixed", "vi"),
        ("unknown", "vi"),
        ("ja", "vi"),
        ("ko", "vi"),
        ("zh", "vi"),
        (None, "vi"),
    ],
)
def test_opposite_target_lang(source: str | None, expected: str) -> None:
    from app.modules.opportunities.application.translation_service import (
        opposite_target_lang,
    )

    assert opposite_target_lang(source) == expected


def test_opposite_target_lang_never_equals_unambiguous_source() -> None:
    """vi/en sources must map to the OTHER language, never themselves."""
    from app.modules.opportunities.application.translation_service import (
        opposite_target_lang,
    )

    assert opposite_target_lang("vi") != "vi"
    assert opposite_target_lang("en") != "en"
