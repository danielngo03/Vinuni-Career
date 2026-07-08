"""Integration tests for AI-assistant conversation management.

Covers the rename / regenerate / edit-and-rerun endpoints and the seq +
soft-delete read path added in migration 0089. All model calls run offline
(``AI_REAL_CALLS_ENABLED=false`` in conftest → OfflineProvider), so no real AI
calls are made. Greeting inputs use the deterministic fast-path reply so the
assistant turn is reproducible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.ai_assistant.application import chat_service, usage_service
from app.modules.ai_assistant.application.session_history import serialize_message
from app.modules.ai_assistant.domain.models import ChatMessage
from app.shared.exceptions import (
    QuotaExceededError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import register_verified


async def _student(db_session, *, tag: str) -> Principal:
    user = await register_verified(
        db_session, email=f"chatmgmt_{tag}_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    return Principal(user_id=user.id, persona="student", permissions=frozenset())


async def _new_session(db_session, principal: Principal) -> uuid.UUID:
    created = await chat_service.create_session(db_session, principal=principal)
    return uuid.UUID(created["id"])


async def _messages(db_session, session_id: uuid.UUID) -> list[ChatMessage]:
    rows = (
        await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.asc())
        )
    ).scalars().all()
    return list(rows)


# --------------------------------------------------------------------------- #
# Rename                                                                       #
# --------------------------------------------------------------------------- #


async def test_rename_session_sets_user_editable_title(db_session) -> None:
    principal = await _student(db_session, tag="rename_ok")
    session_id = await _new_session(db_session, principal)

    result = await chat_service.rename_session(
        db_session,
        principal=principal,
        session_id=session_id,
        title="  Kế hoạch tìm việc  ",
    )

    assert result["id"] == str(session_id)
    assert result["title"] == "Kế hoạch tìm việc"  # stripped


async def test_rename_session_rejects_empty_and_whitespace(db_session) -> None:
    principal = await _student(db_session, tag="rename_empty")
    session_id = await _new_session(db_session, principal)

    with pytest.raises(ValidationFailedError):
        await chat_service.rename_session(
            db_session, principal=principal, session_id=session_id, title=""
        )
    with pytest.raises(ValidationFailedError):
        await chat_service.rename_session(
            db_session, principal=principal, session_id=session_id, title="    "
        )


async def test_rename_session_rejects_over_120_chars(db_session) -> None:
    principal = await _student(db_session, tag="rename_long")
    session_id = await _new_session(db_session, principal)

    with pytest.raises(ValidationFailedError):
        await chat_service.rename_session(
            db_session,
            principal=principal,
            session_id=session_id,
            title="x" * 121,
        )


async def test_rename_session_denied_for_non_owner(db_session) -> None:
    owner = await _student(db_session, tag="rename_owner")
    other = await _student(db_session, tag="rename_other")
    session_id = await _new_session(db_session, owner)

    # A non-owner cannot see (or rename) the session → 404, never a leak.
    with pytest.raises(ResourceNotFoundError):
        await chat_service.rename_session(
            db_session, principal=other, session_id=session_id, title="Hijack"
        )


# --------------------------------------------------------------------------- #
# Regenerate                                                                   #
# --------------------------------------------------------------------------- #


async def test_regenerate_drops_last_assistant_and_produces_new(db_session) -> None:
    principal = await _student(db_session, tag="regen_ok")
    session_id = await _new_session(db_session, principal)

    first = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    assert first["role"] == "assistant"
    old_assistant_id = first["id"]

    regenerated = await chat_service.regenerate_last(
        db_session, principal=principal, session_id=session_id
    )

    assert regenerated["role"] == "assistant"
    assert regenerated["content"]
    assert regenerated["id"] != old_assistant_id

    rows = await _messages(db_session, session_id)
    by_id = {str(m.id): m for m in rows}
    # Original assistant is soft-deleted; the regenerated one is live.
    assert by_id[old_assistant_id].is_deleted is True
    assert by_id[regenerated["id"]].is_deleted is False
    # Exactly one live user + one live assistant remain.
    live = [m for m in rows if not m.is_deleted]
    assert sorted(m.role for m in live) == ["assistant", "user"]

    # Read path shows only the regenerated reply (not the tombstoned one).
    visible = await chat_service.get_session_messages(
        db_session, principal=principal, session_id=session_id
    )
    ids = [m["id"] for m in visible]
    assert old_assistant_id not in ids
    assert regenerated["id"] in ids


async def test_regenerate_without_assistant_reply_is_user_safe_error(db_session) -> None:
    principal = await _student(db_session, tag="regen_none")
    session_id = await _new_session(db_session, principal)

    # A lone user message with no assistant reply yet → nothing to regenerate.
    db_session.add(
        ChatMessage(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user",
            content="Xin chào",
            created_at=datetime.now(UTC),
            seq=1,
        )
    )
    await db_session.flush()

    with pytest.raises(ValidationFailedError):
        await chat_service.regenerate_last(
            db_session, principal=principal, session_id=session_id
        )


async def test_regenerate_on_empty_session_is_user_safe_error(db_session) -> None:
    principal = await _student(db_session, tag="regen_empty")
    session_id = await _new_session(db_session, principal)

    with pytest.raises(ValidationFailedError):
        await chat_service.regenerate_last(
            db_session, principal=principal, session_id=session_id
        )


async def test_regenerate_respects_quota_and_preserves_reply(
    db_session, monkeypatch
) -> None:
    principal = await _student(db_session, tag="regen_quota")
    session_id = await _new_session(db_session, principal)

    first = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    old_assistant_id = first["id"]

    async def _blocked(_session, *, principal) -> None:  # noqa: ANN001
        raise QuotaExceededError(details={"reason": "AI_WEEKLY_ENERGY_EXCEEDED"})

    monkeypatch.setattr(usage_service, "enforce_quota", _blocked)

    with pytest.raises(QuotaExceededError):
        await chat_service.regenerate_last(
            db_session, principal=principal, session_id=session_id
        )

    # Quota is checked BEFORE any truncation — the existing reply survives.
    rows = await _messages(db_session, session_id)
    by_id = {str(m.id): m for m in rows}
    assert by_id[old_assistant_id].is_deleted is False


async def test_regenerate_denied_for_non_owner(db_session) -> None:
    owner = await _student(db_session, tag="regen_owner")
    other = await _student(db_session, tag="regen_intruder")
    session_id = await _new_session(db_session, owner)
    await chat_service.send_message(
        db_session, principal=owner, session_id=session_id, text="Xin chào"
    )

    with pytest.raises(ResourceNotFoundError):
        await chat_service.regenerate_last(
            db_session, principal=other, session_id=session_id
        )


# --------------------------------------------------------------------------- #
# Edit user message + re-run                                                   #
# --------------------------------------------------------------------------- #


async def test_edit_user_message_reruns_and_truncates_later_messages(db_session) -> None:
    principal = await _student(db_session, tag="edit_ok")
    session_id = await _new_session(db_session, principal)

    first = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    second = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="hi"
    )
    rows_before = await _messages(db_session, session_id)
    # user1(seq1), assistant1(seq2), user2(seq3), assistant2(seq4)
    assert [m.role for m in rows_before] == ["user", "assistant", "user", "assistant"]
    user1 = rows_before[0]
    later_ids = {str(m.id) for m in rows_before[1:]}
    assert first["id"] in later_ids and second["id"] in later_ids

    reply = await chat_service.edit_message(
        db_session,
        principal=principal,
        session_id=session_id,
        message_id=user1.id,
        text="hello",
    )

    assert reply["role"] == "assistant"
    assert reply["content"]

    rows_after = await _messages(db_session, session_id)
    by_id = {str(m.id): m for m in rows_after}
    # The edited user message: new content + edited_at stamped, still live.
    edited = by_id[str(user1.id)]
    assert edited.content == "hello"
    assert edited.edited_at is not None
    assert edited.is_deleted is False
    # Every message that came after the edited one is soft-deleted.
    for mid in later_ids:
        assert by_id[mid].is_deleted is True
    # The new reply is live and ordered after the edited message by seq.
    new_reply = by_id[reply["id"]]
    assert new_reply.is_deleted is False
    assert new_reply.seq is not None and edited.seq is not None
    assert new_reply.seq > edited.seq

    # Read path: only the edited user message + the new reply, in seq order.
    visible = await chat_service.get_session_messages(
        db_session, principal=principal, session_id=session_id
    )
    assert [m["id"] for m in visible] == [str(user1.id), reply["id"]]
    assert visible[0]["edited_at"] is not None


async def test_edit_rejects_non_user_message(db_session) -> None:
    principal = await _student(db_session, tag="edit_nonuser")
    session_id = await _new_session(db_session, principal)
    first = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    assistant_id = uuid.UUID(first["id"])

    with pytest.raises(ValidationFailedError):
        await chat_service.edit_message(
            db_session,
            principal=principal,
            session_id=session_id,
            message_id=assistant_id,
            text="đổi nội dung",
        )


async def test_edit_rejects_empty_text(db_session) -> None:
    principal = await _student(db_session, tag="edit_empty")
    session_id = await _new_session(db_session, principal)
    await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    rows = await _messages(db_session, session_id)
    user_msg = next(m for m in rows if m.role == "user")

    with pytest.raises(ValidationFailedError):
        await chat_service.edit_message(
            db_session,
            principal=principal,
            session_id=session_id,
            message_id=user_msg.id,
            text="    ",
        )


async def test_edit_denied_for_non_owner(db_session) -> None:
    owner = await _student(db_session, tag="edit_owner")
    other = await _student(db_session, tag="edit_intruder")
    session_id = await _new_session(db_session, owner)
    await chat_service.send_message(
        db_session, principal=owner, session_id=session_id, text="Xin chào"
    )
    rows = await _messages(db_session, session_id)
    user_msg = next(m for m in rows if m.role == "user")

    with pytest.raises(ResourceNotFoundError):
        await chat_service.edit_message(
            db_session,
            principal=other,
            session_id=session_id,
            message_id=user_msg.id,
            text="hijack",
        )


async def test_edit_respects_quota_and_preserves_messages(db_session, monkeypatch) -> None:
    principal = await _student(db_session, tag="edit_quota")
    session_id = await _new_session(db_session, principal)
    first = await chat_service.send_message(
        db_session, principal=principal, session_id=session_id, text="Xin chào"
    )
    rows = await _messages(db_session, session_id)
    user_msg = next(m for m in rows if m.role == "user")

    async def _blocked(_session, *, principal) -> None:  # noqa: ANN001
        raise QuotaExceededError(details={"reason": "AI_WEEKLY_ENERGY_EXCEEDED"})

    monkeypatch.setattr(usage_service, "enforce_quota", _blocked)

    with pytest.raises(QuotaExceededError):
        await chat_service.edit_message(
            db_session,
            principal=principal,
            session_id=session_id,
            message_id=user_msg.id,
            text="hello",
        )

    rows_after = await _messages(db_session, session_id)
    by_id = {str(m.id): m for m in rows_after}
    # Nothing mutated: original content kept, reply not deleted, no edited_at.
    assert by_id[str(user_msg.id)].content == "Xin chào"
    assert by_id[str(user_msg.id)].edited_at is None
    assert by_id[first["id"]].is_deleted is False


# --------------------------------------------------------------------------- #
# Read path: seq ordering + soft-delete exclusion                             #
# --------------------------------------------------------------------------- #


async def test_read_path_orders_by_seq_not_created_at(db_session) -> None:
    principal = await _student(db_session, tag="read_seq")
    session_id = await _new_session(db_session, principal)

    base = datetime(2026, 1, 1, tzinfo=UTC)
    # seq and created_at deliberately DISAGREE: the message with the later
    # created_at has the SMALLER seq, so a created_at sort would invert them.
    db_session.add_all(
        [
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                role="user",
                content="second-by-seq",
                created_at=base,  # earlier clock
                seq=2,
            ),
            ChatMessage(
                id=uuid.uuid4(),
                session_id=session_id,
                role="user",
                content="first-by-seq",
                created_at=base + timedelta(minutes=5),  # later clock
                seq=1,
            ),
        ]
    )
    await db_session.flush()

    visible = await chat_service.get_session_messages(
        db_session, principal=principal, session_id=session_id
    )
    assert [m["content"] for m in visible] == ["first-by-seq", "second-by-seq"]


async def test_read_path_excludes_soft_deleted(db_session) -> None:
    principal = await _student(db_session, tag="read_deleted")
    session_id = await _new_session(db_session, principal)

    live = ChatMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content="visible",
        created_at=datetime.now(UTC),
        seq=1,
    )
    dead = ChatMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        role="assistant",
        content="tombstoned",
        created_at=datetime.now(UTC),
        seq=2,
        is_deleted=True,
    )
    db_session.add_all([live, dead])
    await db_session.flush()

    visible = await chat_service.get_session_messages(
        db_session, principal=principal, session_id=session_id
    )
    contents = [m["content"] for m in visible]
    assert "visible" in contents
    assert "tombstoned" not in contents


def test_serialize_message_exposes_edited_at() -> None:
    msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="user",
        content="hi",
        created_at=datetime.now(UTC),
        edited_at=datetime.now(UTC),
        seq=1,
    )
    data = serialize_message(msg)
    assert data["edited_at"] is not None
    # seq stays internal — the ordering index is never exposed in responses.
    assert "seq" not in data
