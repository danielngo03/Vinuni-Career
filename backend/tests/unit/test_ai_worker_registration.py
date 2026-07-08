"""Verify the ``make worker-ai`` include path actually registers the AI task.

The Makefile target starts Celery with
``--include=app.ai.agents.worker_tasks`` on queues ``ai,default``. This test
proves that importing that module (exactly what ``--include`` does) registers
the workforce subtask on the shared Celery app under its stable name, and
that dispatch routes it to the ``ai`` queue — so a deployed worker started
with the documented command will really consume workforce subtasks.
"""

from __future__ import annotations

import app.ai.agents.worker_tasks as worker_tasks  # noqa: F401  (the --include)
from app.modules.automation.workers.celery_app import celery_app


def test_workforce_task_registered_on_shared_app() -> None:
    assert worker_tasks.TASK_NAME in celery_app.tasks


def test_dispatch_targets_ai_queue() -> None:
    assert worker_tasks.QUEUE_NAME == "ai"


def test_task_is_ack_late_and_retry_bounded() -> None:
    task = celery_app.tasks[worker_tasks.TASK_NAME]
    assert task.acks_late is True
    assert task.max_retries == worker_tasks.MAX_RETRIES
