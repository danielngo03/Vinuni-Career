from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "c2_career_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.ai_tasks",
        "app.workers.tasks.data_sync_tasks",
        "app.workers.tasks.email_tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)
