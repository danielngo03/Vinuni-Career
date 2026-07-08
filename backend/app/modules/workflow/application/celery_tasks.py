"""Celery task registration for the deferred production execution path.
Not exercised by this plan's tests — those call ``execute_flow`` directly
per the inline-worker convention (docs/LOCAL_DEV_STACK.md).
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.db import get_sessionmaker
from app.modules.automation.workers.celery_app import celery_app
from app.modules.workflow.application.execution_service import execute_flow


@celery_app.task(name="workflow.execute_flow", bind=True, max_retries=3)
def run_execute_flow_task(self, execution_id: str) -> None:
    async def _run() -> None:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await execute_flow(session, execution_id=uuid.UUID(execution_id))

    asyncio.run(_run())
