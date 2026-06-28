import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.opportunities.application.job_scheduler import job_scheduler_loop

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup")
    scheduler_task = asyncio.create_task(job_scheduler_loop())
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutdown")
