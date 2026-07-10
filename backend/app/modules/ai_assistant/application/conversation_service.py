"""Conversation management: edit-and-replay, regenerate, and cancel-confirm.

Frozen FE contract (Lane E builds against exactly this):

- ``PATCH /ai/chat/sessions/{sid}/messages/{message_id}`` body ``{"text": str}``
  → edit a USER message: marks it ``edited_at``, soft-deletes every later
  message (truncate), and re-runs the turn through the exact same pipeline as
  ``send_message``. Returns ``{"reply": <send_message-shaped message dict>}``.

- ``POST .../messages/{message_id}/regenerate`` → redo the assistant reply for
  the LAST user message. ``message_id`` may be that user message OR the
  assistant message being redone (both validated to belong to the tail
  exchange). The stale reply chain is soft-deleted and the turn re-runs.

- ``POST .../messages/{message_id}/confirm`` body ``{"decision": "cancel"}`` →
  resolve a pending confirmation card WITHOUT executing anything and persist a
  localized cancellation acknowledgement. (The ``confirm`` decision keeps using
  ``tool_loop.confirm_tool_action``.)

All operations are owner-only (a non-owned session/message is indistinguishable
from a missing one — 404) and quota-gated where they trigger a real model turn.
Soft-deleted rows stay for audit but are excluded from every read path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.application import chat_service, guardrails, usage_service
from app.modules.ai_assistant.application.session_history import (
    next_seq,
    require_session,
    serialize_message,
)
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

_MAX_USER_MSG_LEN = 1500


async def _get_message(
    session: AsyncSession, chat: ChatSession, message_id: uuid.UUID
) -> ChatMessage:
    msg = (
        await session.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == chat.id,
                ChatMessage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if msg is None:
        raise ResourceNotFoundError()
    return msg


def _after_predicate(anchor: ChatMessage):
    """SQL predicate matching messages strictly AFTER ``anchor`` in thread order.

    Uses ``seq`` when the anchor has one (with a ``created_at`` fallback for
    pre-seq rows written by legacy paths), else pure ``created_at``.
    """
    if anchor.seq is not None:
        return or_(
            ChatMessage.seq > anchor.seq,
            and_(ChatMessage.seq.is_(None), ChatMessage.created_at > anchor.created_at),
        )
    return ChatMessage.created_at > anchor.created_at


async def _soft_delete_after(
    session: AsyncSession, chat: ChatSession, anchor: ChatMessage
) -> None:
    """Soft-delete every non-deleted message after ``anchor`` (truncate-and-replay)."""
    await session.execute(
        update(ChatMessage)
        .where(
            ChatMessage.session_id == chat.id,
            ChatMessage.is_deleted.is_(False),
            ChatMessage.id != anchor.id,
            _after_predicate(anchor),
        )
        .values(is_deleted=True)
    )
    await _reset_memory_if_stale(session, chat)


async def _reset_memory_if_stale(session: AsyncSession, chat: ChatSession) -> None:
    """Reset persistent memory when truncation deleted rows the summary covered."""
    covered = int(chat.memory_message_count or 0)
    if covered <= 0:
        return
    from sqlalchemy import func

    remaining = (
        await session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.session_id == chat.id,
                ChatMessage.is_deleted.is_(False),
                ChatMessage.role.in_(("user", "assistant", "tool_result")),
            )
        )
    ).scalar_one()
    if covered > int(remaining):
        chat.memory_summary = None
        chat.memory_message_count = 0


async def _last_user_message(session: AsyncSession, chat: ChatSession) -> ChatMessage | None:
    return (
        (
            await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == chat.id,
                    ChatMessage.role == "user",
                    ChatMessage.is_deleted.is_(False),
                )
                .order_by(ChatMessage.created_at.desc(), ChatMessage.seq.desc().nullslast())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def _replay_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    chat: ChatSession,
    clean: str,
    deferred_refusal: str | None,
    locale: str,
) -> dict:
    reply = await chat_service.run_turn(
        session,
        principal=principal,
        chat=chat,
        clean=clean,
        locale=locale,
        deferred_refusal=deferred_refusal,
    )
    return {"reply": reply}


# --------------------------------------------------------------------------- #
# Edit                                                                         #
# --------------------------------------------------------------------------- #


async def edit_message(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str,
    locale: str = "vi",
) -> dict:
    """Edit a user message, truncate everything after it, and re-run the turn.

    Owner-only (404 otherwise); only ``role == "user"`` messages are editable.
    The new text passes the same policy preflight as ``send_message`` — a
    refused edit still applies the edit/truncation but answers with the policy
    refusal instead of calling a model.
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    msg = await _get_message(session, chat, message_id)
    if msg.role != "user":
        raise ValidationFailedError(
            "Chỉ có thể chỉnh sửa tin nhắn của bạn.",
            details={"reason": "not_a_user_message"},
        )
    await usage_service.enforce_quota(session, principal=principal)

    text = text.strip()[:_MAX_USER_MSG_LEN]
    pre = guardrails.preflight_policy(text, persona=principal.persona, locale=locale)

    now = datetime.now(UTC)
    await _soft_delete_after(session, chat, msg)

    if pre.refused or not pre.clean_text:
        from app.ai.safety.input_guard import sanitize_instruction

        clean_for_store, _ = sanitize_instruction(text)
        msg.content = clean_for_store or "[đã lọc nội dung]"
        msg.edited_at = now
        if pre.refused and pre.refusal_text:
            refusal_text = pre.refusal_text
        else:
            # Unprocessable-after-sanitize edit: deterministic cannot-process reply.
            from app.modules.ai_assistant.application.messages import assistant_message

            refusal_text = assistant_message("chat.cannot_process", locale)
        reply = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=refusal_text,
            seq=await next_seq(session, chat.id),
            created_at=datetime.now(UTC),
        )
        session.add(reply)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return {"reply": serialize_message(reply)}

    msg.content = pre.clean_text
    msg.edited_at = now
    await session.flush()

    return await _replay_turn(
        session,
        principal=principal,
        chat=chat,
        clean=pre.clean_text,
        deferred_refusal=pre.deferred_refusal_text,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Regenerate                                                                   #
# --------------------------------------------------------------------------- #


async def regenerate_reply(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Regenerate the assistant reply for the LAST user message.

    ``message_id`` may be that last user message itself or an assistant message
    from the tail exchange (the one being redone) — anything else is a 422
    (only the tail of the thread can be replayed). The stale reply chain is
    soft-deleted and the turn re-runs through the standard pipeline.
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    msg = await _get_message(session, chat, message_id)

    last_user = await _last_user_message(session, chat)
    if last_user is None:
        raise ValidationFailedError(
            "Chưa có tin nhắn nào để tạo lại câu trả lời.",
            details={"reason": "no_user_message"},
        )

    if msg.role == "user":
        if msg.id != last_user.id:
            raise ValidationFailedError(
                "Chỉ có thể tạo lại câu trả lời cho tin nhắn mới nhất.",
                details={"reason": "not_last_message"},
            )
    elif msg.role in ("assistant", "tool_call"):
        # Must belong to the tail exchange, i.e. come after the last user turn.
        after_last_user = (
            msg.created_at > last_user.created_at
            or (
                msg.created_at == last_user.created_at
                and (msg.seq or 0) > (last_user.seq or 0)
            )
        )
        if not after_last_user:
            raise ValidationFailedError(
                "Chỉ có thể tạo lại câu trả lời mới nhất.",
                details={"reason": "not_last_message"},
            )
    else:
        raise ValidationFailedError(
            "Không thể tạo lại loại tin nhắn này.",
            details={"reason": "not_regenerable"},
        )

    await usage_service.enforce_quota(session, principal=principal)

    # Re-check policy on the replayed text (defense in depth — the stored text
    # was already cleaned when first sent).
    pre = guardrails.preflight_policy(
        last_user.content, persona=principal.persona, locale=locale
    )

    await _soft_delete_after(session, chat, last_user)
    await session.flush()

    if pre.refused or not pre.clean_text:
        from app.modules.ai_assistant.application.messages import assistant_message

        refusal_text = (
            pre.refusal_text
            if pre.refused and pre.refusal_text
            else assistant_message("chat.cannot_process", locale)
        )
        reply = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=refusal_text,
            seq=await next_seq(session, chat.id),
            created_at=datetime.now(UTC),
        )
        session.add(reply)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return {"reply": serialize_message(reply)}

    return await _replay_turn(
        session,
        principal=principal,
        chat=chat,
        clean=pre.clean_text,
        deferred_refusal=pre.deferred_refusal_text,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Confirm (normalized response shape)                                          #
# --------------------------------------------------------------------------- #


async def confirm_tool_action_normalized(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
) -> dict:
    """Execute a pending confirm and ALWAYS return the frozen FE shape.

    ``{"confirmed": <updated tool_call message | false>, "reply": <message>}``.

    The legacy ``tool_loop.confirm_tool_action`` idempotent branch returns a
    bare message dict on a repeat confirm; this wrapper normalizes it — and a
    confirm on a CANCELED card resolves to ``confirmed: false`` (it was settled
    without execution, and can never execute).
    """
    result = await chat_service.confirm_tool_action(
        session,
        principal=principal,
        session_id=session_id,
        message_id=message_id,
    )
    if "confirmed" in result and "reply" in result:
        return result
    # Idempotent repeat: ``result`` is the serialized, already-settled card.
    tool_result = result.get("tool_result")
    if isinstance(tool_result, dict) and (
        tool_result.get("cancelled") or tool_result.get("canceled")
    ):
        return {"confirmed": False, "reply": result}
    return {"confirmed": result, "reply": result}


# --------------------------------------------------------------------------- #
# Cancel a pending confirmation                                                #
# --------------------------------------------------------------------------- #


async def cancel_tool_action(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Resolve a pending ``confirmation_required`` tool card WITHOUT executing.

    Marks the pending message resolved (it can never be executed afterwards —
    the confirm path's idempotency check sees it as already settled), persists a
    localized cancellation acknowledgement, and returns
    ``{"confirmed": False, "reply": <ack message>}``. Cancelling an
    already-cancelled card is an idempotent no-op; cancelling an already
    EXECUTED action is a 409.
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)

    pending = (
        await session.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == chat.id,
                ChatMessage.role == "tool_call",
                ChatMessage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if pending is None:
        raise ResourceNotFoundError()

    already_cancelled = bool(
        isinstance(pending.tool_result, dict)
        and (pending.tool_result.get("cancelled") or pending.tool_result.get("canceled"))
    )
    if not pending.requires_confirmation:
        if already_cancelled:
            # Idempotent repeat cancel — nothing more to do.
            return {"confirmed": False, "reply": serialize_message(pending)}
        raise ConflictError(
            "Thao tác này đã được thực hiện nên không thể hủy.",
            details={"reason": "already_executed"},
        )

    pending.requires_confirmation = False
    # Settle the card: confirm_tool_action's idempotency guard keys on
    # ``confirmed_at`` — setting it here guarantees a later confirm call can
    # never execute a cancelled action (it returns the settled card instead).
    # Both marker spellings are persisted for the FE reload path (it reads
    # ``tool_result.canceled`` on GET messages to distinguish canceled cards).
    pending.confirmed_at = datetime.now(UTC)
    # Merge — keep any preview artifacts attached to the card (e.g. job_draft)
    # so the cancelled card still renders its context after reload.
    prior_artifacts = (
        pending.tool_result.get("artifacts") if isinstance(pending.tool_result, dict) else None
    )
    pending.tool_result = {
        "ok": False,
        "cancelled": True,
        "canceled": True,
        **({"artifacts": prior_artifacts} if prior_artifacts else {}),
    }

    ack = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=guardrails.cancelled_ack(locale),
        seq=await next_seq(session, chat.id),
        created_at=datetime.now(UTC),
    )
    session.add(ack)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    return {"confirmed": False, "reply": serialize_message(ack)}
