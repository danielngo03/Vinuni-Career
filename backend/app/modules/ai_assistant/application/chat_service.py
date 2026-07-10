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

Guardrail layering (AI_PRODUCT_SPEC §9, wired here):
- EVERY user turn passes ``guardrails.preflight_policy`` (the central
  ``policy_orchestrator`` pipeline) BEFORE the fast-path, the deterministic
  planner, and the native tool loop. Refusals are persisted and returned
  without any model call and without consuming quota/energy.
- Partner turns additionally run a deterministic post-LLM recruiting-domain
  scope guard on pure-text answers (``guardrails.partner_scope_guard``).

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
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.prompts.assistant import v1 as assistant_prompt
from app.ai.prompts.assistant_partner import v3 as partner_prompt_native
from app.ai.retrieval.citation_verify import kb_source_titles, verify_citations
from app.ai.safety.input_guard import sanitize_instruction
from app.ai.safety.output_guard import enforce_keyword_scope
from app.modules.ai_assistant.application import (
    guardrails,
    model_router,
    native_loop,
    turn_telemetry,
    usage_service,
)
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
    next_seq,
    quick_reply,
    refresh_session_title,
    rename_session,
    require_session,
    serialize_message,
    update_session_memory,
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
    "run_turn",
    "send_message",
    "stream_message",
]

# ReAct loop bound for one user message (AI_PRODUCT_SPEC.md §4.1: MAX_ITERATIONS=8).
# Re-exported from tool_loop so both modules share one source of truth.
_MAX_TOOL_ITERATIONS = MAX_ITERATIONS
_MAX_USER_MSG_LEN = 1500

_logger = logging.getLogger("ai.rag")


def _is_partner(principal: Principal) -> bool:
    """True for any partner-recruiter persona (routes to the native tool loop)."""
    return bool(principal.persona) and principal.persona.startswith("partner")


def _system_prompt_for(principal: Principal) -> str:
    """Select the persona system prompt (§8.1 branching, partner assistant spec).

    Partner (recruiter) accounts route through the native loop and never reach
    this; everyone else (student, alumni, university staff pending its own
    future prompt) gets the student prompt.
    """
    return assistant_prompt.SYSTEM_PROMPT


def _chat_alias() -> str:
    from app.ai.gateway import runtime_config

    return runtime_config.current().chat_model_alias


def _new_assistant_message(chat, text: str, seq: int) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=text,
        seq=seq,
        created_at=datetime.now(UTC),
    )


async def _persist_turn_refusal(
    session: AsyncSession,
    *,
    principal: Principal,
    chat,
    user_text: str,
    refusal_text: str,
    guard_flags: list[str],
    persist_user: bool = True,
) -> dict:
    """Persist a policy-refused turn (user msg + refusal reply) — NO model call.

    Never consumes quota/energy (no ``ai_usage_log`` row is written) and records
    a metadata-only ops/audit event with ``status="refused"``.
    """
    if persist_user:
        clean, _ = sanitize_instruction(user_text)
        user_msg = ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="user",
            content=clean or "[đã lọc nội dung]",
            seq=await next_seq(session, chat.id),
            created_at=datetime.now(UTC),
        )
        session.add(user_msg)
        if chat.title is None:
            chat.title = (clean or user_text)[:80]

    reply = _new_assistant_message(chat, refusal_text, await next_seq(session, chat.id))
    session.add(reply)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    await turn_telemetry.record_chat_turn(
        session,
        principal=principal,
        session_id=chat.id,
        alias=_chat_alias(),
        status="refused",
        latency_ms=0,
        iterations=0,
        tool_names=[],
        guard_flags=guard_flags,
    )
    return serialize_message(reply)


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


# --------------------------------------------------------------------------- #
# Partner native turn                                                          #
# --------------------------------------------------------------------------- #


async def _partner_history(session: AsyncSession, principal: Principal, chat, clean: str):
    """Build the LLM history for a partner turn (prior messages + context turn)."""
    history = await load_history(session, chat)
    user_context = await build_user_context(session, principal)
    history.append(
        AIMessage(
            role="user",
            content=partner_prompt_native.build_user_message(
                clean, context=user_context, persona=principal.persona
            ),
        )
    )
    return history


async def _partner_turn_kwargs(
    session: AsyncSession, principal: Principal, chat, clean: str, locale: str
) -> dict:
    """Assemble the native-loop kwargs for one partner turn.

    Deterministic multi-tier routing (``model_router``) picks the serving alias
    and the tool subset (fail-open to the full set); the persona scope guard and
    the allowance-exhausted copy plug the turn into the guardrail layers.
    """
    history = await _partner_history(session, principal, chat, clean)
    decision = model_router.route_turn(clean)
    specs = model_router.select_specs(native_loop.available_specs(principal), decision)

    def _scope_guard(text: str, used_tool: bool) -> str:
        return guardrails.partner_scope_guard(text, used_tool=used_tool, locale=locale)

    return {
        "history": history,
        "system_prompt": partner_prompt_native.PARTNER_SYSTEM_PROMPT_NATIVE,
        "specs": specs,
        "locale": locale,
        "model_alias": decision.model_alias,
        "escalate_alias": decision.escalate_alias,
        "text_guard": _scope_guard,
        "limit_reply": guardrails.limit_reached_reply(principal.persona, locale),
    }


async def _run_partner_turn(
    session: AsyncSession, *, principal: Principal, chat, clean: str, locale: str
) -> dict:
    """Run one partner turn via the native tool loop; return the final message."""
    kwargs = await _partner_turn_kwargs(session, principal, chat, clean, locale)
    final_message: dict | None = None
    async for ev in native_loop.run_native_turn(session, principal=principal, chat=chat, **kwargs):
        if ev.get("type") == "done":
            final_message = ev["message"]
    if final_message is not None:
        await update_session_memory(session, chat)
        return final_message
    # Defensive fallback — the generator always yields a terminal ``done``, but
    # never leave the caller without a persisted reply.
    assistant_msg = _new_assistant_message(
        chat, ai_unavailable_reply(locale), await next_seq(session, chat.id)
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()
    return serialize_message(assistant_msg)


async def _stream_partner_turn(
    session: AsyncSession, *, principal: Principal, chat, clean: str, locale: str
):
    """Stream one partner turn via the native tool loop (yields SSE event dicts)."""
    kwargs = await _partner_turn_kwargs(session, principal, chat, clean, locale)
    async for ev in native_loop.run_native_turn(session, principal=principal, chat=chat, **kwargs):
        if ev.get("type") == "done":
            await update_session_memory(session, chat)
        yield ev


# --------------------------------------------------------------------------- #
# Turn driver (shared by send_message and conversation management)             #
# --------------------------------------------------------------------------- #


async def run_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    chat,
    clean: str,
    locale: str = "vi",
    deferred_refusal: str | None = None,
) -> dict:
    """Answer one already-persisted user message and return the reply dict.

    ``clean`` must be the policy-cleaned user text and the user message must
    already be persisted on ``chat``. Used by ``send_message`` and by the
    edit/regenerate replay paths (``conversation_service``) so all of them run
    the exact same pipeline: fast-path → partner native loop → deterministic
    planner (with deferred external-source refusal fallback) → ReAct loop.
    """
    if quick_text := fast_path_reply(clean, locale, persona=principal.persona):
        assistant_msg = _new_assistant_message(chat, quick_text, await next_seq(session, chat.id))
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        return serialize_message(assistant_msg)

    # Partner recruiter assistant: native function-calling loop over a
    # persona+RBAC-filtered tool set (its own prompt/tools; bypasses the
    # student-centric deterministic planner entirely). Returns the terminal
    # message from the shared native turn generator.
    if _is_partner(principal):
        return await _run_partner_turn(
            session, principal=principal, chat=chat, clean=clean, locale=locale
        )

    agent_plan = await build_agent_plan(
        clean,
        principal=principal,
        session=session,
        chat=chat,
    )
    if deferred_refusal is not None and agent_plan is not None and agent_plan.action != "reply":
        # Policy flagged an external-source ask but the planner misread it as an
        # internal tool action (e.g. a job search for a "fetch this URL" ask) —
        # answering with internal data would be misleading. Only a deterministic
        # boundary REPLY may override the refusal.
        agent_plan = None
    if agent_plan:
        if agent_plan_requires_confirmation(agent_plan):
            confirm_msg = create_confirmation_message(chat, agent_plan)
            confirm_msg.seq = await next_seq(session, chat.id)
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
        assistant_msg = _new_assistant_message(chat, agent_text, await next_seq(session, chat.id))
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        await update_session_memory(session, chat)
        return serialize_message(assistant_msg)

    if deferred_refusal is not None:
        # Policy flagged an external-source ask the planner did not catch —
        # deterministic refusal; the model is never called for this intent.
        return await _persist_turn_refusal(
            session,
            principal=principal,
            chat=chat,
            user_text=clean,
            refusal_text=deferred_refusal,
            guard_flags=["external_source_request"],
            persist_user=False,
        )

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
    used_model = False
    turn_status = "ok"
    tool_names: list[str] = []
    final_text: str | None = None
    kb_sources: list[str] = []  # §6.5: retrieved doc titles for this turn's citation check
    t0 = time.monotonic()

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
            used_model = True
        except AIUnavailableError:
            final_text = ai_unavailable_reply()
            turn_status = "error"
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
                seq=await next_seq(session, chat.id),
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
        tool_names.append(tool_name)
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
    assistant_msg = _new_assistant_message(chat, final_text, await next_seq(session, chat.id))
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    await _finalize_llm_turn(
        session,
        principal=principal,
        chat=chat,
        assistant_msg_id=assistant_msg.id,
        status=turn_status,
        latency_ms=int((time.monotonic() - t0) * 1000),
        iterations=iterations,
        tool_names=tool_names,
        used_model=used_model and turn_status == "ok",
    )
    return serialize_message(assistant_msg)


async def _finalize_llm_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    chat,
    assistant_msg_id: uuid.UUID,
    status: str,
    latency_ms: int,
    iterations: int,
    tool_names: list[str],
    used_model: bool,
) -> None:
    """Post-turn upkeep for the generic LLM loop: telemetry, energy, memory."""
    from app.ai.gateway.factory import real_provider_active

    await turn_telemetry.record_chat_turn(
        session,
        principal=principal,
        session_id=chat.id,
        alias=_chat_alias(),
        status=status,
        latency_ms=latency_ms,
        iterations=iterations,
        tool_names=tool_names,
        guard_flags=[],
    )
    if used_model and real_provider_active():
        await turn_telemetry.record_turn_billable(
            session,
            principal=principal,
            assistant_message_id=assistant_msg_id,
            session_id=chat.id,
        )
    await update_session_memory(session, chat)


# --------------------------------------------------------------------------- #
# Public entry points                                                          #
# --------------------------------------------------------------------------- #


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

    # Central safety policy (intent → PII redaction/injection strip → action)
    # BEFORE fast-path/planner/native loop. Refusals never reach a model.
    text = text.strip()[:_MAX_USER_MSG_LEN]
    pre = guardrails.preflight_policy(text, persona=principal.persona, locale=locale)
    if pre.refused:
        return await _persist_turn_refusal(
            session,
            principal=principal,
            chat=chat,
            user_text=text,
            refusal_text=pre.refusal_text or "",
            guard_flags=list(pre.flags),
        )

    clean = pre.clean_text
    if not clean:
        reply = await quick_reply(
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
        seq=await next_seq(session, chat.id),
        created_at=datetime.now(UTC),
    )
    session.add(user_msg)

    # Update session title from first user message (deterministic fallback; a
    # concise cheap-model title replaces it after the first exchange completes).
    was_first_exchange = chat.title is None
    if was_first_exchange:
        chat.title = clean[:80]

    reply = await run_turn(
        session,
        principal=principal,
        chat=chat,
        clean=clean,
        locale=locale,
        deferred_refusal=pre.deferred_refusal_text,
    )
    if was_first_exchange:
        await refresh_session_title(session, chat, clean)
    return reply


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
    locale = "vi"
    if not principal.is_authenticated:
        yield {"type": "error", "code": "auth_required"}
        return

    try:
        await usage_service.enforce_quota(session, principal=principal)
    except QuotaExceededError:
        yield {
            "type": "error",
            "code": "quota_exceeded",
            "message": guardrails.limit_reached_reply(principal.persona, locale),
        }
        return

    try:
        chat = await require_session(session, principal, session_id)
    except Exception:
        yield {"type": "error", "code": "session_not_found"}
        return

    # Central safety policy BEFORE fast-path/planner/native loop (see send_message).
    clean_text = text.strip()[:_MAX_USER_MSG_LEN]
    pre = guardrails.preflight_policy(clean_text, persona=principal.persona, locale=locale)
    if pre.refused:
        refusal = await _persist_turn_refusal(
            session,
            principal=principal,
            chat=chat,
            user_text=clean_text,
            refusal_text=pre.refusal_text or "",
            guard_flags=list(pre.flags),
        )
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(refusal["content"]):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": refusal}
        return

    clean = pre.clean_text
    if not clean:
        yield {"type": "error", "code": "invalid_message"}
        return

    # Persist user message
    user_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="user",
        content=clean,
        seq=await next_seq(session, chat.id),
        created_at=datetime.now(UTC),
    )
    session.add(user_msg)
    was_first_exchange = chat.title is None
    if was_first_exchange:
        chat.title = clean[:80]

    yield {"type": "status", "code": "received"}

    if quick_text := fast_path_reply(clean, persona=principal.persona):
        assistant_msg = _new_assistant_message(chat, quick_text, await next_seq(session, chat.id))
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(quick_text):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": serialize_message(assistant_msg)}
        return

    # Partner recruiter assistant: native function-calling loop (own prompt +
    # persona/RBAC-filtered tools). Streams the same SSE event vocabulary.
    if _is_partner(principal):
        async for ev in _stream_partner_turn(
            session, principal=principal, chat=chat, clean=clean, locale=locale
        ):
            yield ev
        if was_first_exchange:
            await refresh_session_title(session, chat, clean)
        return

    agent_plan = await build_agent_plan(
        clean,
        principal=principal,
        session=session,
        chat=chat,
    )
    if (
        pre.deferred_refusal_text is not None
        and agent_plan is not None
        and agent_plan.action != "reply"
    ):
        # See run_turn: only a deterministic boundary REPLY may override a
        # policy-flagged external-source ask.
        agent_plan = None
    if agent_plan:
        if agent_plan_requires_confirmation(agent_plan):
            yield {"type": "status", "code": "confirming_action"}
            confirm_msg = create_confirmation_message(chat, agent_plan)
            confirm_msg.seq = await next_seq(session, chat.id)
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
        assistant_msg = _new_assistant_message(chat, agent_text, await next_seq(session, chat.id))
        session.add(assistant_msg)
        chat.last_message_at = datetime.now(UTC)
        await session.commit()
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(agent_text):
            yield {"type": "token", "text": chunk}
        await update_session_memory(session, chat)
        if was_first_exchange:
            await refresh_session_title(session, chat, clean)
        yield {"type": "done", "message": serialize_message(assistant_msg)}
        return

    if pre.deferred_refusal_text is not None:
        # Policy flagged an external-source ask the planner did not catch —
        # deterministic refusal; the model is never called for this intent.
        refusal = await _persist_turn_refusal(
            session,
            principal=principal,
            chat=chat,
            user_text=clean,
            refusal_text=pre.deferred_refusal_text,
            guard_flags=["external_source_request"],
            persist_user=False,
        )
        yield {"type": "status", "code": "responding"}
        for chunk in local_stream_chunks(refusal["content"]):
            yield {"type": "token", "text": chunk}
        yield {"type": "done", "message": refusal}
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
    used_model = False
    turn_status = "ok"
    tool_names: list[str] = []
    final_text: str | None = None
    final_text_streamed = False
    kb_sources: list[str] = []  # §6.5: retrieved doc titles for this turn's citation check
    t0 = time.monotonic()

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
            used_model = True
        except AIUnavailableError:
            final_text = ai_unavailable_reply()
            final_text_streamed = False
            turn_status = "error"
            break

        if not raw_response:
            final_text = ai_unavailable_reply()
            final_text_streamed = False
            turn_status = "error"
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
                seq=await next_seq(session, chat.id),
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
        tool_names.append(tool_name)
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
    assistant_msg = _new_assistant_message(chat, final_text, await next_seq(session, chat.id))
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    await _finalize_llm_turn(
        session,
        principal=principal,
        chat=chat,
        assistant_msg_id=assistant_msg.id,
        status=turn_status,
        latency_ms=int((time.monotonic() - t0) * 1000),
        iterations=iterations,
        tool_names=tool_names,
        used_model=used_model and turn_status == "ok",
    )
    if was_first_exchange:
        await refresh_session_title(session, chat, clean)

    yield {"type": "done", "message": serialize_message(assistant_msg)}
