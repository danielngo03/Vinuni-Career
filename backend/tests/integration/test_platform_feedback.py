"""Integration tests for the platform feedback endpoint (POST /feedback).

Covers: guest submission (no auth required), authenticated submission tagged
to the user, unknown category coerced to "other", validation failure on a
too-short message, and empty-state listing (no feedback exists yet for a
freshly seeded DB).
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.platform_feedback.api.router import FeedbackBody, submit_feedback
from app.modules.platform_feedback.domain.models import UserFeedback
from app.shared.permissions import GUEST
from pydantic import ValidationError
from sqlalchemy import func, select

from tests.documents_utils import make_student


async def _count_feedback(db_session) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(UserFeedback))
    ).scalar_one()


# --------------------------------------------------------------------------- #
# happy path                                                                   #
# --------------------------------------------------------------------------- #


async def test_guest_can_submit_feedback_without_auth(db_session) -> None:
    body = FeedbackBody(category="bug", message="The apply button is broken on mobile.")
    result = await submit_feedback(body, principal=GUEST, session=db_session)

    assert "id" in result["data"]
    assert "created_at" in result["data"]

    row = (
        await db_session.execute(
            select(UserFeedback).where(UserFeedback.id == uuid.UUID(result["data"]["id"]))
        )
    ).scalar_one()
    assert row.user_id is None
    assert row.category == "bug"


async def test_authenticated_student_feedback_is_tagged_to_user(db_session) -> None:
    user, student = await make_student(db_session)
    body = FeedbackBody(category="suggestion", message="Add dark mode please.")
    result = await submit_feedback(body, principal=student, session=db_session)

    row = (
        await db_session.execute(
            select(UserFeedback).where(UserFeedback.id == uuid.UUID(result["data"]["id"]))
        )
    ).scalar_one()
    assert row.user_id == user.id
    assert row.category == "suggestion"


# --------------------------------------------------------------------------- #
# category normalization                                                       #
# --------------------------------------------------------------------------- #


async def test_unknown_category_falls_back_to_other(db_session) -> None:
    body = FeedbackBody(category="not-a-real-category", message="Random unclassified note.")
    result = await submit_feedback(body, principal=GUEST, session=db_session)

    row = (
        await db_session.execute(
            select(UserFeedback).where(UserFeedback.id == uuid.UUID(result["data"]["id"]))
        )
    ).scalar_one()
    assert row.category == "other"


async def test_category_is_case_and_whitespace_normalized(db_session) -> None:
    body = FeedbackBody(category="  PRAISE  ", message="Great platform overall!")
    result = await submit_feedback(body, principal=GUEST, session=db_session)

    row = (
        await db_session.execute(
            select(UserFeedback).where(UserFeedback.id == uuid.UUID(result["data"]["id"]))
        )
    ).scalar_one()
    assert row.category == "praise"


# --------------------------------------------------------------------------- #
# validation failure                                                           #
# --------------------------------------------------------------------------- #


def test_message_too_short_fails_schema_validation() -> None:
    with pytest.raises(ValidationError):
        FeedbackBody(category="bug", message="hi")


def test_empty_category_fails_schema_validation() -> None:
    with pytest.raises(ValidationError):
        FeedbackBody(category="", message="A valid length message here.")


# --------------------------------------------------------------------------- #
# empty state                                                                  #
# --------------------------------------------------------------------------- #


async def test_no_feedback_rows_before_any_submission(db_session) -> None:
    assert await _count_feedback(db_session) == 0
