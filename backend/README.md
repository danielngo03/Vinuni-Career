# VinUni Career Platform Backend

FastAPI modular monolith for Student, Partner, and University workflows.

## Architecture

```text
app/
├── bootstrap/      # application factory, middleware, exception mapping, routes
├── shared/         # IDs, errors, events, pagination, security primitives
├── modules/        # business capabilities with four-layer boundaries
├── ai/             # provider-independent AI pipelines and safety
└── platform/       # database, cache, storage, search, workflows, telemetry
```

Every business module owns:

```text
module/
├── api/
├── application/
├── domain/
└── infrastructure/
```

`bootstrap/routes.py` is the only HTTP composition root. Domain code must not
import FastAPI, SQLAlchemy, or platform adapters. Architecture tests enforce
these rules.

The remaining migration debt is documented in
[`architecture/inventory.md`](architecture/inventory.md).

## Local setup

```bash
make install
make init-db
make run
```

- API: `http://127.0.0.1:8000/api/v1`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Scalar: `http://127.0.0.1:8000/scalar`

## Verification

```bash
make check
make migration-check
```

`make check` runs Ruff and the complete unit, architecture, contract, and E2E
suite.

## Worker processes

```bash
WORKER_QUEUES=ai ./scripts/start_worker.sh
WORKER_QUEUES=documents ./scripts/start_worker.sh
WORKER_QUEUES=notifications ./scripts/start_worker.sh
```

Production should set `WORKFLOW_BACKEND=celery` until the Temporal adapter is
enabled. `local` is only an in-process development fallback.

## AI safety and operations

- AI requests are persisted as tenant-scoped `ai_runs`.
- APIs return a run ID before execution and expose SSE progress.
- The specialist workforce has explicit agents for CV extraction, profile
  matching, JD analysis, moderation, verification, admin review, and career
  coaching. `GET /api/v1/ai/runs/capabilities` exposes their responsibilities
  and human-review boundaries.
- Career coaching uses a bounded ReAct runtime with an allow-listed tool set,
  finite step budget, redacted output, and auditable action summaries. Hidden
  model reasoning is never persisted.
- Ingestion supports signature checks and honest OCR escalation. Retrieval runs
  chunking, embedding, dense/sparse fusion, and provider reranking with a
  deterministic fallback.
- Provider routing, circuit breaking, PII masking, prompt-injection checks,
  structured extraction, hybrid retrieval, and offline fallback are available.
- Auto-approval is controlled by versioned institution policy and never
  performs automatic rejection.
- Celery is the supported distributed worker transport. Temporal, malware
  scanning, pgvector persistence, and evaluation-based release gates remain
  production deployment work and are intentionally not presented as complete.
