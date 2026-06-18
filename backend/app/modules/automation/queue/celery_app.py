from __future__ import annotations

from celery import Celery

from app.shared.config import settings

celery_app = Celery(
    "vinuni_career_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.modules.automation.workers.tasks.ai_tasks",
        "app.modules.automation.workers.tasks.data_sync_tasks",
        "app.modules.automation.workers.tasks.email_tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    task_routes={
        "ai.*": {"queue": "ai"},
        "documents.*": {"queue": "documents"},
        "email.*": {"queue": "notifications"},
        "data_sync.*": {"queue": "default"},
    },
)
