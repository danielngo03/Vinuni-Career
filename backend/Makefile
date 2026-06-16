.PHONY: install test lint run init-db compose-up compose-down compose-logs

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/python -m ruff check app tests scripts

init-db:
	.venv/bin/python scripts/init_db.py

run:
	.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

compose-up:
	docker compose -f deploy/compose/docker-compose.yml up --build

compose-down:
	docker compose -f deploy/compose/docker-compose.yml down

compose-logs:
	docker compose -f deploy/compose/docker-compose.yml logs -f --tail=100
