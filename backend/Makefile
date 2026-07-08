.PHONY: install dev worker-ai test lint typecheck migrate downgrade revision fmt check

install:
	uv sync

dev:
	uv run uvicorn app.main:app --reload --port 8000

# Background worker for AI workforce subtasks (AI_PRODUCT_SPEC §4.2) plus the
# default queue. Requires a running Redis broker (docs/LOCAL_DEV_STACK.md).
# --include registers app.ai.agents.worker_tasks on the shared celery app
# without coupling the automation module to AI code at import time.
worker-ai:
	uv run celery -A app.modules.automation.workers.celery_app worker \
		-l info -Q ai,default --include=app.ai.agents.worker_tasks

test:
	uv run pytest -q

lint:
	uv run ruff check .

fmt:
	uv run ruff check --fix . && uv run ruff format .

typecheck:
	uv run mypy app

# Combined quality gate: lint + typecheck + test, in that order (fastest signal
# first). CI and pre-commit should both run this instead of the individual
# targets so lint/type debt cannot silently reaccumulate between them.
check: lint typecheck test

migrate:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade base

revision:
	uv run alembic revision -m "$(m)"
