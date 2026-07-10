"""AI assistant session/message history management.

Owns chat session CRUD (create/list/archive), message persistence/serialization,
conversation history loading for the LLM (with old-context compression), and the
lightweight per-turn user-context builder used to personalize replies. Extracted
from the former monolithic ``chat_service.py`` so session/history concerns are
independent of the tool-calling loop and response formatting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.exceptions import AuthRequiredError, ResourceNotFoundError
from app.shared.permissions import Principal

_MAX_HISTORY_MESSAGES = 20
_COMPRESS_THRESHOLD = 16  # compress when history exceeds this many messages
_SUMMARY_KEEP_RECENT = 6  # keep the N most recent turns after compression

# Persistent conversation memory (ChatSession.memory_summary, migration 0101).
_MEMORY_DELTA_TRIGGER = 16  # summarize when this many messages exceed coverage
_MEMORY_KEEP_RECENT = 6  # never fold the N most recent messages into memory
_MEMORY_MAX_CHARS = 1500  # hard cap on the stored rolling summary
_TITLE_MAX_CHARS = 60

# Conversation roles that form the LLM-visible history/memory stream.
_CONVO_ROLES = ("user", "assistant", "tool_result")


# --------------------------------------------------------------------------- #
# Session CRUD                                                                #
# --------------------------------------------------------------------------- #


async def create_session(
    session: AsyncSession,
    *,
    principal: Principal,
) -> dict:
    """Create a new chat session for the principal."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = ChatSession(
        id=uuid.uuid4(),
        user_id=principal.user_id,
        persona=principal.persona,
        created_at=datetime.now(UTC),
    )
    session.add(chat)
    await session.flush()
    await session.refresh(chat)
    await session.commit()
    return serialize_session(chat)


async def list_sessions(
    session: AsyncSession,
    *,
    principal: Principal,
    limit: int = 20,
) -> list[dict]:
    """List recent (non-archived) sessions for the principal."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    rows = (
        (
            await session.execute(
                select(ChatSession)
                .where(
                    ChatSession.user_id == principal.user_id,
                    ChatSession.is_archived.is_(False),
                )
                .order_by(ChatSession.last_message_at.desc().nullslast())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [serialize_session(r) for r in rows]


async def get_session_messages(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    limit: int = 50,
) -> list[dict]:
    """Return the most recent messages for a session (owner-only)."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    rows = (
        (
            await session.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat.id)
                .where(ChatMessage.role != "tool_result")
                .where(ChatMessage.is_deleted.is_(False))
                .order_by(ChatMessage.created_at.asc(), ChatMessage.seq.asc().nullsfirst())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [serialize_message(m) for m in rows]


async def archive_session(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
) -> dict:
    """Archive (soft-delete) a chat session."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    chat.is_archived = True
    await session.commit()
    return {"status": "archived"}


async def rename_session(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    title: str,
) -> dict:
    """Rename a chat session owned by the principal."""
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    chat.title = title.strip()[:120]
    await session.commit()
    await session.refresh(chat)
    return serialize_session(chat)


async def require_session(
    session: AsyncSession,
    principal: Principal,
    session_id: uuid.UUID,
) -> ChatSession:
    chat = (
        await session.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == principal.user_id,
                ChatSession.is_archived.is_(False),
            )
        )
    ).scalar_one_or_none()
    if chat is None:
        raise ResourceNotFoundError()
    return chat


# --------------------------------------------------------------------------- #
# Conversation history + personalization context                             #
# --------------------------------------------------------------------------- #


async def build_user_context(
    session: AsyncSession,
    principal: Principal,
) -> dict:
    """Build a lightweight user context dict for LLM personalization.

    Includes CV count, active application count, and persona so the assistant
    can give tailored advice without making N+1 service calls. Fails silently —
    missing context is better than a broken chat path.
    """
    if not principal.is_authenticated:
        return {}
    context: dict = {"persona": principal.persona or "student"}
    nested = None
    try:
        from sqlalchemy import text as sa_text

        nested = await session.begin_nested()
        result = await session.execute(
            sa_text(
                "SELECT "
                "  (SELECT COUNT(*) FROM cv_profiles "
                "   WHERE user_id = :uid AND deleted_at IS NULL) AS cv_count, "
                "  (SELECT COUNT(*) FROM job_applications "
                "   WHERE applicant_id = :uid "
                "   AND status NOT IN ('rejected','withdrawn')) AS app_count"
            ).params(uid=principal.user_id)
        )
        row = result.fetchone()
        if row:
            context["cv_count"] = int(row.cv_count or 0)
            context["active_application_count"] = int(row.app_count or 0)
        await nested.commit()
    except Exception:
        if nested is not None and nested.is_active:
            await nested.rollback()
        pass
    return context


async def next_seq(session: AsyncSession, session_id: uuid.UUID) -> int:
    """Allocate the next monotonic per-session message ``seq``.

    Explicitly flushes first (the app sessionmaker runs ``autoflush=False``) so
    messages added earlier in the same turn are visible to the MAX() query.
    Pre-0089 rows have ``seq IS NULL`` and are ignored here; readers fall back
    to ``created_at`` for them.
    """
    await session.flush()
    current = (
        await session.execute(
            select(func.max(ChatMessage.seq)).where(ChatMessage.session_id == session_id)
        )
    ).scalar()
    return int(current or 0) + 1


def _convo_rows_query(chat_id: uuid.UUID):
    """Ordered, non-deleted conversation rows for history/memory reads."""
    return (
        select(ChatMessage)
        .where(
            ChatMessage.session_id == chat_id,
            ChatMessage.is_deleted.is_(False),
            ChatMessage.role.in_(_CONVO_ROLES),
        )
        .order_by(ChatMessage.created_at.asc(), ChatMessage.seq.asc().nullsfirst())
    )


def _to_ai_message(m: ChatMessage) -> AIMessage:
    if m.role == "assistant":
        return AIMessage(role="assistant", content=m.content)
    return AIMessage(role="user", content=m.content)  # tool_result → user context


async def load_history(
    session: AsyncSession,
    chat: ChatSession,
) -> list[AIMessage]:
    """Build the LLM history: [persistent memory block] + recent message window.

    Messages already covered by the session's persistent ``memory_summary``
    (the first ``memory_message_count`` conversation rows) are excluded and
    represented by a single injected memory turn instead. Soft-deleted rows
    (edit/regenerate truncation) are always excluded; ordering is ``seq`` with a
    ``created_at`` fallback for pre-seq rows.

    Sessions without persistent memory keep the legacy ephemeral compression:
    when the window still exceeds ``_COMPRESS_THRESHOLD`` the older portion is
    summarized in-flight (never persisted here).
    """
    covered = max(0, int(chat.memory_message_count or 0))
    total = (
        await session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.session_id == chat.id,
                ChatMessage.is_deleted.is_(False),
                ChatMessage.role.in_(_CONVO_ROLES),
            )
        )
    ).scalar_one()
    if covered > total:
        covered = 0  # coverage invalidated (e.g. edit truncated covered rows)

    start = max(covered, int(total) - _MAX_HISTORY_MESSAGES)
    rows = (await session.execute(_convo_rows_query(chat.id).offset(start))).scalars().all()

    history: list[AIMessage] = [_to_ai_message(m) for m in rows]

    if chat.memory_summary and covered:
        return [
            AIMessage(role="assistant", content=f"[Conversation memory]\n{chat.memory_summary}")
        ] + history

    # Legacy ephemeral compression for sessions without persistent memory yet.
    if len(history) > _COMPRESS_THRESHOLD:
        to_summarize = history[: len(history) - _SUMMARY_KEEP_RECENT]
        recent = history[len(history) - _SUMMARY_KEEP_RECENT :]
        summary = await _summarize_history(to_summarize)
        # Inject the summary as an assistant context turn before the recent messages
        history = [AIMessage(role="assistant", content=f"[Context summary]\n{summary}")] + recent

    return history


async def update_session_memory(session: AsyncSession, chat: ChatSession) -> None:
    """Fold old conversation rows into the persistent rolling memory summary.

    Called after a completed turn. When more than ``_MEMORY_DELTA_TRIGGER``
    conversation messages exist beyond the covered count, the DELTA (everything
    beyond coverage except the ``_MEMORY_KEEP_RECENT`` most recent rows) is
    summarized with the cheap chat alias (deterministic truncation offline),
    scrubbed by the output guard, merged into ``memory_summary`` (capped), and
    ``memory_message_count`` is advanced. Best-effort: failures leave the
    session untouched and never break the turn. Commits on success.
    """
    try:
        rows = (await session.execute(_convo_rows_query(chat.id))).scalars().all()
        total = len(rows)
        covered = max(0, int(chat.memory_message_count or 0))
        if covered > total:
            # Edit/regenerate truncated rows the summary claimed to cover —
            # the stored memory can no longer be trusted; reset it.
            chat.memory_summary = None
            chat.memory_message_count = 0
            await session.commit()
            return
        if total - covered <= _MEMORY_DELTA_TRIGGER:
            return
        boundary = total - _MEMORY_KEEP_RECENT
        delta = rows[covered:boundary]
        if not delta:
            return

        summary = await _summarize_history([_to_ai_message(m) for m in delta])
        from app.ai.gateway.output_guard import scrub_text

        summary = scrub_text(summary).strip()
        if not summary:
            return
        merged = f"{chat.memory_summary}\n{summary}" if chat.memory_summary else summary
        # Keep the TAIL when over the cap: recent memory beats stale memory.
        chat.memory_summary = merged[-_MEMORY_MAX_CHARS:]
        chat.memory_message_count = covered + len(delta)
        await session.commit()
    except Exception:  # noqa: BLE001 — memory upkeep must never break the reply
        import logging

        logging.getLogger("ai.chat").warning("ai_chat_memory_update_failed", exc_info=True)


async def refresh_session_title(
    session: AsyncSession, chat: ChatSession, first_text: str
) -> None:
    """Set a concise session title (≤60 chars) after the first exchange.

    One cheap-model call at most; offline (or on any failure) falls back to the
    deterministic truncation of the first user message. Output is scrubbed by
    the output guard before persisting. Best-effort: never raises. Commits on
    success.
    """
    try:
        fallback = first_text.strip()[:_TITLE_MAX_CHARS].strip()
        title = fallback

        from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
        from app.ai.gateway.output_guard import scrub_text

        if real_provider_active():
            try:
                provider = get_provider_for_alias("chat_cheap")
                completion = await provider.complete(
                    [
                        AIMessage(
                            role="system",
                            content=(
                                "You name chat conversations. Return ONLY a short title "
                                "(max 8 words, no quotes, same language as the message) "
                                "for the conversation that starts with the user message."
                            ),
                        ),
                        AIMessage(role="user", content=first_text[:400]),
                    ],
                    alias="chat_cheap",
                    temperature=0.1,
                    max_tokens=30,
                )
                generated = scrub_text(completion.text).strip().strip('"').strip()
                generated = generated.splitlines()[0][:_TITLE_MAX_CHARS].strip()
                if generated:
                    title = generated
            except Exception:  # noqa: BLE001 — non-blocking, keep fallback
                title = fallback

        if title:
            chat.title = title
            await session.commit()
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("ai.chat").warning("ai_chat_title_refresh_failed", exc_info=True)


async def _summarize_history(old_turns: list[AIMessage]) -> str:
    """Summarize a list of old conversation turns into a compact context string.

    Uses the cheap chat alias when real calls are active. Offline (and on any
    provider failure) it degrades to a deterministic truncated concatenation of
    the transcript so context is never silently lost and tests stay stable.
    """
    from app.ai.gateway.factory import get_provider_for_alias, real_provider_active

    if not old_turns:
        return ""

    # Build a compact transcript for summarization
    lines = []
    for m in old_turns:
        tag = "User" if m.role == "user" else "Assistant"
        lines.append(f"{tag}: {m.content[:400]}")
    transcript = "\n".join(lines)

    if not real_provider_active():
        # Deterministic offline fallback: truncated concatenation.
        return transcript[:800]

    summarize_messages = [
        AIMessage(
            role="system",
            content=(
                "You summarize conversation context for an AI assistant. "
                "Return a concise 3-5 sentence summary covering: what the user asked about, "
                "what information was retrieved or discussed, and any key facts established. "
                "Do not invent details. Write in third person."
            ),
        ),
        AIMessage(
            role="user",
            content=f"Summarize this conversation:\n\n{transcript}",
        ),
    ]

    try:
        from app.ai.gateway.output_guard import scrub_text

        provider = get_provider_for_alias("chat_cheap")
        completion = await provider.complete(
            summarize_messages, alias="chat_cheap", temperature=0.1, max_tokens=300
        )
        return scrub_text(completion.text)
    except Exception:
        # Fallback: plain text truncation so context isn't lost
        return transcript[:800]


# --------------------------------------------------------------------------- #
# Message persistence + serialization                                        #
# --------------------------------------------------------------------------- #


async def quick_reply(chat: ChatSession, text: str, session: AsyncSession) -> dict:
    msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=text,
        seq=await next_seq(session, chat.id),
        created_at=datetime.now(UTC),
    )
    session.add(msg)
    return serialize_message(msg)


def serialize_session(chat: ChatSession) -> dict:
    return {
        "id": str(chat.id),
        "title": chat.title,
        "persona": chat.persona,
        "created_at": chat.created_at.isoformat(),
        "last_message_at": chat.last_message_at.isoformat() if chat.last_message_at else None,
    }


def serialize_message(msg: ChatMessage) -> dict:
    return {
        "id": str(msg.id),
        "session_id": str(msg.session_id),
        "role": msg.role,
        "content": msg.content,
        "tool_name": msg.tool_name,
        "tool_args": msg.tool_args,
        "tool_result": msg.tool_result,
        "requires_confirmation": msg.requires_confirmation,
        "confirmed_at": msg.confirmed_at.isoformat() if msg.confirmed_at else None,
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
        "created_at": msg.created_at.isoformat(),
    }
