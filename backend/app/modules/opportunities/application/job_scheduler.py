from __future__ import annotations

import asyncio
import logging

from app.modules.opportunities.application.job_service import run_due_job_scheduled_actions
from app.platform.database.session import SessionLocal

logger = logging.getLogger(__name__)


async def job_scheduler_loop(interval_seconds: int = 30) -> None:
    while True:
        try:
            with SessionLocal() as db:
                executed = run_due_job_scheduled_actions(db)
                if executed:
                    logger.info("Executed %s scheduled job action(s)", executed)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled job action poller failed")
        await asyncio.sleep(interval_seconds)
