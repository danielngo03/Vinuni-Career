"""Celery task definitions for workforce subtask execution.

Thin by design: every task resolves an executor from ``EXECUTORS`` and calls
straight into the *existing*, already-governed application service (which in
turn calls the AI gateway through its established entrypoint, e.g.
``app.ai.cv.llm.generate_json_note``). No provider/model access happens here.

Registered on the SAME shared ``celery_app`` instance as every other
background task in this codebase (``app.modules.automation.workers.celery_app``
— see its module docstring for the worker start command and the
``task_acks_late``/idempotency conventions this task follows). This module is
never imported by ``app.modules.automation.workers`` itself; a deployed worker
process must include it explicitly. The supported local/dev start command is::

    make worker-ai
    # = uv run celery -A app.modules.automation.workers.celery_app worker \\
    #       -l info -Q ai,default --include=app.ai.agents.worker_tasks

Requires a running Redis broker (docs/LOCAL_DEV_STACK.md). Without a worker
running, a dispatched run's subtasks never execute and its status stays
``running`` — dispatch is broker-outage-tolerant by design (see
``dispatch_subtask``). Unit/integration tests set
``celery_app.conf.task_always_eager = True`` so subtasks run synchronously
in-process without a broker (``tests/unit/test_ai_workforce.py``).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents import coordinator
from app.ai.agents.models import SubtaskResult, SubtaskSpec, SubtaskStatus
from app.modules.automation.workers.celery_app import celery_app
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

Executor = Callable[[AsyncSession, Principal, dict], Awaitable[dict]]

MAX_RETRIES = 3
TASK_NAME = "ai.workforce.run_subtask"
QUEUE_NAME = "ai"


async def _execute_screening_brief(
    session: AsyncSession, principal: Principal, payload: dict
) -> dict:
    from app.modules.recruitment.application import screening_brief_service

    application_id = uuid.UUID(payload["application_id"])
    return await screening_brief_service.generate_screening_brief(
        session, principal=principal, application_id=application_id
    )


# Extend the workforce framework with a new subtask type by adding one entry
# here — never by branching an existing executor on ``subtask_type``.
EXECUTORS: dict[str, Executor] = {
    coordinator.SCREENING_BRIEF_SUBTASK_TYPE: _execute_screening_brief,
}


def _run_coro_blocking(coro: Awaitable[dict]) -> dict:
    """Run an async coroutine to completion from sync Celery task code.

    Handles both real deployment (no running loop -> ``asyncio.run``) and
    eager-mode tests (already inside a running event loop -> run the coroutine
    on a dedicated thread with its own loop, since ``asyncio.run`` cannot be
    called while a loop is already running on this thread).
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()  # type: ignore[arg-type]


async def _execute_and_record(
    run_id: uuid.UUID, subtask_key: str, subtask_type: str, payload: dict
) -> dict:
    from app.core.db import get_sessionmaker

    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        existing = await coordinator.get_terminal_result(
            session, run_id=run_id, subtask_key=subtask_key
        )
        if existing is not None:
            # Idempotent no-op: a redelivered message for an already-terminal
            # subtask must never re-call the AI gateway (no double cost).
            return existing
        principal = await coordinator.load_run_principal(session, run_id)

    executor = EXECUTORS.get(subtask_type)
    start = time.monotonic()
    if executor is None:
        result = SubtaskResult(
            key=subtask_key, status=SubtaskStatus.FAILED, error_code="unknown_subtask_type"
        )
    else:
        try:
            async with sessionmaker() as session:
                output = await executor(session, principal, payload)
            result = SubtaskResult(
                key=subtask_key,
                status=SubtaskStatus.SUCCESS,
                result=output,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception:  # noqa: BLE001 - one subtask must not crash the run
            logger.warning(
                "workforce.subtask_failed",
                extra={"subtask_type": subtask_type, "run_id": str(run_id)},
                exc_info=True,
            )
            result = SubtaskResult(
                key=subtask_key,
                status=SubtaskStatus.FAILED,
                error_code="execution_error",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

    async with sessionmaker() as session:
        await coordinator.record_subtask_result(session, run_id=run_id, result=result)
    return result.to_json()


@celery_app.task(
    name=TASK_NAME,
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=5,
    acks_late=True,
)
def run_subtask(self, run_id: str, subtask_key: str, subtask_type: str, payload: dict) -> dict:
    """Execute one workforce subtask and persist its terminal result.

    Idempotent: dedup happens by ``subtask_key`` inside ``_execute_and_record``
    before any AI call is made, so Celery's at-least-once delivery can never
    double-charge or double-write a subtask's result.
    """

    return _run_coro_blocking(
        _execute_and_record(uuid.UUID(run_id), subtask_key, subtask_type, payload)
    )


def dispatch_subtask(*, run_id: uuid.UUID, subtask: SubtaskSpec) -> None:
    """Enqueue one planned subtask. Never raises — a broker outage degrades to
    "run stays in progress until re-dispatched", not a 500 for the caller who
    already got their ``run_id`` back."""

    try:
        run_subtask.apply_async(
            args=[str(run_id), subtask.key, subtask.subtask_type, subtask.payload],
            queue=QUEUE_NAME,
        )
    except Exception:  # noqa: BLE001 - broker unavailable is a known degrade path
        logger.warning(
            "workforce.dispatch_failed",
            extra={"run_id": str(run_id), "subtask_key": subtask.key},
        )
