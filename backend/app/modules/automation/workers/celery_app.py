"""Celery application skeleton.

Importable in Phase 0 but not required to run — local development uses the inline
task queue (``app.core.worker``). When background workers are needed, start::

    uv run celery -A app.modules.automation.workers.celery_app worker -l info

All tasks must be idempotent (``docs/ARCHITECTURE.md`` §4.5).
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vinuni_career",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="default",
    worker_max_tasks_per_child=200,
    timezone=settings.timezone,
    enable_utc=True,
)


@celery_app.task(name="health.ping")
def ping() -> str:
    """Trivial liveness task (idempotent)."""

    return "pong"
