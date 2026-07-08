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
from weakref import WeakKeyDictionary

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.exceptions import (
    AuthRequiredError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

_MAX_HISTORY_MESSAGES = 20
_COMPRESS_THRESHOLD = 16   # compress when history exceeds this many messages
_SUMMARY_KEEP_RECENT = 6   # keep the N most recent turns after compression

_MAX_TITLE_LEN = 120


# --------------------------------------------------------------------------- #
# Per-session monotonic message ordering (seq)                                #
# --------------------------------------------------------------------------- #
#
# ``ChatMessage.seq`` is a monotonic, per-session ordering index. ``created_at``
# alone is not a reliable order key: several messages produced in one turn (user
# + hidden tool_result(s) + assistant) can share the same microsecond, and the
# edit / regenerate truncate-and-replay logic needs a strict "everything after
# message X" predicate. ``seq`` gives that.
#
# Assignment is done in-memory per turn: an async entry point seeds a cursor from
# the current DB MAX(seq) once (``seed_seq_cursor``), then each message created in
# that turn takes the next value synchronously (``next_seq``) — no intervening
# flush required. Soft-deleted rows keep their seq, so a later turn's MAX(seq)
# never reuses a value that a truncate-and-replay tombstoned.
#
# The cursor is held in a WeakKeyDictionary keyed by the live ``ChatSession``
# instance (not a mapped column), so it is scoped to the request that loaded the
# session and is dropped automatically when that instance is garbage-collected.
_seq_cursors: WeakKeyDictionary[ChatSession, int] = WeakKeyDictionary()


async def seed_seq_cursor(session: AsyncSession, chat: ChatSession) -> None:
    """Seed the per-turn seq cursor from the current DB MAX(seq) for this session.

    Idempotent per ``chat`` instance: only queries the first time it is called in
    a turn. Every async entry point that will create messages (send / stream /
    confirm / regenerate / edit) calls this before allocating any seq. The MAX is
    computed over ALL rows (including soft-deleted ones) so a truncate-and-replay
    never reuses a tombstoned seq.
    """
    if chat in _seq_cursors:
        return
    current_max = (
        await session.execute(
            select(func.coalesce(func.max(ChatMessage.seq), 0)).where(
                ChatMessage.session_id == chat.id
            )
        )
    ).scalar_one()
    _seq_cursors[chat] = int(current_max or 0)


def next_seq(chat: ChatSession) -> int:
    """Reserve and return the next monotonic seq for a message in this turn.

    Requires ``seed_seq_cursor`` to have run for this ``chat`` instance earlier in
    the same turn. Falls back to a 0 base if unseeded (should not happen in the
    real call paths) so an ordering index is always produced.
    """
    cursor = _seq_cursors.get(chat, 0) + 1
    _seq_cursors[chat] = cursor
    return cursor


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
        # Org context for partner (recruiter) chats — NULL for students / no-org
        # principals; used for org-scoped audit and energy metering attribution.
        org_id=principal.org_id,
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
        await session.execute(
            select(ChatSession)
            .where(
                ChatSession.user_id == principal.user_id,
                ChatSession.is_archived.is_(False),
            )
            .order_by(ChatSession.last_message_at.desc().nullslast())
            .limit(limit)
        )
    ).scalars().all()
    return [serialize_session(r) for r in rows]


async def get_session_messages(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    limit: int = 50,
) -> list[dict]:
    """Return the most recent messages for a session (owner-only).

    Excludes hidden ``tool_result`` rows and soft-deleted (superseded) rows, and
    orders by the monotonic ``seq`` (falling back to ``created_at`` for any row
    whose seq is NULL — e.g. pre-migration rows / ad-hoc fixtures).
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat.id)
            .where(ChatMessage.role != "tool_result")
            .where(ChatMessage.is_deleted.is_(False))
            .order_by(
                # NULL-seq rows sort last (IS NULL → True/1), then seq asc, then
                # created_at as the portable tiebreaker (works on SQLite + PG).
                ChatMessage.seq.is_(None),
                ChatMessage.seq.asc(),
                ChatMessage.created_at.asc(),
            )
            .limit(limit)
        )
    ).scalars().all()
    return [serialize_message(m) for m in rows]


async def rename_session(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    title: str,
) -> dict:
    """Rename a chat session (owner-only).

    Turns the auto-generated first-message title into a user-editable one. The
    title is stripped and must be 1..120 characters after stripping; empty /
    whitespace-only titles are rejected with a user-safe validation error.
    Ownership is enforced by ``require_session`` (a non-owner sees 404, never
    another user's session).
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    clean = (title or "").strip()
    if not clean:
        raise ValidationFailedError(
            "Tên cuộc trò chuyện không được để trống.",
            details={"reason": "title_empty"},
        )
    if len(clean) > _MAX_TITLE_LEN:
        raise ValidationFailedError(
            "Tên cuộc trò chuyện quá dài (tối đa 120 ký tự).",
            details={"reason": "title_too_long"},
        )
    chat.title = clean
    await session.commit()
    return serialize_session(chat)


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


async def load_history(
    session: AsyncSession,
    chat: ChatSession,
) -> list[AIMessage]:
    """Load the last N messages and convert to AIMessage list for the LLM.

    When the session has more than _COMPRESS_THRESHOLD messages, the older
    portion is summarized into a single injected summary message so the context
    window stays bounded without losing long-term conversational context.
    """
    rows = (
        await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat.id)
            .where(ChatMessage.is_deleted.is_(False))
            .order_by(
                # Most recent N by seq (NULL-seq rows sort last), created_at as
                # the portable tiebreaker; reversed below to chronological order.
                ChatMessage.seq.is_(None),
                ChatMessage.seq.desc(),
                ChatMessage.created_at.desc(),
            )
            .limit(_MAX_HISTORY_MESSAGES)
        )
    ).scalars().all()
    rows = list(reversed(rows))

    history: list[AIMessage] = []
    for m in rows:
        if m.role == "user":
            history.append(AIMessage(role="user", content=m.content))
        elif m.role == "assistant":
            history.append(AIMessage(role="assistant", content=m.content))
        elif m.role == "tool_result":
            history.append(AIMessage(role="user", content=m.content))

    # Compress old context when history exceeds the threshold.
    # Keep the most recent _SUMMARY_KEEP_RECENT turns verbatim; summarize the rest.
    if len(history) > _COMPRESS_THRESHOLD:
        to_summarize = history[: len(history) - _SUMMARY_KEEP_RECENT]
        recent = history[len(history) - _SUMMARY_KEEP_RECENT :]
        summary = await _summarize_history(to_summarize)
        # Inject the summary as an assistant context turn before the recent messages
        history = [AIMessage(role="assistant", content=f"[Context summary]\n{summary}")] + recent

    return history


async def _summarize_history(old_turns: list[AIMessage]) -> str:
    """Summarize a list of old conversation turns into a compact context string.

    Uses the cheap chat model. Falls back to a plain concatenation on AI failure
    so the context is never silently lost.
    """
    from app.ai.gateway import runtime_config
    from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
    from app.ai.gateway.offline import OfflineProvider

    if not old_turns:
        return ""

    # Build a compact transcript for summarization
    lines = []
    for m in old_turns:
        tag = "User" if m.role == "user" else "Assistant"
        lines.append(f"{tag}: {m.content[:400]}")
    transcript = "\n".join(lines)

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

    alias = runtime_config.current().chat_model_alias
    if real_provider_active():
        try:
            provider = get_provider_for_alias(alias)
        except Exception:
            provider = OfflineProvider()
    else:
        provider = OfflineProvider()

    try:
        from app.ai.gateway.output_guard import scrub_text
        completion = await provider.complete(
            summarize_messages, alias=alias, temperature=0.1, max_tokens=300
        )
        return scrub_text(completion.text)
    except Exception:
        # Fallback: plain text truncation so context isn't lost
        return transcript[:800]


# --------------------------------------------------------------------------- #
# Message persistence + serialization                                        #
# --------------------------------------------------------------------------- #


def quick_reply(chat: ChatSession, text: str, session: AsyncSession) -> dict:
    msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=text,
        created_at=datetime.now(UTC),
        seq=next_seq(chat),
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
        "created_at": msg.created_at.isoformat(),
        "edited_at": msg.edited_at.isoformat() if msg.edited_at else None,
    }
