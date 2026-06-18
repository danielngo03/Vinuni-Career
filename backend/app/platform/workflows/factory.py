from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.platform.workflows.protocols import WorkflowDispatcher
from app.shared.config import settings
from app.shared.errors import AppError, ErrorCode

_local_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="local-workflow")


class LocalWorkflowDispatcher:
    """Development fallback; production must use Celery or Temporal."""

    def dispatch_ai_run(self, run_id: str) -> None:
        from app.modules.ai_operations.application.run_executor import execute_ai_run

        if settings.app_env == "test":
            execute_ai_run(run_id)
            return
        _local_executor.submit(execute_ai_run, run_id)


class CeleryWorkflowDispatcher:
    def dispatch_ai_run(self, run_id: str) -> None:
        from app.modules.automation.queue.celery_app import celery_app

        celery_app.send_task("ai.execute_run", args=[run_id], queue="ai")


class TemporalWorkflowDispatcher:
    def dispatch_ai_run(self, run_id: str) -> None:
        raise AppError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message=(
                "Temporal dispatch is selected but the Temporal adapter has not "
                "been enabled in this deployment"
            ),
            status_code=503,
            details={
                "run_id": run_id,
                "address": settings.temporal_address,
                "namespace": settings.temporal_namespace,
                "task_queue": settings.temporal_task_queue,
            },
        )


@lru_cache
def get_workflow_dispatcher() -> WorkflowDispatcher:
    if settings.workflow_backend == "celery":
        return CeleryWorkflowDispatcher()
    if settings.workflow_backend == "temporal":
        return TemporalWorkflowDispatcher()
    return LocalWorkflowDispatcher()
