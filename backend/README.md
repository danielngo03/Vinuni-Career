# VinUni Career Platform — Backend (Phase 0)

Greenfield FastAPI backend scaffold. Local-first, no Docker required for the app runtime.

## Requirements

- Python 3.12 (managed via `uv`)
- PostgreSQL (local) — see `DATABASE_URL` in `.env`
- Redis (optional in Phase 0) — see `REDIS_URL`

## Quick start

```bash
uv sync                       # install dependencies
uv run alembic upgrade head   # apply baseline migration
make dev                      # run API at http://localhost:8000
```

Health checks:

- `GET /api/v1/health` — liveness, always 200.
- `GET /api/v1/ready` — readiness, checks DB (required) + Redis (optional/degraded).

## Quality gates

```bash
make test       # pytest (no real AI keys, no Redis required)
make lint       # ruff
make typecheck  # mypy (scoped to app/)
make check      # lint + typecheck + test (the combined gate; run this before pushing)
make migrate    # alembic upgrade head
make downgrade  # alembic downgrade base
```

## Local data reset and seed

The development seed is intentionally idempotent and now seeds the lookup tables
it depends on before creating marketplace data:

- provinces and wards from `scripts/seeds/provinces.json` / `wards.json`
- the 3-level industry taxonomy from `scripts/seeds/industry_taxonomy.py`
- partner companies, official-logo crawl targets, jobs, RBAC members, and linked
  job metadata such as `industry_id`, multi-location JSON, seniority level, and
  structured candidate requirements

For a clean local database:

```bash
uv run python scripts/reset_local_db.py
uv run alembic upgrade head
uv run python scripts/seed_dev.py
```

### Pre-commit (optional, recommended)

`.pre-commit-config.yaml` wires `ruff check`, `ruff format --check`, and `mypy`
as commit-time hooks (via `uv run`, so they always match `make check` exactly —
no separate tool versions to drift). One-time setup after `uv sync`:

```bash
uv run pre-commit install
```

After that, every `git commit` runs the same lint/format/type checks
automatically. Run them on demand without committing with:

```bash
uv run pre-commit run --all-files
```

## Layout

- `app/core/` — config, db engine/session, logging, queue interface.
- `app/bootstrap/` — app lifespan + router mounting.
- `app/shared/` — exceptions, responses, pagination, RBAC, audit, base models.
- `app/api/` — cross-cutting routes (health/readiness).
- `app/ai/gateway/` — provider-agnostic AI gateway (offline + OpenAI-compatible) + output guard.
- `app/ai/extraction/` — text-native document extraction + CV upload validation.
- `app/modules/notifications/` — outbox dispatch, template renderer, local email adapter.
- `app/modules/automation/workers/` — Celery app skeleton (importable, not required to run).
- `alembic/` — async migration env + baseline migration.

## Notes

- `PGVECTOR_ENABLED=false` locally (running Postgres has no `vector` extension). RAG/pgvector is Phase 2.
- AI real calls are gated behind `AI_REAL_CALLS_ENABLED` (default false). Tests use the offline provider.
