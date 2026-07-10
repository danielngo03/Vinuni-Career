"""Native function-calling tool loop (OpenAI-compatible ``tools=`` interface).

The legacy path (``tool_loop`` + ``chat_service``) emulates tool calls by asking
the model to emit a ``{"tool_call": ...}`` JSON blob in its own text. That is
fragile — it only fires when a real provider echoes the exact JSON — and it
advertises the whole tool list in the prompt regardless of the caller's
permissions.

This module runs the modern loop instead: it hands the provider a persona- and
RBAC-filtered ``tools`` array and executes the ``tool_calls`` the model returns.
Two invariants:

1. RBAC first (:func:`authorize_tool`): the model only *sees* tools whose
   ``ToolSpec.required_permissions`` the caller satisfies, decided by the same
   service-layer ``permission_checker`` the REST API uses. Dispatch re-checks
   before executing (defense in depth). A partner admin who revokes a member's
   ``applications:read`` grant therefore removes candidate tools from that
   member's assistant entirely — the chatbot can never exceed the human's reach.
2. Human-in-the-loop writes: ``confirmation_required`` tools are NEVER executed
   inline. The loop persists a pending ``tool_call`` message (the frontend's
   confirmation card) and stops; execution happens only via the existing
   ``confirm_tool_action`` path after the user clicks confirm.

:func:`run_native_turn` is an async generator of SSE-style event dicts (the same
vocabulary as ``chat_service.stream_message``) ending in a ``done`` event; the
non-streaming ``send_message`` consumes it and returns the terminal message.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AICompletion, AIMessage
from app.ai.safety.input_guard import neutralize_tool_payload
from app.modules.ai_assistant.application import guardrails, model_router, turn_telemetry
from app.modules.ai_assistant.application.messages import assistant_message
from app.modules.ai_assistant.application.response_formatter import (
    ai_unavailable_reply,
    local_stream_chunks,
)
from app.modules.ai_assistant.application.session_history import next_seq, serialize_message
from app.modules.ai_assistant.application.tool_loop import (
    MAX_ITERATIONS,
    MAX_TOOL_CALLS_PER_TURN,
    persist_tool_result,
)
from app.modules.ai_assistant.application.tool_registry import TOOL_SPECS, dispatch_tool
from app.modules.ai_assistant.application.tools.specs import (
    PARTNER_USER,
    STUDENT,
    UNIVERSITY_STAFF,
    ToolSpec,
)
from app.modules.ai_assistant.domain.models import ChatMessage
from app.shared.exceptions import AIUnavailableError, PaymentRequiredError, QuotaExceededError
from app.shared.permissions import Principal, permission_checker

_TASK_TYPE = "ai_assistant_chat"

# Cap the JSON blob we feed a tool result back to the model with, so a large
# result set can't blow the context / cost budget.
_MAX_TOOL_RESULT_CHARS = 6000


# --------------------------------------------------------------------------- #
# Persona + RBAC gate                                                          #
# --------------------------------------------------------------------------- #


def _persona_token(principal: Principal) -> str | None:
    """Map the real login persona to a ``ToolSpec.persona`` vocabulary token.

    Returns ``None`` for an unrecognised persona (then persona filtering is a
    no-op and only ``authorize_tool`` gates the tool).
    """
    persona = principal.persona or ""
    if persona == "student":
        return STUDENT
    if persona.startswith("partner"):
        return PARTNER_USER
    if persona.startswith("university"):
        return UNIVERSITY_STAFF
    return None


def _persona_matches_role(principal: Principal, want: str) -> bool:
    persona = principal.persona or ""
    if want == "student":
        return persona == "student"
    if want in ("partner_user", "partner", "partner_member"):
        return persona.startswith("partner")
    if want in ("university_staff", "university"):
        return persona.startswith("university")
    return persona == want


def authorize_tool(principal: Principal, spec: ToolSpec) -> bool:
    """Central RBAC gate — True iff ``principal`` may invoke ``spec``.

    Interprets each ``ToolSpec.required_permissions`` entry:
    - ``"authenticated"``          → the principal has a user id.
    - ``"role:<persona>"``         → persona-family match (student/partner/university).
    - ``"<resource>:<action>"``    → ``permission_checker.can`` (real grant + tenant).
    All entries must pass (fail-closed).
    """
    for req in spec.required_permissions:
        if req == "authenticated":
            if not principal.is_authenticated:
                return False
        elif req.startswith("role:"):
            if not _persona_matches_role(principal, req.split(":", 1)[1]):
                return False
        elif ":" in req:
            resource, action = req.split(":", 1)
            if not permission_checker.can(
                principal, resource, action, resource_org_id=principal.org_id
            ):
                return False
        else:  # unknown token — require at least authentication
            if not principal.is_authenticated:
                return False
    return True


def available_specs(principal: Principal) -> list[ToolSpec]:
    """Tools this principal may use: persona-scoped AND grant-authorized."""
    token = _persona_token(principal)
    out: list[ToolSpec] = []
    for spec in TOOL_SPECS.values():
        if token is not None and token not in spec.persona:
            continue
        if not authorize_tool(principal, spec):
            continue
        out.append(spec)
    return out


def specs_to_openai_tools(specs: list[ToolSpec]) -> list[dict]:
    """Render ToolSpecs as the OpenAI-compatible ``tools`` array."""
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.parameters or {"type": "object", "properties": {}},
            },
        }
        for s in specs
    ]


# --------------------------------------------------------------------------- #
# LLM call (native tools, cost-tracked)                                        #
# --------------------------------------------------------------------------- #


async def llm_complete_native(
    history: list[AIMessage],
    *,
    system_prompt: str,
    tools: list[dict],
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    alias: str | None = None,
) -> AICompletion:
    """Call the chat model with the native ``tools`` interface.

    Mirrors ``tool_loop.llm_complete``'s cost tracking + budget guard + output
    guard, but returns the full :class:`AICompletion` (text AND ``tool_calls``).
    ``alias`` overrides the configured chat alias (multi-tier routing — never
    exposed to callers/users). Degrades to the offline provider when real calls
    are disabled (returns a plain text answer with no tool_calls).
    """
    from app.ai.gateway import runtime_config
    from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
    from app.ai.gateway.offline import OfflineProvider
    from app.ai.gateway.output_guard import guard_completion
    from app.ai.observability.cost_estimator import estimate_cost_usd
    from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
    from app.modules.ai_settings.application.budget_guard import check_async

    alias = alias or runtime_config.current().chat_model_alias
    messages = [AIMessage(role="system", content=system_prompt)] + history

    if real_provider_active():
        try:
            provider = get_provider_for_alias(alias)
        except Exception:
            provider = OfflineProvider()
    else:
        provider = OfflineProvider()

    prompt_chars = sum(len(m.content) for m in messages)
    estimated_cost = estimate_cost_usd(alias, prompt_chars=prompt_chars, completion_chars=256)
    if db is not None and real_provider_active():
        await check_async(db, alias=alias, estimated_cost_usd=estimated_cost, user_id=user_id)

    try:
        completion = await provider.complete(
            messages,
            alias=alias,
            temperature=0.3,
            max_tokens=900,
            tools=tools,
            tool_choice="auto",
        )
    except Exception as exc:
        if db is not None:
            await log_ai_usage_async(
                db,
                task_type=_TASK_TYPE,
                alias=alias,
                success=False,
                user_id=user_id,
                session_id=session_id,
            )
        else:
            log_ai_usage(task_type=_TASK_TYPE, alias=alias, success=False)
        raise AIUnavailableError() from exc

    guarded_text = guard_completion(completion)
    completion_chars = len(guarded_text)
    cost_usd = estimate_cost_usd(
        alias, prompt_chars=prompt_chars, completion_chars=completion_chars
    )
    if db is not None:
        await log_ai_usage_async(
            db,
            task_type=_TASK_TYPE,
            alias=alias,
            success=True,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
            user_id=user_id,
            session_id=session_id,
            cost_usd=cost_usd,
        )
    else:
        log_ai_usage(
            task_type=_TASK_TYPE,
            alias=alias,
            success=True,
            prompt_chars=prompt_chars,
            completion_chars=completion_chars,
        )
    return AICompletion(
        text=guarded_text,
        model_alias=completion.model_alias,
        usage=completion.usage,
        finish_reason=completion.finish_reason,
        tool_calls=completion.tool_calls,
    )


# --------------------------------------------------------------------------- #
# Turn driver                                                                  #
# --------------------------------------------------------------------------- #


def _default_chat_alias() -> str:
    from app.ai.gateway import runtime_config

    return runtime_config.current().chat_model_alias


def _tool_result_message(
    call_id: str, name: str, result: dict, *, flags: list[str] | None = None
) -> AIMessage:
    """Serialise a tool result back into model context.

    Tool output is UNTRUSTED DATA (a candidate CV, an uploaded attachment, a
    knowledge-base chunk can smuggle injected instructions). Neutralise
    injection markers in every string value before the model sees it; record an
    ``untrusted_data_neutralized`` guard flag (metadata only) when anything was
    defused. Defense in depth with the system-prompt untrusted-data rule and the
    RBAC/confirmation gates.
    """
    scrubbed, neutralized = neutralize_tool_payload(result)
    if neutralized and flags is not None:
        flags.append("untrusted_data_neutralized")
    payload = json.dumps(scrubbed, ensure_ascii=False)[:_MAX_TOOL_RESULT_CHARS]
    return AIMessage(role="tool", content=payload, tool_call_id=call_id, name=name)


def _confirmation_message(
    chat_id: uuid.UUID, spec: ToolSpec, name: str, args: dict, locale: str, seq: int | None = None
) -> ChatMessage:
    copy = spec.confirmation_copy
    if copy:
        content = f"{copy.title}\n{copy.body}"
    else:
        content = assistant_message("chat.preparing_tool", locale, tool_name=name)
    return ChatMessage(
        id=uuid.uuid4(),
        session_id=chat_id,
        role="tool_call",
        content=content,
        tool_name=name,
        tool_args=args,
        requires_confirmation=True,
        seq=seq,
        created_at=datetime.now(UTC),
    )


async def run_native_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    chat,
    history: list[AIMessage],
    system_prompt: str,
    specs: list[ToolSpec],
    locale: str = "vi",
    model_alias: str | None = None,
    escalate_alias: str | None = None,
    text_guard: Callable[[str, bool], str] | None = None,
    limit_reply: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Drive one assistant turn with native tool-calling.

    ``history`` must already end with the current user message (with any context
    injection). Yields SSE event dicts and ends with a ``done`` event carrying
    either the final assistant message or a pending confirmation card.

    Multi-tier routing: ``model_alias`` selects the serving alias for this turn
    (internal only); when the chosen tier fails or returns an empty completion
    and ``escalate_alias`` is set, the loop retries ONCE on that alias.
    ``text_guard(text, used_tool)`` is applied to a model-produced final answer
    (persona scope guard); ``limit_reply`` is the persona-appropriate user-safe
    message for budget/allowance exhaustion mid-turn.
    """
    from app.ai.gateway.factory import real_provider_active
    from app.ai.observability.cost_estimator import estimate_cost_usd

    openai_tools = specs_to_openai_tools(specs)
    allowed = {s.name: s for s in specs}
    alias = model_alias or _default_chat_alias()
    escalated = False
    iterations = 0
    tool_calls_used = 0
    final_text: str | None = None
    final_from_model = False
    turn_status = "ok"
    turn_cost_usd = 0.0
    tool_names: list[str] = []
    guard_flags: list[str] = []
    t0 = time.monotonic()
    # Render-worthy artifacts (download buttons, charts, ...) surfaced from tool
    # results to the FE via the final assistant message — NOT fed to the model.
    artifacts: list[dict] = []

    # Leak-safe phase timeline (frozen vocabulary in ``model_router``): every
    # turn opens with "understanding" (before the first model call); each tool
    # dispatch emits its mapped work phase; the final text is preceded by
    # "composing". A ``status`` event NEVER carries a tool name — the separate
    # ``tool_call`` event still does, for internal/eval use only, and the FE
    # renders phases exclusively so the tool identity never reaches the client.
    yield {"type": "status", "code": model_router.PHASE_UNDERSTANDING}

    while iterations < MAX_ITERATIONS:
        iterations += 1
        try:
            completion = await llm_complete_native(
                history,
                system_prompt=system_prompt,
                tools=openai_tools,
                db=session,
                user_id=principal.user_id,
                session_id=chat.id,
                alias=alias,
            )
        except (PaymentRequiredError, QuotaExceededError):
            # Budget/allowance exhausted mid-turn — persona-appropriate copy,
            # no charge, turn marked blocked.
            final_text = limit_reply or ai_unavailable_reply(locale)
            turn_status = "blocked"
            guard_flags.append("budget_blocked")
            break
        except AIUnavailableError:
            if escalate_alias and not escalated:
                escalated = True
                alias = escalate_alias
                guard_flags.append("escalated")
                iterations -= 1  # the failed call does not consume an iteration
                continue
            final_text = ai_unavailable_reply(locale)
            turn_status = "error"
            break

        turn_cost_usd += estimate_cost_usd(
            alias,
            prompt_chars=sum(len(m.content or "") for m in history),
            completion_chars=len(completion.text or ""),
        )

        calls = completion.tool_calls
        if not calls:
            text = (completion.text or "").strip()
            if not text and escalate_alias and not escalated:
                # Empty completion — one escalation retry on the stronger tier.
                escalated = True
                alias = escalate_alias
                guard_flags.append("escalated")
                iterations -= 1
                continue
            if text:
                final_text = text
                final_from_model = True
            else:
                final_text = ai_unavailable_reply(locale)
                turn_status = "error"
            break

        # Echo the assistant's tool-call turn back into history so the next hop
        # (and the OpenAI protocol) has the matching context for the results.
        history.append(AIMessage(role="assistant", content=completion.text or "", tool_calls=calls))

        for call in calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            call_id = call.get("id") or name or str(uuid.uuid4())
            try:
                parsed = json.loads(fn.get("arguments") or "{}")
                args = parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                args = {}

            spec = allowed.get(name)
            if spec is None:
                # Model asked for a tool it cannot see — keep protocol valid.
                history.append(
                    _tool_result_message(call_id, name, {"ok": False, "error": "tool_unavailable"})
                )
                yield {"type": "tool_result", "name": name, "ok": False}
                continue

            # Defense in depth: re-check the grant even though `specs` was filtered.
            if not authorize_tool(principal, spec):
                history.append(
                    _tool_result_message(call_id, name, {"ok": False, "error": "permission_denied"})
                )
                yield {"type": "tool_result", "name": name, "ok": False}
                continue

            if spec.permission_class == "confirmation_required":
                # Sensible terminal phase for the confirmation-card path (e.g.
                # create_job / move_candidate_stage → "analyzing") — the card is
                # then streamed as the terminal ``done`` event, no final text.
                yield {"type": "status", "code": model_router.phase_for_tool(name)}
                confirm_msg = _confirmation_message(
                    chat.id, spec, name, args, locale, seq=await next_seq(session, chat.id)
                )
                if artifacts:
                    # Artifacts collected from read-only tools earlier in this
                    # turn (e.g. the job_draft preview that preceded a
                    # create_job proposal) must survive the pending-confirmation
                    # early return — attach them to the confirmation card.
                    confirm_msg.tool_result = {"artifacts": artifacts}
                session.add(confirm_msg)
                chat.last_message_at = datetime.now(UTC)
                await session.commit()
                guard_flags.append("confirmation_pending")
                await turn_telemetry.record_chat_turn(
                    session,
                    principal=principal,
                    session_id=chat.id,
                    alias=alias,
                    status="ok",
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    iterations=iterations,
                    tool_names=[*tool_names, name],
                    guard_flags=guard_flags,
                )
                if real_provider_active():
                    # Real tokens produced this user-visible confirmation card.
                    await turn_telemetry.record_turn_billable(
                        session,
                        principal=principal,
                        assistant_message_id=confirm_msg.id,
                        session_id=chat.id,
                        provider_cost_usd=turn_cost_usd or None,
                    )
                yield {"type": "done", "message": serialize_message(confirm_msg)}
                return

            if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                history.append(
                    _tool_result_message(
                        call_id, name, {"ok": False, "error": "tool_limit_reached"}
                    )
                )
                continue

            # Read-only tool — dispatch inline. Emit the leak-safe work phase
            # FIRST (the only signal the FE renders); the ``tool_call`` event
            # below still carries the raw name for internal/eval consumers only.
            yield {"type": "status", "code": model_router.phase_for_tool(name)}
            yield {"type": "tool_call", "name": name}
            result = await dispatch_tool(name, args, session=session, principal=principal)
            tool_calls_used += 1
            tool_names.append(name)
            # A ``render`` block is a FE-only artifact (download/chart). Pull it
            # out so it reaches the client but not the model's context/cost.
            render = result.pop("render", None) if isinstance(result, dict) else None
            if isinstance(render, dict):
                artifacts.append(render)
            yield {"type": "tool_result", "name": name, "ok": bool(result.get("ok"))}
            persist_tool_result(session, chat=chat, tool_name=name, tool_args=args, result=result)
            # Untrusted-data injection defense: tool output (CV text, attachment
            # extraction, KB chunks) is neutralised before re-entering context.
            history.append(_tool_result_message(call_id, name, result, flags=guard_flags))
        # Loop: model now sees the tool results and either answers or calls more.

    if final_text is None:
        final_text = ai_unavailable_reply(locale)
        turn_status = "error" if turn_status == "ok" else turn_status

    # A model that imitates the stored tool-dump format produces an unusable
    # answer ("[Tool result: X] {json…}") — swap in a localized generic
    # completion; any collected artifacts still render below it.
    if final_from_model and final_text.lstrip().startswith("[Tool result"):
        guard_flags.append("tool_dump_scrubbed")
        final_text = guardrails.tool_data_reply(locale)
        final_from_model = False

    # Post-LLM deterministic scope guard on a model-produced pure-text answer
    # (a tool-grounded answer is trusted by construction — skip flag inside).
    if text_guard is not None and final_from_model:
        guarded = text_guard(final_text, tool_calls_used > 0)
        if guarded != final_text:
            guard_flags.append("scope_refused")
            final_text = guarded

    # Ungrounded-number telemetry flag (partner turns only): a model-produced
    # pure-text answer that used NO tool this turn yet asserts a specific count /
    # percentage / salary / metric has no source for that number. Flag it for
    # eval/telemetry ONLY — the user-facing text is never altered (a false
    # positive must never scrub a legitimate answer). Conservative by design:
    # ``has_ungrounded_numeric_claim`` ignores years, dates, and list ordinals.
    if (
        final_from_model
        and tool_calls_used == 0
        and (principal.persona or "").startswith("partner")
        and guardrails.has_ungrounded_numeric_claim(final_text)
    ):
        guard_flags.append("ungrounded_numeric_suspected")

    yield {"type": "status", "code": model_router.PHASE_COMPOSING}
    for chunk in local_stream_chunks(final_text):
        yield {"type": "token", "text": chunk}

    assistant_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=final_text,
        # Attach render artifacts (downloads/charts) for the FE. Reuses the
        # existing tool_result JSON column; serialize_message forwards it.
        tool_result={"artifacts": artifacts} if artifacts else None,
        seq=await next_seq(session, chat.id),
        created_at=datetime.now(UTC),
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    # Per-turn observability (metadata only) + idempotent energy accounting.
    await turn_telemetry.record_chat_turn(
        session,
        principal=principal,
        session_id=chat.id,
        alias=alias,
        status=turn_status,
        latency_ms=int((time.monotonic() - t0) * 1000),
        iterations=iterations,
        tool_names=tool_names,
        guard_flags=guard_flags,
    )
    if turn_status == "ok" and final_from_model and real_provider_active():
        await turn_telemetry.record_turn_billable(
            session,
            principal=principal,
            assistant_message_id=assistant_msg.id,
            session_id=chat.id,
            provider_cost_usd=turn_cost_usd or None,
        )

    yield {"type": "done", "message": serialize_message(assistant_msg)}
