# Backend architecture inventory

Updated: 2026-06-18

## Executive assessment

The backend now has a real modular-monolith skeleton and automated boundary
checks. It is substantially cleaner than the legacy layout, but it is not yet
the final V2 architecture.

Current assessment:

- Composition and package layout: good.
- Access/RBAC and pending-session boundary: good.
- Verification policy and state machine: functional.
- Document lifecycle and outbox foundation: functional, still incomplete.
- AI gateway and run lifecycle: functional foundation.
- Specialist agent workforce and bounded ReAct runtime: functional, auditable foundation.
- Chunking, embeddings, dense/sparse fusion, and reranking: integrated for indexed text.
- Domain ownership of ORM models: incomplete.
- Temporal orchestration and production evaluation gates: not complete.
- Reporting projections: incomplete; dashboards still perform cross-domain reads.

## Current module map

| Capability | Owner | State |
| --- | --- | --- |
| App composition, middleware, errors | `app/bootstrap` | Clean composition root |
| Shared kernel | `app/shared` | Canonical errors/events/IDs; compatibility alias remains for `shared.exceptions` |
| Accounts, sessions, OIDC, identity, RBAC | `app/modules/access` | Consolidated; former `identity` module removed |
| VinUni taxonomy and organization administration | `app/modules/institution` | Former generic `organizations` module absorbed |
| Student profile | `app/modules/students` | Four-layer skeleton; ORM ownership still in platform |
| Partner domain | `app/modules/partners` | Skeleton only; onboarding ownership pending |
| Jobs, events, bookmarks | `app/modules/opportunities` | Routers/services/models moved |
| CVs, applications, interviews | `app/modules/recruitment` | Routers/services/models moved |
| Notifications and reviews | `app/modules/engagement` | Moved; domain policy depth pending |
| Documents | `app/modules/documents` | Presigned upload contract, ACL, scan state machine, outbox event |
| Reporting | `app/modules/reporting` | Moved; projection tables not yet authoritative |
| Automation and workers | `app/modules/automation` | Celery queues isolated; Temporal adapter pending |
| AI operation lifecycle | `app/modules/ai_operations` | Tenant-scoped runs and SSE; execution uses workflow port |
| AI pipelines | `app/ai` | Gateway, honest extraction escalation, chunking/embedding/hybrid retrieval/rerank, safety, specialist workforce |
| Infrastructure adapters | `app/platform` | DB/cache/storage/search/workflow/telemetry/integration boundaries |

## Enforced architecture rules

`tests/architecture/test_module_boundaries.py` prevents:

- return of global `app/services`, `app/schemas`, `app/infra`, `app/core`,
  `app/domain`, `app/workers`, or `app/api` source packages;
- business modules missing `api/application/domain/infrastructure`;
- domain layers importing FastAPI, SQLAlchemy, bootstrap, or platform adapters;
- application layers importing HTTP/bootstrap concerns;
- recreation of the generic `organizations` module.

## Remaining violations and debt

### P0 before production

1. Replace the local workflow dispatcher with Temporal for verification and
   long-running AI workflows. Celery is an acceptable interim worker transport,
   not the final human-in-the-loop orchestrator.
2. Implement a real malware scanner worker and authenticated object-upload path
   for local development. S3 presigned PUT is supported; local presigned PUT
   still requires a serving adapter.
3. Move the in-process specialist execution graph to Temporal activities and
   add durable cancellation, per-provider cost budgets, and prompt registry IDs.
4. Add PostgreSQL/pgvector integration tests and production load tests.

### P1 architecture completion

1. Split generic `app/modules/registrations`:
   - Student onboarding commands/models into `students`;
   - Partner onboarding commands/models into `partners`;
   - verification policy, evidence, review queue, and provider contracts into
     `institution`.
2. Move platform-owned business ORM models to module infrastructure:
   - identity/session models to `access`;
   - academic models to `students`;
   - verification models to their owning modules.
3. Stop importing the compatibility aggregator
   `app.platform.database.models` from application/API code; use repositories
   and application ports.
4. Replace cross-module ORM relationships with IDs and explicit queries/ports.
5. Move root module `schemas.py` files into API contracts or application DTOs.
6. Replace dashboard cross-domain queries with transactional-outbox-fed
   projection tables.

### P2 capability depth

1. Add SIS/CSV roster providers and registry/tax providers.
2. Add pgvector persistence and production index mappings; current hybrid
   retrieval is adapter-backed and fully testable in memory.
3. Add evaluation datasets and measurable RRF/rerank lift before enabling
   model-based ranking changes globally.
4. Add shadow metrics, human override metrics, fairness/calibration reports,
   and release gates.
5. Remove compatibility routes tagged `compatibility/*` after API v2 clients
   migrate.

## Test baseline

- Ruff: clean.
- Mypy: clean for `app`.
- Unit, architecture, contract, and E2E tests: 38 passing.
- Alembic: upgrade → downgrade base → upgrade passes on a fresh database.
- New security coverage includes tenant-scoped AI runs and authenticated
  document scan callbacks.

## Removal rule

Compatibility code may be removed only when:

1. its replacement contract is present in OpenAPI;
2. behavior and authorization tests cover the replacement;
3. frontend/generated clients no longer import the old contract;
4. migration upgrade/downgrade remains green.
