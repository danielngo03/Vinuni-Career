"""Persistent conversation memory + seq ordering + title tests (Lane A).

Uses the migration-0101 columns (ChatSession.memory_summary /
memory_message_count) and the 0089 conversation-management columns
(ChatMessage.seq / is_deleted). Offline provider only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.ai_assistant.application import chat_service
from app.modules.ai_assistant.application.session_history import (
    load_history,
    next_seq,
    refresh_session_title,
    update_session_memory,
)
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import register_verified


async def _student(db_session) -> Principal:
    user = await register_verified(
        db_session, email=f"mem_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    return Principal(user_id=user.id, persona="student", permissions=frozenset())


async def _chat(db_session, principal) -> ChatSession:
    created = await chat_service.create_session(db_session, principal=principal)
    return (
        await db_session.execute(
            select(ChatSession).where(ChatSession.id == uuid.UUID(created["id"]))
        )
    ).scalar_one()


def _msg(chat_id, i: int, role: str, content: str, *, deleted: bool = False) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        session_id=chat_id,
        role=role,
        content=content,
        seq=i,
        is_deleted=deleted,
        created_at=datetime.now(UTC) + timedelta(milliseconds=i),
    )


async def _seed_turns(db_session, chat, n: int, *, start: int = 1) -> None:
    for i in range(start, start + n):
        role = "user" if i % 2 == 1 else "assistant"
        db_session.add(_msg(chat.id, i, role, f"turn {i} nội dung tin nhắn"))
    await db_session.commit()


# --------------------------------------------------------------------------- #
# seq allocation + read paths                                                  #
# --------------------------------------------------------------------------- #


async def test_send_message_writes_monotonic_seq(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)

    await chat_service.send_message(
        db_session, principal=principal, session_id=chat.id, text="Xin chào"
    )
    await chat_service.send_message(
        db_session, principal=principal, session_id=chat.id, text="Tôi muốn thay đổi theme hệ thống"
    )

    rows = (
        (
            await db_session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat.id)
                .order_by(ChatMessage.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    seqs = [m.seq for m in rows if m.seq is not None]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs)), "seq must be unique per session"
    assert seqs[0] == 1


async def test_next_seq_counts_pending_messages(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    db_session.add(_msg(chat.id, 1, "user", "a"))
    # not committed yet — autoflush must still see it
    assert await next_seq(db_session, chat.id) == 2


async def test_get_session_messages_excludes_soft_deleted(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    db_session.add(_msg(chat.id, 1, "user", "giữ lại"))
    db_session.add(_msg(chat.id, 2, "assistant", "đã xóa mềm", deleted=True))
    db_session.add(_msg(chat.id, 3, "assistant", "cũng giữ lại"))
    await db_session.commit()

    messages = await chat_service.get_session_messages(
        db_session, principal=principal, session_id=chat.id
    )
    contents = [m["content"] for m in messages]
    assert contents == ["giữ lại", "cũng giữ lại"]


async def test_load_history_excludes_soft_deleted(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    db_session.add(_msg(chat.id, 1, "user", "còn đây"))
    db_session.add(_msg(chat.id, 2, "assistant", "biến mất", deleted=True))
    await db_session.commit()

    history = await load_history(db_session, chat)
    assert [m.content for m in history] == ["còn đây"]


# --------------------------------------------------------------------------- #
# Persistent memory                                                            #
# --------------------------------------------------------------------------- #


async def test_update_session_memory_folds_delta_and_advances_count(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    await _seed_turns(db_session, chat, 24)

    await update_session_memory(db_session, chat)

    assert chat.memory_summary
    assert chat.memory_message_count == 24 - 6  # keep the 6 most recent uncovered
    assert len(chat.memory_summary) <= 1500

    # No new messages → second call is a no-op (delta below trigger).
    summary_before = chat.memory_summary
    count_before = chat.memory_message_count
    await update_session_memory(db_session, chat)
    assert chat.memory_summary == summary_before
    assert chat.memory_message_count == count_before


async def test_update_session_memory_appends_next_delta(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    await _seed_turns(db_session, chat, 24)
    await update_session_memory(db_session, chat)
    first_count = chat.memory_message_count

    await _seed_turns(db_session, chat, 20, start=25)
    await update_session_memory(db_session, chat)

    assert chat.memory_message_count == 44 - 6
    assert chat.memory_message_count > first_count
    assert chat.memory_summary


async def test_update_session_memory_ignores_soft_deleted_rows(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    await _seed_turns(db_session, chat, 10)
    for i in range(11, 31):
        db_session.add(_msg(chat.id, i, "user", f"deleted {i}", deleted=True))
    await db_session.commit()

    await update_session_memory(db_session, chat)

    # Only 10 live rows — below the trigger, nothing folded.
    assert chat.memory_summary is None
    assert chat.memory_message_count == 0


async def test_update_session_memory_resets_after_truncation(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    await _seed_turns(db_session, chat, 24)
    await update_session_memory(db_session, chat)
    assert chat.memory_message_count == 18

    # Truncate the thread below the covered count (e.g. a deep edit).
    rows = (
        (await db_session.execute(select(ChatMessage).where(ChatMessage.session_id == chat.id)))
        .scalars()
        .all()
    )
    for m in rows:
        if (m.seq or 0) > 4:
            m.is_deleted = True
    await db_session.commit()

    await update_session_memory(db_session, chat)
    assert chat.memory_summary is None
    assert chat.memory_message_count == 0


async def test_memory_summary_is_leak_scrubbed(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    for i in range(1, 25):
        role = "user" if i % 2 == 1 else "assistant"
        db_session.add(
            _msg(chat.id, i, role, f"turn {i} uses openai and deepseek via openrouter")
        )
    await db_session.commit()

    await update_session_memory(db_session, chat)

    assert chat.memory_summary
    lowered = chat.memory_summary.lower()
    for banned in ("openai", "deepseek", "openrouter"):
        assert banned not in lowered


async def test_load_history_injects_memory_block_and_skips_covered(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    await _seed_turns(db_session, chat, 24)
    await update_session_memory(db_session, chat)

    history = await load_history(db_session, chat)

    assert history[0].role == "assistant"
    assert history[0].content.startswith("[Conversation memory]")
    # Recent window only: the 6 uncovered turns after the memory block.
    assert len(history) == 1 + 6
    assert all("turn" in m.content for m in history[1:])
    assert history[-1].content.startswith("turn 24")


# --------------------------------------------------------------------------- #
# Session title                                                                #
# --------------------------------------------------------------------------- #


async def test_first_exchange_sets_title_with_60_char_cap_offline(db_session) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)
    long_text = "Tôi muốn tìm việc thực tập ngành phân tích dữ liệu ở Hà Nội cho kỳ hè năm sau"

    await chat_service.send_message(
        db_session, principal=principal, session_id=chat.id, text=long_text
    )
    await db_session.refresh(chat)

    assert chat.title
    assert len(chat.title) <= 60
    assert chat.title == long_text[:60].strip()


async def test_refresh_session_title_scrubs_generated_output(db_session, monkeypatch) -> None:
    principal = await _student(db_session)
    chat = await _chat(db_session, principal)

    class _FakeCompletion:
        text = 'Powered by openai gpt-4: "Hiring pipeline review"'

    class _FakeProvider:
        async def complete(self, *args, **kwargs):
            return _FakeCompletion()

    import app.ai.gateway.factory as factory

    monkeypatch.setattr(factory, "real_provider_active", lambda: True)
    monkeypatch.setattr(factory, "get_provider_for_alias", lambda alias: _FakeProvider())

    await refresh_session_title(db_session, chat, "câu hỏi đầu tiên của tôi")
    await db_session.refresh(chat)

    assert chat.title
    lowered = chat.title.lower()
    assert "openai" not in lowered
    assert "gpt-4" not in lowered
    assert len(chat.title) <= 60
