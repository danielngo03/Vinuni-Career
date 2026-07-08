"""AI assistant chat service (thin orchestrator).

Manages chat turns end to end: dispatches LLM completions, runs the tool-calling
loop, and persists/serializes messages. All LLM calls go through the gateway;
provider/model internals never reach the caller.

Session/message persistence lives in ``session_history``; the ReAct tool-calling
loop primitives (LLM calls, tool-call parsing, agent-plan execution, post-
confirmation execution) live in ``tool_loop``; deterministic response text
(fast-path replies, AI-unavailable copy, SSE chunking) lives in
``response_formatter``. This module composes them into ``send_message`` /
``stream_message`` and re-exports the session CRUD + confirmation entry points
routers depend on.

Tool dispatch rules (AI_PRODUCT_SPEC.md §4):
- read_only tools: dispatched immediately, result injected as assistant context.
- confirmation_required tools: NOT dispatched here — the router returns a pending
  tool_call message that the frontend must display as a confirmation card.
  The user must call POST /confirm with the message_id to execute.

Max iterations per turn: 8 (AI rule: MAX_ITERATIONS = 8, §4.1); at most
MAX_TOOL_CALLS_PER_TURN = 12 tool dispatches per turn (both enforced via
``tool_loop`` constants, imported below).
Streaming: stream_message() is an async generator that yields SSE event dicts.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy.service import build_usage_context, charge_units
from app.ai.gateway.base import AIMessage
from app.ai.observability.billable_usage import FEATURE_CHATBOT, record_billable_usage
from app.ai.prompts.assistant import v1 as assistant_prompt
from app.ai.retrieval.citation_verify import kb_source_titles, verify_citations
from app.ai.safety.input_guard import sanitize_instruction
from app.ai.safety.output_guard import enforce_keyword_scope
from app.ai.safety.policy_orchestrator import ACTION_REFUSE, READ_ONLY, check_policy
from app.modules.ai_assistant.application import usage_service
from app.modules.ai_assistant.application.agentic import planner
from app.modules.ai_assistant.application.agentic.persona_registry import (
    resolve_persona_profile,
)
from app.modules.ai_assistant.application.agents import build_agent_plan
from app.modules.ai_assistant.application.messages import assistant_message
from app.modules.ai_assistant.application.response_formatter import (
    ai_unavailable_reply,
    fast_path_reply,
    local_stream_chunks,
    strip_tool_call_json,
)
from app.modules.ai_assistant.application.session_history import (
    archive_session,
    build_user_context,
    create_session,
    get_session_messages,
    list_sessions,
    load_history,
    next_seq,
    quick_reply,
    rename_session,
    require_session,
    seed_seq_cursor,
    serialize_message,
)
from app.modules.ai_assistant.application.tool_loop import (
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_TURN,
    agent_plan_requires_confirmation,
    confirm_tool_action,
    create_confirmation_message,
    execute_agent_plan,
    llm_complete,
    parse_tool_call,
    persist_tool_result,
)
from app.modules.ai_assistant.application.tool_registry import TOOL_SPECS, dispatch_tool
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.exceptions import (
    AIUnavailableError,
    AuthRequiredError,
    QuotaExceededError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

__all__ = [
    "archive_session",
    "confirm_tool_action",
    "create_session",
    "edit_message",
    "get_session_messages",
    "list_sessions",
    "regenerate_last",
    "rename_session",
    "send_message",
    "stream_message",
]

# ReAct loop bound for one user message (AI_PRODUCT_SPEC.md §4.1: MAX_ITERATIONS=8).
# Re-exported from tool_loop so both modules share one source of truth.
_MAX_TOOL_ITERATIONS = MAX_ITERATIONS
_MAX_USER_MSG_LEN = 1500

_logger = logging.getLogger("ai.rag")


def _system_prompt_for(principal: Principal) -> str:
    """Select the persona system prompt via the persona registry (§8.1).

    Resolves ``principal.persona`` to its :class:`PersonaProfile` (one source of
    truth for prompt + planner + tool surface). Student/alumni get the student
    prompt, partner members the org-scoped partner prompt, university staff the
    university prompt; an unknown persona degrades to the student prompt.
    """
    return resolve_persona_profile(principal.persona).system_prompt


def _apply_citation_guard(final_text: str, kb_sources: list[str]) -> str:
    """Run §6.5 citation verification when this turn used ``knowledge_base_query``.

    Strips any citation naming a document that was not actually retrieved and
    logs metadata only (never raw answer/citation text — §15).
    """
    if not kb_sources:
        return final_text
    check = verify_citations(final_text, kb_sources)
    if check.cited_count:
        _logger.info(
            "ai_rag_citation_check",
            extra={
                "cited_count": check.cited_count,
                "grounded_count": check.grounded_count,
                "hallucination_risk": check.hallucination_risk,
            },
        )
    return check.clean_answer


def _apply_topical_scope_guard(final_text: str, *, used_tool: bool, locale: str = "vi") -> str:
    """Fallback keyword scope-check on the model's OWN final answer (ai.md item 1).

    See ``app.ai.safety.output_guard.enforce_keyword_scope`` for the full
    design rationale. Skipped whenever a tool was dispatched this turn — a
    tool-grounded answer is trusted by construction.
    """
    return enforce_keyword_scope(
        final_text,
        domain_keywords=planner.DOMAIN_KEYWORDS,
        refusal_text=planner.out_of_scope_reply(locale),
        skip=used_tool,
    )


async def _charge_chatbot_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    chat_id: uuid.UUID,
    idempotency_key: uuid.UUID,
) -> None:
    """Charge exactly one FEATURE_CHATBOT credit for a completed chat turn.

    Called once per turn ONLY when a genuine model answer was produced (never for
    fast-path/agent-plan replies, confirmation-pending turns, or the
    AI-unavailable fallback — those callers do not invoke this). The idempotency
    key namespaces the ledger write: ``send_message`` / ``stream_message`` pass
    the *user message id* (so a redelivery / retry of the same turn is a no-op and
    never double-charges), while regenerate / edit-and-rerun pass a fresh key per
    attempt so each re-run is metered as its own normal chat turn.
    ``record_billable_usage`` is idempotent on that key.

    Scope: partner members debit the shared ORG energy pool, students their own
    user scope — ``build_usage_context`` resolves the billing scope. Best-effort:
    a metering failure must never break the reply, so all errors are swallowed.
    """
    try:
        ctx = build_usage_context(
            principal,
            feature_key=FEATURE_CHATBOT,
            task_type="ai_assistant_chat",
            session_id=chat_id,
            idempotency_parts=(idempotency_key,),
        )
        await record_billable_usage(
            session,
            ctx=ctx,
            result_status="success",
            base_units=charge_units(FEATURE_CHATBOT),
        )
    except Exception:  # noqa: BLE001 — accounting must never break the reply
        _logger.warning("chatbot_turn_metering_failed", exc_info=True)


async def send_message(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    text: str,
    locale: str = "vi",
) -> dict:
    """Send a user message and return the assistant's response.

    Runs up to _MAX_TOOL_ITERATIONS read-only tool calls transparently.
    Returns the final assistant message dict. ``locale`` ("vi"/"en") selects the
    language of deterministic user-facing assistant text; unknown values fall
    back to "vi".
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    # Daily/weekly allowance gate — refuses with 409 QUOTA_EXCEEDED when either
    # window is exhausted (an exhausted week blocks even with daily room left).
    await usage_service.enforce_quota(session, principal=principal)
    # Seed the per-turn monotonic seq cursor before any message is created.
    await seed_seq_cursor(session, chat)

    # Sanitize user input
    text = text.strip()[: _MAX_USER_MSG_LEN]
    clean, _ = sanitize_instruction(text)
    if not clean:
        reply = quick_reply(
            chat,
            assistant_message("chat.cannot_process", locale),
            session,
        )
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return reply

    # Persist user message
    user_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="user",
        content=clean,
        created_at=datetime.now(UTC),
        seq=next_seq(chat),
    )
    session.add(user_msg)

    # Update session title from first user message
    if chat.title is None:
        chat.title = clean[:80]

    # Idempotency key = user message id: a redelivery of the same turn is a no-op.
    return await _generate_reply_for(
        session,
        principal=principal,
        chat=chat,
        clean=clean,
        charge_key=user_msg.id,
        locale=locale,
    )


async def _generate_reply_for(
    session: AsyncSession,
    *,
    principal: Principal,
    chat: ChatSession,
    clean: str,
    charge_key: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Run one assistant turn for an already-persisted user message.

    Shared by ``send_message`` (fresh user message) and the regenerate /
    edit-and-rerun flows (existing user message, later messages already
    truncated). Runs the fast-path reply, the deterministic agent plan, the
    intent-level safety gate, and the LLM tool-calling loop exactly as before,
    persists the assistant reply, meters a genuine model answer via
    ``_charge_chatbot_turn`` (idempotent on ``charge_key``), commits, and returns
    the serialized assistant message.

    Assumes the caller has already checked auth + quota and seeded the seq cursor
    (``seed_seq_cursor`` here is an idempotent safety net).
    """
    await seed_seq_cursor(session, chat)

    if quick_text := fast_path_reply(clean):
        assistant_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=quick_text,
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return serialize_message(assistant_msg)

    if agent_plan := await build_agent_plan(
        clean,
        principal=principal,
        session=session,
        chat=chat,
    ):
        if agent_plan_requires_confirmation(agent_plan):
            confirm_msg = create_confirmation_message(chat, agent_plan)
            session.add(confirm_msg)
            chat.last_message_at = datetime.now(UTC)
            await session.commit()
            return serialize_message(confirm_msg)

        agent_text = await execute_agent_plan(
            agent_plan,
            chat=chat,
            session=session,
            principal=principal,
            ai_unavailable_reply=ai_unavailable_reply(),
        )
        assistant_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=agent_text,
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return serialize_message(assistant_msg)

    # Intent-level safety gate on the USER turn before the LLM loop — mirrors
    # AiTaskRunner._sanitize_messages so the chat path is guarded identically to
    # batch AI tasks. Harmful / boundary-probe / external-source intents are
    # refused with a user-safe message and NO model call (never charged). The
    # deterministic planner replies above are already scope-correct, so this only
    # guards turns that actually reach the LLM (open partner/university turns).
    policy = check_policy(clean, READ_ONLY, locale=locale)
    if policy.action == ACTION_REFUSE:
        refusal = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=policy.refusal_message or ai_unavailable_reply(),
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(refusal)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return serialize_message(refusal)

    # Build LLM conversation history
    history = await load_history(session, chat)

    # Inject user profile context so the LLM can give personalized advice
    user_context = await build_user_context(session, principal)
    history.append(
        AIMessage(
            role="user",
            content=assistant_prompt.build_user_message(clean, context=user_context),
        )
    )

    # Tool dispatch loop (read-only only; max MAX_ITERATIONS LLM turns, max
    # MAX_TOOL_CALLS_PER_TURN tool dispatches — AI_PRODUCT_SPEC.md §4.1).
    system_prompt = _system_prompt_for(principal)
    iterations = 0
    tool_call_count = 0
    used_tool = False
    final_text: str | None = None
    # True only when the loop produced a genuine model answer (the one billable
    # outcome). Stays False for AI-unavailable / unknown-tool / tool-cap
    # fallbacks so we never charge for a non-answer.
    chargeable = False
    kb_sources: list[str] = []  # §6.5: retrieved doc titles for this turn's citation check

    while iterations < _MAX_TOOL_ITERATIONS:
        iterations += 1
        try:
            raw_response = await llm_complete(
                history,
                db=session,
                user_id=principal.user_id,
                org_id=principal.org_id,
                session_id=chat.id,
                system_prompt=system_prompt,
            )
        except AIUnavailableError:
            final_text = ai_unavailable_reply()
            break

        # Check if the model wants to call a tool
        tool_call = parse_tool_call(raw_response)
        if tool_call is None:
            final_text = _apply_citation_guard(raw_response, kb_sources)
            final_text = _apply_topical_scope_guard(final_text, used_tool=used_tool)
            chargeable = True
            break

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        spec = TOOL_SPECS.get(tool_name)

        if spec is None:
            # Unknown tool — stop and ask for clarification
            final_text = "Tôi gặp sự cố khi xử lý yêu cầu này. Vui lòng thử lại."
            break

        if spec.permission_class == "confirmation_required":
            # Do NOT execute — return a pending confirmation message
            confirm_msg = ChatMessage(
                id=uuid.uuid4(),
                session_id=chat.id,
                role="tool_call",
                content=f"Đang chuẩn bị thực hiện: {tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
                requires_confirmation=True,
                created_at=datetime.now(UTC),
                seq=next_seq(chat),
            )
            session.add(confirm_msg)
            chat.last_message_at = datetime.now(UTC)
            await session.commit()
            return serialize_message(confirm_msg)

        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            # §4.1 hard cap reached — stop dispatching further tools this turn.
            final_text = ai_unavailable_reply()
            break

        # Execute read-only tool
        result = await dispatch_tool(tool_name, tool_args, session=session, principal=principal)
        tool_call_count += 1
        used_tool = True
        persist_tool_result(
            session,
            chat=chat,
            tool_name=tool_name,
            tool_args=tool_args,
            result=result,
        )
        if tool_name == "knowledge_base_query" and result.get("ok"):
            kb_sources = kb_source_titles(result.get("chunks") or [])

        # Inject tool result as a context message for the next LLM turn
        tool_context = assistant_prompt.build_tool_result_message(tool_name, result)
        history.append(AIMessage(role="assistant", content=raw_response))
        history.append(AIMessage(role="user", content=tool_context))

    if final_text is None:
        final_text = ai_unavailable_reply()

    # Persist assistant message
    assistant_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=final_text,
        created_at=datetime.now(UTC),
        seq=next_seq(chat),
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)

    # Meter one FEATURE_CHATBOT credit for this turn on a genuine model answer
    # (best-effort, idempotent on ``charge_key``). Committed together with the
    # assistant message below.
    if chargeable:
        await _charge_chatbot_turn(
            session, principal=principal, chat_id=chat.id, idempotency_key=charge_key
        )

    await session.commit()

    return serialize_message(assistant_msg)


async def stream_message(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    text: str,
) -> AsyncGenerator[dict, None]:
    """Stream the assistant reply for a user message as a series of SSE event dicts.

    Yields event dicts; the router serialises each to a JSON SSE line. Events:
    - ``{"type": "token", "text": "..."}``        — partial text (simulated)
    - ``{"type": "tool_call", "name": "..."}``    — before tool dispatch
    - ``{"type": "tool_result", "name": "...", "ok": bool}`` — after dispatch
    - ``{"type": "done", "message": {...}}``       — final persisted message
    - ``{"type": "error", "code": "..."}``         — on failure

    The first non-tool response is streamed through the gateway when the
    selected provider supports token streaming. Tool-call JSON is buffered and
    never shown to the user.
    """
    if not principal.is_authenticated:
        yield {"type": "error", "code": "auth_required"}
        return

    try:
        await usage_service.enforce_quota(session, principal=principal)
    except QuotaExceededError:
        yield {"type": "error", "code": "quota_exceeded"}
        return

    try:
        chat = await require_session(session, principal, session_id)
    except Exception:
        yield {"type": "error", "code": "session_not_found"}
        return

    # Seed the per-turn monotonic seq cursor before any message is created.
    await seed_seq_cursor(session, chat)

    # Sanitize input
    clean_text = text.strip()[: _MAX_USER_MSG_LEN]
    clean, _ = sanitize_instruction(clean_text)
    if not clean:
        yield {"type": "error", "code": "invalid_message"}
        return

    # Persist user message
    user_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="user",
        content=clean,
        created_at=datetime.now(UTC),
        seq=next_seq(chat),
    )
    session.add(user_msg)
    if chat.title is None:
        chat.title = clean[:80]

    yield {"type": "status", "code": "received"}

    if quick_text := fast_path_reply(clean):
        assistant_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=quick_text,
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(quick_text):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": serialize_message(assistant_msg)}
        return

    if agent_plan := await build_agent_plan(
        clean,
        principal=principal,
        session=session,
        chat=chat,
    ):
        if agent_plan_requires_confirmation(agent_plan):
            yield {"type": "status", "code": "confirming_action"}
            confirm_msg = create_confirmation_message(chat, agent_plan)
            session.add(confirm_msg)
            chat.last_message_at = datetime.now(UTC)
            await session.commit()
            yield {"type": "done", "message": serialize_message(confirm_msg)}
            return

        if agent_plan.action == "tool" and agent_plan.tool_name:
            yield {"type": "status", "code": agent_plan.status_code}
            yield {"type": "tool_call", "name": agent_plan.tool_name}
        else:
            yield {"type": "status", "code": "responding"}
        agent_text = await execute_agent_plan(
            agent_plan,
            chat=chat,
            session=session,
            principal=principal,
            ai_unavailable_reply=ai_unavailable_reply(),
        )
        if agent_plan.action == "tool" and agent_plan.tool_name:
            yield {"type": "tool_result", "name": agent_plan.tool_name, "ok": True}
        assistant_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=agent_text,
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(agent_text):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": serialize_message(assistant_msg)}
        return

    # Intent-level safety gate before the LLM loop (see send_message): refuse
    # harmful / boundary-probe / external-source turns with a user-safe message,
    # streamed like any other reply, with NO model call (never charged).
    policy = check_policy(clean, READ_ONLY)
    if policy.action == ACTION_REFUSE:
        refusal_text = policy.refusal_message or ai_unavailable_reply()
        refusal = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=refusal_text,
            created_at=datetime.now(UTC),
            seq=next_seq(chat),
        )
        session.add(refusal)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(refusal_text):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": serialize_message(refusal)}
        return

    yield {"type": "status", "code": "retrieving_context"}
    history = await load_history(session, chat)
    user_context = await build_user_context(session, principal)
    history.append(
        AIMessage(
            role="user",
            content=assistant_prompt.build_user_message(clean, context=user_context),
        )
    )

    system_prompt = _system_prompt_for(principal)
    iterations = 0
    tool_call_count = 0
    used_tool = False
    final_text: str | None = None
    final_text_streamed = False
    # True only when the loop produced a genuine model answer (the one billable
    # outcome) — see send_message for the rationale.
    chargeable = False
    kb_sources: list[str] = []  # §6.5: retrieved doc titles for this turn's citation check

    while iterations < _MAX_TOOL_ITERATIONS:
        iterations += 1
        yield {
            "type": "status",
            "code": "thinking" if iterations == 1 else "synthesizing",
        }
        try:
            raw_response = await llm_complete(
                history,
                db=session,
                user_id=principal.user_id,
                org_id=principal.org_id,
                session_id=chat.id,
                system_prompt=system_prompt,
            )
        except AIUnavailableError:
            final_text = ai_unavailable_reply()
            final_text_streamed = False
            break

        if not raw_response:
            final_text = ai_unavailable_reply()
            final_text_streamed = False
            break

        tool_call = parse_tool_call(raw_response)
        if tool_call is None:
            final_text = _apply_citation_guard(strip_tool_call_json(raw_response), kb_sources)
            final_text = _apply_topical_scope_guard(final_text, used_tool=used_tool)
            final_text_streamed = False
            chargeable = True
            break

        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})
        spec = TOOL_SPECS.get(tool_name)

        if spec is None:
            final_text = "Tôi gặp sự cố khi xử lý yêu cầu này. Vui lòng thử lại."
            break

        if spec.permission_class == "confirmation_required":
            confirm_msg = ChatMessage(
                id=uuid.uuid4(),
                session_id=chat.id,
                role="tool_call",
                content=f"Đang chuẩn bị thực hiện: {tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
                requires_confirmation=True,
                created_at=datetime.now(UTC),
                seq=next_seq(chat),
            )
            session.add(confirm_msg)
            chat.last_message_at = datetime.now(UTC)
            await session.commit()
            yield {"type": "done", "message": serialize_message(confirm_msg)}
            return

        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            # §4.1 hard cap reached — stop dispatching further tools this turn.
            final_text = ai_unavailable_reply()
            final_text_streamed = False
            break

        yield {"type": "status", "code": "using_tool"}
        yield {"type": "tool_call", "name": tool_name}
        result = await dispatch_tool(tool_name, tool_args, session=session, principal=principal)
        tool_call_count += 1
        used_tool = True
        yield {"type": "tool_result", "name": tool_name, "ok": result.get("ok", False)}
        persist_tool_result(
            session,
            chat=chat,
            tool_name=tool_name,
            tool_args=tool_args,
            result=result,
        )
        if tool_name == "knowledge_base_query" and result.get("ok"):
            kb_sources = kb_source_titles(result.get("chunks") or [])

        tool_context = assistant_prompt.build_tool_result_message(tool_name, result)
        history.append(AIMessage(role="assistant", content=raw_response))
        history.append(AIMessage(role="user", content=tool_context))

    if final_text is None:
        final_text = ai_unavailable_reply()
        final_text_streamed = False

    if not final_text_streamed:
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(final_text):
            yield {"type": "token", "text": chunk}

    # Persist and emit done
    assistant_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=final_text,
        created_at=datetime.now(UTC),
        seq=next_seq(chat),
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)

    # Meter one FEATURE_CHATBOT credit for this turn on a genuine model answer
    # (best-effort, idempotent on the user message id).
    if chargeable:
        await _charge_chatbot_turn(
            session, principal=principal, chat_id=chat.id, idempotency_key=user_msg.id
        )

    await session.commit()

    yield {"type": "done", "message": serialize_message(assistant_msg)}


# --------------------------------------------------------------------------- #
# Conversation management: regenerate + edit-and-rerun (truncate-and-replay)  #
# --------------------------------------------------------------------------- #
#
# v1 semantics are TRUNCATE-AND-REPLAY (not branching): superseded messages are
# soft-deleted (``is_deleted=True``, seq retained so a later MAX(seq) never
# reuses the value) and the assistant is re-run from the surviving history via
# the same ``_generate_reply_for`` path as a normal turn — identical
# enforce_quota + safety policy + metering. Re-runs use a fresh idempotency key
# so each attempt is metered as its own chat turn.


async def _messages_after(
    session: AsyncSession, *, chat: ChatSession, pivot: ChatMessage
) -> list[ChatMessage]:
    """Return the non-deleted messages ordered strictly after ``pivot``.

    Uses ``seq`` when the pivot has one (the normal case); falls back to
    ``created_at`` for a pre-migration pivot whose seq is NULL.
    """
    after = (
        ChatMessage.seq > pivot.seq
        if pivot.seq is not None
        else ChatMessage.created_at > pivot.created_at
    )
    rows = (
        await session.execute(
            select(ChatMessage).where(
                ChatMessage.session_id == chat.id,
                ChatMessage.is_deleted.is_(False),
                after,
            )
        )
    ).scalars().all()
    return list(rows)


async def regenerate_last(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Regenerate the assistant reply to the most recent user message (owner-only).

    Soft-deletes the most recent assistant message plus any trailing tool_call /
    tool_result rows produced after the last user message, then re-runs the
    assistant from the remaining history. Returns the new assistant message.

    Raises a user-safe validation error when there is nothing to regenerate: no
    user message yet, or no assistant reply following the last user message (e.g.
    the last turn is still a pending confirmation card).
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)
    # Normal-turn quota gate BEFORE mutating anything — an exhausted week must not
    # destroy the existing reply.
    await usage_service.enforce_quota(session, principal=principal)

    pivot = (
        await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == chat.id,
                ChatMessage.role == "user",
                ChatMessage.is_deleted.is_(False),
            )
            .order_by(
                ChatMessage.seq.is_(None),
                ChatMessage.seq.desc(),
                ChatMessage.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if pivot is None:
        raise ValidationFailedError(
            "Chưa có tin nhắn nào để tạo lại câu trả lời.",
            details={"reason": "no_user_message"},
        )

    trailing = await _messages_after(session, chat=chat, pivot=pivot)
    if not any(m.role == "assistant" for m in trailing):
        raise ValidationFailedError(
            "Chưa có câu trả lời nào để tạo lại.",
            details={"reason": "no_assistant_reply"},
        )

    for message in trailing:
        message.is_deleted = True
    await session.flush()

    # Fresh idempotency key so this re-run is metered as its own chat turn.
    return await _generate_reply_for(
        session,
        principal=principal,
        chat=chat,
        clean=pivot.content,
        charge_key=uuid.uuid4(),
        locale=locale,
    )


async def edit_message(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    text: str,
    locale: str = "vi",
) -> dict:
    """Edit a sent USER message in place and re-run from it (owner-only).

    Stamps ``edited_at`` and stores the new sanitized content on the target user
    message, soft-deletes every later message in the session, then re-runs the
    assistant from the edited message. Returns the new assistant reply.

    Rejects editing a non-user message (422) or a message the caller does not own
    — a foreign message id or a message in another user's session resolves to 404
    via ``require_session`` + the session-scoped lookup.
    """
    if not principal.is_authenticated:
        raise AuthRequiredError()
    chat = await require_session(session, principal, session_id)

    target = (
        await session.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id,
                ChatMessage.session_id == chat.id,
                ChatMessage.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError()
    if target.role != "user":
        raise ValidationFailedError(
            "Chỉ có thể chỉnh sửa tin nhắn của bạn.",
            details={"reason": "not_user_message"},
        )

    clean_text = text.strip()[: _MAX_USER_MSG_LEN]
    clean, _ = sanitize_instruction(clean_text)
    if not clean:
        raise ValidationFailedError(
            "Nội dung tin nhắn không được để trống.",
            details={"reason": "empty_message"},
        )

    # Normal-turn quota gate BEFORE mutating anything.
    await usage_service.enforce_quota(session, principal=principal)

    target.content = clean
    target.edited_at = datetime.now(UTC)

    trailing = await _messages_after(session, chat=chat, pivot=target)
    for message in trailing:
        message.is_deleted = True
    await session.flush()

    # Fresh idempotency key so this re-run is metered as its own chat turn.
    return await _generate_reply_for(
        session,
        principal=principal,
        chat=chat,
        clean=clean,
        charge_key=uuid.uuid4(),
        locale=locale,
    )
