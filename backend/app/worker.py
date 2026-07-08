"""Standalone background scheduler entrypoint: ``python -m app.worker`` (ADR-0003).

Run alongside the API in its own process::

    cd backend && BACKGROUND_WORKER_MODE=scheduler uv run python -m app.worker

It refuses to start unless ``BACKGROUND_WORKER_MODE=scheduler`` so the default
``inline`` config — and the entire test suite — never spawns a loop, and the API
process never runs periodic jobs (lifecycle decoupled from the request path so the
API can scale to N workers without N schedulers).
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metadata import import_all_models
from app.modules.automation.scheduler import runner

logger = logging.getLogger(__name__)


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.background_worker_mode != "scheduler":
        logger.error(
            "worker.refused_mode",
            extra={
                "mode": settings.background_worker_mode,
                "expected": "scheduler",
            },
        )
        return 2
    import_all_models()
    logger.info(
        "worker.start",
        extra={"base_tick_seconds": settings.scheduler_base_tick_seconds},
    )
    try:
        asyncio.run(runner.run_forever())
    except KeyboardInterrupt:
        logger.info("worker.stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
