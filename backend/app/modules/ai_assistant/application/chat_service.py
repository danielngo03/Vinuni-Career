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

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.prompts.assistant import v1 as assistant_prompt
from app.ai.prompts.assistant_partner import v1 as partner_prompt
from app.ai.retrieval.citation_verify import kb_source_titles, verify_citations
from app.ai.safety.input_guard import sanitize_instruction
from app.ai.safety.output_guard import enforce_keyword_scope
from app.modules.ai_assistant.application import usage_service
from app.modules.ai_assistant.application.agentic import planner
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
    quick_reply,
    rename_session,
    require_session,
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
from app.modules.ai_assistant.domain.models import ChatMessage
from app.shared.exceptions import AIUnavailableError, AuthRequiredError, QuotaExceededError
from app.shared.permissions import Principal

# Real partner persona value assigned at login (app.modules.auth.api.deps ->
# identity.persona; see app.modules.messaging.domain.rules.PARTNER_MEMBER).
# NOTE: ai_assistant's own ToolSpec.persona constant is named "partner_user"
# for historical reasons but is only used to scope tool-list advertising in
# the system prompts (assistant/v1.py, assistant_partner/v1.py) — it is
# unrelated to this real persona string and must not be confused with it.
_PARTNER_PERSONA = "partner_member"

__all__ = [
    "archive_session",
    "confirm_tool_action",
    "create_session",
    "get_session_messages",
    "list_sessions",
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
    """Select the persona system prompt (§8.1 branching, partner assistant spec).

    Partner (recruiter) accounts get the org-scoped ``PARTNER_SYSTEM_PROMPT``;
    everyone else (student, alumni, guest-in-practice-never-reaches-here,
    university staff pending its own future prompt) gets the student prompt.
    """
    if principal.persona == _PARTNER_PERSONA:
        return partner_prompt.PARTNER_SYSTEM_PROMPT
    return assistant_prompt.SYSTEM_PROMPT


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
    )
    session.add(user_msg)

    # Update session title from first user message
    if chat.title is None:
        chat.title = clean[:80]

    if quick_text := fast_path_reply(clean):
        assistant_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="assistant",
            content=quick_text,
            created_at=datetime.now(UTC),
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
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return serialize_message(assistant_msg)

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
    kb_sources: list[str] = []  # §6.5: retrieved doc titles for this turn's citation check

    while iterations < _MAX_TOOL_ITERATIONS:
        iterations += 1
        try:
            raw_response = await llm_complete(
                history,
                db=session,
                user_id=principal.user_id,
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
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
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
        )
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(agent_text):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": serialize_message(assistant_msg)}
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
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    yield {"type": "done", "message": serialize_message(assistant_msg)}
