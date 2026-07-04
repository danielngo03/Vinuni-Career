"""AI assistant ReAct tool-calling loop primitives.

Owns: the LLM completion/streaming calls (with cost tracking + budget guard),
tool-call JSON parsing/normalization, persisting tool results as hidden
conversation memory, executing a deterministic domain-agent plan, and the
post-confirmation tool execution path. ``chat_service.send_message`` /
``stream_message`` compose these primitives into the per-turn control flow.
Extracted from the former monolithic ``chat_service.py``.

Tool dispatch rules (AI_PRODUCT_SPEC.md §4):
- read_only tools: dispatched immediately, result injected as assistant context.
- confirmation_required tools: NOT dispatched here — the caller must return a
  pending tool_call message that the frontend displays as a confirmation card.
  The user must call ``confirm_tool_action`` with the message_id to execute.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.prompts.assistant import v1 as assistant_prompt
from app.modules.ai_assistant.application.agents import AgentPlan, format_tool_result
from app.modules.ai_assistant.application.session_history import (
    require_session,
    serialize_message,
)
from app.modules.ai_assistant.application.tool_registry import TOOL_SPECS, dispatch_tool
from app.modules.ai_assistant.domain.models import ChatMessage, ChatSession
from app.shared.exceptions import AIUnavailableError, AuthRequiredError, ResourceNotFoundError
from app.shared.permissions import Principal

_TASK_TYPE = "ai_assistant_chat"

# ReAct loop bounds (AI_PRODUCT_SPEC.md §4.1): MAX_ITERATIONS caps LLM turns
# within one user message; MAX_TOOL_CALLS_PER_TURN caps tool dispatches within
# one user message. The current loop dispatches at most one tool per
# iteration, so the second cap can never bind today, but both are named and
# enforced explicitly so a future multi-tool-call-per-iteration change stays
# spec-compliant without another audit.
MAX_ITERATIONS = 8
MAX_TOOL_CALLS_PER_TURN = 12


# --------------------------------------------------------------------------- #
# Tool-call parsing                                                           #
# --------------------------------------------------------------------------- #


def parse_tool_call(raw: str) -> dict[str, Any] | None:
    """If the LLM output is a tool_call JSON, parse and return it. Else None."""
    raw = raw.strip()
    # Look for {"tool_call": {"name": ..., "args": ...}}
    try:
        if "{" in raw and "tool_call" in raw:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end > start:
                obj = json.loads(raw[start : end + 1])
                tc = obj.get("tool_call")
                if isinstance(tc, dict) and "name" in tc:
                    return _normalize_tool_call(tc)
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _normalize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Normalize common model arg variants to the declared tool schema."""
    name = str(tool_call.get("name") or "")
    raw_args = tool_call.get("args")
    args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
    if name in {"get_salary_benchmark", "get_career_advice"}:
        if not args.get("role"):
            args["role"] = (
                args.get("job_title")
                or args.get("title")
                or args.get("occupation")
                or args.get("position")
                or ""
            )
    return {"name": name, "args": args}


# --------------------------------------------------------------------------- #
# Tool execution + persistence                                               #
# --------------------------------------------------------------------------- #


def persist_tool_result(
    session: AsyncSession,
    *,
    chat: ChatSession,
    tool_name: str,
    tool_args: dict,
    result: dict,
) -> None:
    """Persist read-only tool results as hidden conversation memory."""
    tool_context = assistant_prompt.build_tool_result_message(tool_name, result)
    session.add(
        ChatMessage(
            id=uuid.uuid4(),
            session_id=chat.id,
            role="tool_result",
            content=tool_context,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=result,
            created_at=datetime.now(UTC),
        )
    )


def agent_plan_requires_confirmation(plan: AgentPlan) -> bool:
    if plan.action != "tool" or not plan.tool_name:
        return False
    spec = TOOL_SPECS.get(plan.tool_name)
    return bool(spec and spec.permission_class == "confirmation_required")


def create_confirmation_message(chat: ChatSession, plan: AgentPlan) -> ChatMessage:
    tool_name = plan.tool_name or ""
    spec = TOOL_SPECS.get(tool_name)
    copy = spec.confirmation_copy if spec else None
    if copy:
        content = f"{copy.title}\n{copy.body}"
        if plan.reason:
            content = f"{content}\n\n{plan.reason}"
    else:
        reason = f": {plan.reason}" if plan.reason else ""
        content = f"Đang chờ xác nhận để thực hiện {tool_name}{reason}"
    return ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="tool_call",
        content=content,
        tool_name=tool_name,
        tool_args=plan.tool_args or {},
        requires_confirmation=True,
        created_at=datetime.now(UTC),
    )


async def execute_agent_plan(
    plan: AgentPlan,
    *,
    chat: ChatSession,
    session: AsyncSession,
    principal: Principal,
    ai_unavailable_reply: str,
) -> str:
    """Execute a deterministic domain-agent plan and return user-facing text."""
    if plan.action == "reply":
        return plan.reply or ai_unavailable_reply

    if not plan.tool_name:
        return ai_unavailable_reply

    tool_args = plan.tool_args or {}
    result = await dispatch_tool(plan.tool_name, tool_args, session=session, principal=principal)
    persist_tool_result(
        session,
        chat=chat,
        tool_name=plan.tool_name,
        tool_args=tool_args,
        result=result,
    )
    return format_tool_result(plan, result)


async def confirm_tool_action(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
) -> dict:
    """Execute a ``confirmation_required`` tool after the user confirms.

    Looks up the pending tool_call message, validates ownership, executes the
    tool via ``dispatch_tool``, persists the result, and marks the message
    confirmed. Idempotent: if already confirmed, returns the cached result.
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
            )
        )
    ).scalar_one_or_none()

    if pending is None:
        raise ResourceNotFoundError()

    # Idempotent — already confirmed
    if pending.confirmed_at is not None:
        return serialize_message(pending)

    # Execute the tool
    tool_name = pending.tool_name or ""
    tool_args = pending.tool_args or {}
    result = await dispatch_tool(tool_name, tool_args, session=session, principal=principal)

    # Persist result and mark confirmed
    pending.tool_result = result
    pending.confirmed_at = datetime.now(UTC)
    pending.requires_confirmation = False

    # Write a follow-up assistant message summarising the outcome
    ok = result.get("ok", False)
    summary_text = (
        _confirmation_result_text(tool_name)
        if ok
        else _confirmation_error_text(tool_name, result)
    )
    follow_up = ChatMessage(
        id=uuid.uuid4(),
        session_id=chat.id,
        role="assistant",
        content=summary_text,
        created_at=datetime.now(UTC),
    )
    session.add(follow_up)
    chat.last_message_at = datetime.now(UTC)
    await session.commit()

    return {
        "confirmed": serialize_message(pending),
        "reply": serialize_message(follow_up),
    }


def _confirmation_result_text(tool_name: str) -> str:
    if tool_name == "save_job":
        return "Đã lưu việc làm này vào danh sách của bạn."
    if tool_name == "apply_job":
        return "Đã nộp đơn ứng tuyển. Bạn có thể theo dõi trạng thái trong **Đơn ứng tuyển**."
    if tool_name == "move_candidate_stage":
        return "Đã cập nhật trạng thái ứng viên."
    return "Đã thực hiện thao tác."


def _confirmation_error_text(tool_name: str, result: dict[str, Any]) -> str:
    error = result.get("error")
    if tool_name == "apply_job":
        if error == "no_cv_found":
            return "Bạn chưa có CV để nộp đơn. Hãy tạo hoặc upload CV trong **CV Studio** trước."
        if error == "already_applied":
            return (
                "Bạn đã ứng tuyển vị trí này rồi. "
                "Hãy kiểm tra trạng thái trong **Đơn ứng tuyển**."
            )
        return "Mình chưa nộp đơn được lúc này. Bạn có thể mở trang việc làm và nhấn **Ứng tuyển**."
    if tool_name == "save_job":
        return "Mình chưa lưu được việc làm này. Bạn có thể mở trang việc làm và nhấn nút lưu."
    return "Mình chưa thực hiện được thao tác này. Vui lòng thử lại."


# --------------------------------------------------------------------------- #
# LLM calls (cost-tracked)                                                    #
# --------------------------------------------------------------------------- #


async def llm_complete(
    history: list[AIMessage],
    *,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    system_prompt: str | None = None,
) -> str:
    """Call the LLM with the conversation history and return the raw text.

    ``system_prompt`` selects the persona system prompt (student vs partner);
    callers should always pass it explicitly — it defaults to the student
    prompt only for backward compatibility with any caller not yet updated.

    When ``db`` is provided, writes a row to ``ai_usage_log`` via the async
    path (mandatory cost tracking per AI_PRODUCT_SPEC §5.4). Degrades silently
    to sync log-only if the DB write fails — never breaks the chat path.
    """
    from app.ai.gateway import runtime_config
    from app.ai.gateway.factory import get_provider_for_alias, real_provider_active
    from app.ai.gateway.offline import OfflineProvider
    from app.ai.gateway.output_guard import guard_completion
    from app.ai.observability.cost_estimator import estimate_cost_usd
    from app.ai.observability.usage import log_ai_usage, log_ai_usage_async
    from app.modules.ai_settings.application.budget_guard import check_async

    alias = runtime_config.current().chat_model_alias
    resolved_system_prompt = system_prompt or assistant_prompt.SYSTEM_PROMPT
    messages = [AIMessage(role="system", content=resolved_system_prompt)] + history

    if real_provider_active():
        try:
            provider = get_provider_for_alias(alias)
        except Exception:
            provider = OfflineProvider()
    else:
        provider = OfflineProvider()

    # Estimate cost and enforce daily budget BEFORE consuming tokens (§11.2).
    prompt_chars = sum(len(m.content) for m in messages)
    estimated_cost = estimate_cost_usd(alias, prompt_chars=prompt_chars, completion_chars=256)
    if db is not None and real_provider_active():
        await check_async(
            db,
            alias=alias,
            estimated_cost_usd=estimated_cost,
            user_id=user_id,
        )

    try:
        completion = await provider.complete(
            messages, alias=alias, temperature=0.4, max_tokens=800
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

    text = guard_completion(completion)
    completion_chars = len(text)
    cost_usd = estimate_cost_usd(
        alias,
        prompt_chars=prompt_chars,
        completion_chars=completion_chars,
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
    return text


async def llm_stream_chunks(
    history: list[AIMessage],
    *,
    db: AsyncSession | None = None,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a chat turn through the governed AI task runner."""
    from app.ai.gateway import runtime_config
    from app.ai.gateway.task_runner import AiTaskRunner

    alias = runtime_config.current().chat_model_alias
    messages = [AIMessage(role="system", content=assistant_prompt.SYSTEM_PROMPT)] + history
    runner = AiTaskRunner(
        db,
        alias=alias,
        task_type=_TASK_TYPE,
        user_id=user_id,
        session_id=session_id,
    )
    async for chunk in runner.stream(messages, temperature=0.4, max_tokens=800):
        yield chunk
