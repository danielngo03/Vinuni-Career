.PHONY: install test lint typecheck check contract run init-db migrate migrate-down migration-check ai-smoke

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/python -m ruff check app tests scripts alembic

typecheck:
	.venv/bin/python -m mypy app --ignore-missing-imports --no-error-summary

check: lint typecheck test

contract:
	.venv/bin/python scripts/export_openapi.py

init-db:
	.venv/bin/alembic upgrade head
	.venv/bin/python scripts/init_db.py

migrate:
	.venv/bin/alembic upgrade head

migrate-down:
	.venv/bin/alembic downgrade -1

migration-check:
	rm -f /tmp/vinuni-career-migration-check.db
	DATABASE_URL=sqlite:////tmp/vinuni-career-migration-check.db .venv/bin/alembic upgrade head
	DATABASE_URL=sqlite:////tmp/vinuni-career-migration-check.db .venv/bin/alembic downgrade base
	DATABASE_URL=sqlite:////tmp/vinuni-career-migration-check.db .venv/bin/alembic upgrade head

ai-smoke:
	.venv/bin/python scripts/smoke_ai.py

run:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
