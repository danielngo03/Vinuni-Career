"""Conversation memory helpers for agentic tool planning."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_assistant.application.agentic.models import ConversationEntity
from app.modules.ai_assistant.domain.models import ChatMessage

_ORDINAL_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (1, re.compile(r"\b(đầu\s*tiên|thứ\s*nhất|số\s*1|#?1|first)\b", re.IGNORECASE)),
    (2, re.compile(r"\b(thứ\s*hai|thứ\s*2|số\s*2|#?2|second)\b", re.IGNORECASE)),
    (3, re.compile(r"\b(thứ\s*ba|thứ\s*3|số\s*3|#?3|third)\b", re.IGNORECASE)),
    (4, re.compile(r"\b(thứ\s*tư|thứ\s*4|số\s*4|#?4|fourth)\b", re.IGNORECASE)),
    (5, re.compile(r"\b(thứ\s*năm|thứ\s*5|số\s*5|#?5|fifth)\b", re.IGNORECASE)),
)

_REFERENCE_RE = re.compile(
    r"\b(cái|job|việc|vị\s*trí|công\s*ty|company|event|sự\s*kiện|cv|hồ\s*sơ)\s*"
    r"(đó|này|kia|vừa\s*rồi|trên)\b",
    re.IGNORECASE,
)


async def resolve_recent_entity(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    text: str,
    kinds: set[str],
    search_limit: int = 12,
) -> ConversationEntity | None:
    """Resolve "job đó", "cái thứ 2", etc. from hidden tool-result memory."""

    ordinal = _extract_ordinal(text)
    has_reference = ordinal is not None or _REFERENCE_RE.search(text)
    if not has_reference:
        return None

    rows = (
        (
            await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == "tool_result",
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(search_limit)
            )
        )
        .scalars()
        .all()
    )

    wanted_position = ordinal or 1
    for row in rows:
        entities = [
            entity
            for entity in extract_entities(row.tool_name or "", row.tool_result or {})
            if entity.kind in kinds
        ]
        if not entities:
            continue
        if wanted_position == 999:
            return entities[-1]
        if wanted_position <= len(entities):
            return entities[wanted_position - 1]
        if ordinal is None:
            return entities[0]
    return None


def extract_entities(tool_name: str, result: dict[str, Any]) -> list[ConversationEntity]:
    """Extract user-referenceable entities from a tool result."""

    if not result.get("ok"):
        return []

    if tool_name in {"search_jobs", "recommend_jobs", "get_saved_jobs", "get_partner_jobs"}:
        return _entities_from_items(
            result.get("jobs") or result.get("recommendations") or result.get("saved_jobs") or [],
            kind="job",
            source_tool=tool_name,
        )
    if tool_name == "get_job_detail":
        job = result.get("job") or {}
        return _entities_from_items([job], kind="job", source_tool=tool_name)
    if tool_name == "search_companies":
        return _entities_from_items(
            result.get("companies") or [],
            kind="company",
            source_tool=tool_name,
        )
    if tool_name == "get_company_detail":
        company = result.get("company") or {}
        return _entities_from_items([company], kind="company", source_tool=tool_name)
    if tool_name in {"search_events", "get_upcoming_events", "get_my_registered_events"}:
        return _entities_from_items(
            result.get("events") or result.get("registered_events") or [],
            kind="event",
            source_tool=tool_name,
        )
    if tool_name == "get_my_cvs":
        return _entities_from_items(
            result.get("cvs") or [],
            kind="cv",
            source_tool=tool_name,
        )
    return []


def _extract_ordinal(text: str) -> int | None:
    lowered = text.lower()
    if re.search(r"\b(cuối|last)\b", lowered):
        return 999
    for value, pattern in _ORDINAL_PATTERNS:
        if pattern.search(text):
            return value
    return None


def _entities_from_items(
    items: Iterable[dict[str, Any]],
    *,
    kind: str,
    source_tool: str,
) -> list[ConversationEntity]:
    entities: list[ConversationEntity] = []
    for index, item in enumerate(items, start=1):
        url = _as_optional_str(item.get("url"))
        entity_id = _as_optional_str(item.get("id")) or _id_from_url(url)
        label = _label_for_item(item, kind=kind)
        if not entity_id and kind in {"job", "event", "cv"}:
            continue
        entities.append(
            ConversationEntity(
                kind=kind,  # type: ignore[arg-type]
                id=entity_id,
                label=label,
                url=url,
                source_tool=source_tool,
                position=index,
            )
        )
    return entities


def _label_for_item(item: dict[str, Any], *, kind: str) -> str:
    if kind == "job":
        title = item.get("title") or item.get("job_title") or "Vị trí tuyển dụng"
        company = item.get("company") or item.get("company_name") or ""
        return f"{title} · {company}".strip(" ·")
    if kind == "company":
        return str(item.get("name") or item.get("display_name") or "Công ty")
    if kind == "event":
        return str(item.get("title") or "Sự kiện")
    if kind == "cv":
        return str(item.get("title") or "CV")
    return str(item.get("title") or item.get("name") or "Mục đã chọn")


def _id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.rstrip("/").split("/")[-1]
    return value or None


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
