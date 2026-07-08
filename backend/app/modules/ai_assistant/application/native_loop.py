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
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AICompletion, AIMessage
from app.modules.ai_assistant.application.messages import assistant_message
from app.modules.ai_assistant.application.response_formatter import (
    ai_unavailable_reply,
    local_stream_chunks,
)
from app.modules.ai_assistant.application.session_history import serialize_message
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
from app.shared.exceptions import AIUnavailableError
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
) -> AICompletion:
    """Call the chat model with the native ``tools`` interface.

    Mirrors ``tool_loop.llm_complete``'s cost tracking + budget guard + output
    guard, but returns the full :class:`AICompletion` (text AND ``tool_calls``).
    Degrades to the offline provider when real calls are disabled (returns a
    plain text answer with no tool_calls).
    """
    from app.ai.gateway import runtime_config
    from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
    from app.ai.gateway.offline import OfflineProvider
    from app.ai.gateway.output_guard import guard_completion
    from app.ai.observability.cost_estimator import estimate_cost_usd
    from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
    from app.modules.ai_settings.application.budget_guard import check_async

    alias = runtime_config.current().chat_model_alias
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


def _tool_result_message(call_id: str, name: str, result: dict) -> AIMessage:
    payload = json.dumps(result, ensure_ascii=False)[:_MAX_TOOL_RESULT_CHARS]
    return AIMessage(role="tool", content=payload, tool_call_id=call_id, name=name)


def _confirmation_message(
    chat_id: uuid.UUID, spec: ToolSpec, name: str, args: dict, locale: str
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
) -> AsyncGenerator[dict, None]:
    """Drive one assistant turn with native tool-calling.

    ``history`` must already end with the current user message (with any context
    injection). Yields SSE event dicts and ends with a ``done`` event carrying
    either the final assistant message or a pending confirmation card.
    """
    openai_tools = specs_to_openai_tools(specs)
    allowed = {s.name: s for s in specs}
    iterations = 0
    tool_calls_used = 0
    final_text: str | None = None
    # Render-worthy artifacts (download buttons, charts, ...) surfaced from tool
    # results to the FE via the final assistant message — NOT fed to the model.
    artifacts: list[dict] = []

    while iterations < MAX_ITERATIONS:
        iterations += 1
        yield {"type": "status", "code": "thinking" if iterations == 1 else "synthesizing"}
        try:
            completion = await llm_complete_native(
                history,
                system_prompt=system_prompt,
                tools=openai_tools,
                db=session,
                user_id=principal.user_id,
                session_id=chat.id,
            )
        except AIUnavailableError:
            final_text = ai_unavailable_reply(locale)
            break

        calls = completion.tool_calls
        if not calls:
            final_text = completion.text.strip() or ai_unavailable_reply(locale)
            break

        # Echo the assistant's tool-call turn back into history so the next hop
        # (and the OpenAI protocol) has the matching context for the results.
        history.append(
            AIMessage(role="assistant", content=completion.text or "", tool_calls=calls)
        )

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
                confirm_msg = _confirmation_message(chat.id, spec, name, args, locale)
                session.add(confirm_msg)
                chat.last_message_at = datetime.now(UTC)
                await session.commit()
                yield {"type": "done", "message": serialize_message(confirm_msg)}
                return

            if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                history.append(
                    _tool_result_message(
                        call_id, name, {"ok": False, "error": "tool_limit_reached"}
                    )
                )
                continue

            # Read-only tool — dispatch inline.
            yield {"type": "tool_call", "name": name}
            result = await dispatch_tool(name, args, session=session, principal=principal)
            tool_calls_used += 1
            # A ``render`` block is a FE-only artifact (download/chart). Pull it
            # out so it reaches the client but not the model's context/cost.
            render = result.pop("render", None) if isinstance(result, dict) else None
            if isinstance(render, dict):
                artifacts.append(render)
            yield {"type": "tool_result", "name": name, "ok": bool(result.get("ok"))}
            persist_tool_result(
                session, chat=chat, tool_name=name, tool_args=args, result=result
            )
            history.append(_tool_result_message(call_id, name, result))
        # Loop: model now sees the tool results and either answers or calls more.

    if final_text is None:
        final_text = ai_unavailable_reply(locale)

    yield {"type": "status", "code": "responding"}
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
        created_at=datetime.now(UTC),
    )
    session.add(assistant_msg)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()
    yield {"type": "done", "message": serialize_message(assistant_msg)}
