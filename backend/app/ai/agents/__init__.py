"""Multi-agent "workforce" pattern (``docs/AI_PRODUCT_SPEC.md`` §4.2).

A coordinator agent decomposes a complex task into idempotent subtasks,
dispatches each subtask to a Celery worker, and aggregates results once every
subtask has reached a terminal state. See ``workforce.py`` for the public
entrypoint other modules should call.
"""

from __future__ import annotations
