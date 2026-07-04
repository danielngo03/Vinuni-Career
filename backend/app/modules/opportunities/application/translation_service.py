"""JD translation service — AI-powered with DB cache.

Cost policy (docs/ENVIRONMENT.md):
- Only calls AI when ``real_provider_active()`` is True.
- Caches in ``job_translations`` so each (job_id, target_lang) pair is
  translated AT MOST ONCE regardless of request volume.
- Falls back gracefully (returns None) when AI is unavailable; callers
  return HTTP 503 and the frontend shows a 'translation unavailable' state.

Supported target languages: vi, en.
Translation direction: any detected source language → the target.
No-op: when source == target (job is already in the requested language).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import factory as ai_factory
from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.prompts.jd_translation.v1 import STATIC_SYSTEM_PROMPT, build_user_message
from app.modules.opportunities.domain.models import Job, JobTranslation
from app.shared.exceptions import AIUnavailableError

logger = logging.getLogger(__name__)

_SUPPORTED_TARGET_LANGS: frozenset[str] = frozenset({"vi", "en"})


class _TranslatableJob(Protocol):
    """Structural shape ``_ai_translate``/``_machine_translate_job`` read off a ``Job``.

    Kept as a narrow ``Protocol`` (rather than the full ``Job`` ORM model)
    because these private helpers only ever read these fields — the offline
    eval runner exercises ``_ai_translate`` with a lightweight stand-in, not a
    real DB-backed ``Job`` row. Field types mirror ``Job`` exactly
    (``app/modules/opportunities/domain/models.py``) so any real ``Job``
    instance satisfies this protocol structurally.
    """

    id: uuid.UUID
    language_code: str
    title: str
    description: str
    requirements: str | None
    benefits: str | None


async def get_or_create_translation(
    session: AsyncSession,
    *,
    job: Job,
    target_lang: str,
) -> dict | None:
    """Return cached or freshly AI-generated translation.

    Returns:
        dict with keys title/description/requirements/benefits/language_code/
        target_lang/from_cache — or None when AI is unavailable.

    Side-effects:
        Writes a new ``JobTranslation`` row when a fresh translation is produced.
    """
    if target_lang not in _SUPPORTED_TARGET_LANGS:
        logger.debug("translate: unsupported target_lang=%s", target_lang)
        return None

    source_lang = getattr(job, "language_code", None) or "en"
    if source_lang == target_lang:
        return None  # Already in the target language — caller should not call translate.

    # Cache check
    existing = (
        await session.execute(
            select(JobTranslation).where(
                JobTranslation.job_id == job.id,
                JobTranslation.target_lang == target_lang,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        return {
            "title": existing.title,
            "description": existing.description,
            "requirements": existing.requirements,
            "benefits": existing.benefits,
            "language_code": source_lang,
            "target_lang": target_lang,
            "from_cache": True,
        }

    if not ai_factory.real_provider_active():
        logger.debug("translate: AI offline — returning None for job_id=%s", job.id)
        return None

    translated = await _ai_translate(job, target_lang=target_lang, session=session)
    if translated is None:
        return None

    # Persist to cache
    row = JobTranslation(
        job_id=job.id,
        target_lang=target_lang,
        title=translated.get("title"),
        description=translated.get("description"),
        requirements=translated.get("requirements"),
        benefits=translated.get("benefits"),
        translated_by=runtime_config.current().chat_model_alias,
    )
    session.add(row)
    await session.flush()

    return {
        **translated,
        "language_code": source_lang,
        "target_lang": target_lang,
        "from_cache": False,
    }


async def _ai_translate(
    job: _TranslatableJob,
    *,
    target_lang: str,
    session: AsyncSession | None = None,
) -> dict | None:
    """Translate JD fields with a fast MT draft plus AI polishing.

    The optional ``deep-translator`` pass is intentionally a draft, not the
    product answer: it is fast and cheap, but can mistranslate HR/legal nuance.
    The platform AI then normalizes terminology, preserves markdown, validates
    the JSON shape, and fills any fields the MT pass could not produce. If the
    AI provider fails after a successful MT pass, the MT draft is still better
    UX than a hard 503 for a public job detail.
    """

    source_lang = getattr(job, "language_code", None) or "en"
    machine_draft = await _machine_translate_job(job, target_lang=target_lang)
    try:
        user_msg = build_user_message(
            source_lang=source_lang,
            target_lang=target_lang,
            title=job.title,
            description=job.description,
            requirements=job.requirements,
            benefits=job.benefits,
            machine_draft=machine_draft,
        )
        runner = AiTaskRunner(
            session,
            alias=runtime_config.current().chat_model_alias,
            task_type="jd_translation",
        )
        completion = await runner.complete(
            [
                AIMessage(role="system", content=STATIC_SYSTEM_PROMPT),
                AIMessage(role="user", content=user_msg),
            ],
            temperature=0.1,
            max_tokens=4096,
        )
        raw = completion.text.strip()

        # Strip optional markdown code block wrapper
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        draft = machine_draft or {}
        return {
            "title": data.get("title") or draft.get("title") or None,
            "description": data.get("description") or draft.get("description") or None,
            "requirements": data.get("requirements") or draft.get("requirements") or None,
            "benefits": data.get("benefits") or draft.get("benefits") or None,
        }
    except (AIUnavailableError, json.JSONDecodeError) as exc:
        logger.warning("translate: AI call failed for job_id=%s: %s", job.id, exc)
        return machine_draft
    except Exception as exc:  # noqa: BLE001
        logger.error("translate: unexpected error for job_id=%s: %s", job.id, exc)
        return machine_draft


async def _machine_translate_job(job: _TranslatableJob, *, target_lang: str) -> dict | None:
    """Best-effort fast translation draft via ``deep-translator``.

    ``deep-translator`` is optional. When the package or upstream service is not
    available, this returns ``None`` and the normal AI translation path continues.
    The helper is deliberately private and never exposes engine details.
    """

    source_lang = getattr(job, "language_code", None) or "auto"
    source = "auto" if source_lang in {"unknown", "mixed"} else source_lang
    fields = {
        "title": job.title,
        "description": job.description,
        "requirements": job.requirements,
        "benefits": job.benefits,
    }

    def _run() -> dict | None:
        try:
            from deep_translator import GoogleTranslator  # type: ignore
        except Exception:
            return None

        out: dict[str, str | None] = {}
        try:
            translator = GoogleTranslator(source=source, target=target_lang)
            for key, value in fields.items():
                if not value:
                    out[key] = None
                    continue
                # Keep chunks conservative; the AI polish pass sees the original
                # fields too, so this draft does not need to be perfect.
                out[key] = translator.translate(value[:4500])
            return out
        except Exception:
            return None

    return await asyncio.to_thread(_run)
