"""Startup / shutdown lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai.extraction.adapters import (
    GatewayLlmStructuringAdapter,
    set_llm_structuring_adapter,
)
from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.metadata import import_all_models
from app.core.worker import get_queue
from app.modules.ai_settings.application import resolver as ai_settings_resolver
from app.modules.documents.application.template_seed import (
    ensure_default_templates as ensure_default_cv_templates,
)
from app.modules.notifications.application.template_seed import ensure_default_templates
from app.modules.onboarding.application import doc_verification
from app.modules.recruitment.application.access import install_authorizer

logger = logging.getLogger(__name__)


async def _seed_default_templates() -> None:
    """Best-effort: ensure baseline notification templates exist on startup.

    Idempotent and non-fatal — a not-yet-migrated DB or transient error must not
    block the API from coming up.
    """

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            created = await ensure_default_templates(session)
            await session.commit()
        if created:
            logger.info("notifications.templates_seeded", extra={"created": created})
    except Exception:  # noqa: BLE001 - startup must not crash on seed failure
        logger.warning("notifications.template_seed_failed", exc_info=True)


async def _seed_default_cv_templates() -> None:
    """Best-effort: ensure baseline CV templates exist on startup."""

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            created = await ensure_default_cv_templates(session)
            await session.commit()
        if created:
            logger.info("cv.templates_seeded", extra={"created": created})
    except Exception:  # noqa: BLE001 - startup must not crash on seed failure
        logger.warning("cv.template_seed_failed", exc_info=True)


async def _publish_ai_runtime_config() -> None:
    """Resolve the ``ai_settings`` row and publish the runtime snapshot (ADR-0011 §2).

    Best-effort: the gateway is already env-bootstrapped, so a not-yet-migrated DB
    or transient error must not block startup — it simply leaves the env snapshot
    in place until the next resolve.
    """

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await ai_settings_resolver.resolve_and_publish(session)
            await session.commit()
        logger.info("ai_settings.runtime_published")
    except Exception:  # noqa: BLE001 - startup must not crash on resolve failure
        logger.warning("ai_settings.runtime_publish_failed", exc_info=True)


def _install_ai_adapters() -> None:
    """Install runtime AI adapters that are gated later by resolved settings."""

    set_llm_structuring_adapter(GatewayLlmStructuringAdapter())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    import_all_models()
    _install_ai_adapters()
    # Wire the recruitment partner-access authorizer into the documents snapshot
    # facade so partner CV downloads resolve (watermarked) for owned-org jobs.
    install_authorizer()
    get_queue().register(doc_verification.TASK_NAME, doc_verification.run_verification)
    await _seed_default_templates()
    await _seed_default_cv_templates()
    await _publish_ai_runtime_config()
    logger.info(
        "app.startup",
        extra={"env": settings.app_env, "worker_mode": settings.background_worker_mode},
    )

    # Embedded scheduler — single-process local dev convenience only.
    # In production use the standalone `python -m app.worker` process instead
    # so multiple API workers don't each run their own scheduler (ADR-0003).
    scheduler_task: asyncio.Task[None] | None = None
    if settings.background_worker_mode == "scheduler":
        from app.modules.automation.scheduler import runner  # noqa: PLC0415

        scheduler_task = asyncio.create_task(runner.run_forever(), name="embedded-scheduler")
        logger.info("scheduler.embedded_started")

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            logger.info("scheduler.embedded_stopped")
        await dispose_engine()
        logger.info("app.shutdown")
