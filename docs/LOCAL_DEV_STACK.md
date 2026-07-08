# Local Development Stack — VinUni Career Platform

> Purpose: keep the greenfield build lightweight and runnable on localhost before any Docker-first workflow.

---

## 1. Local-First Rule

- Backend and frontend run directly on the machine during early development.
- Docker is optional for infrastructure only and must not be required to run the app in Phase 0/1.
- Heavy services are feature-flagged behind adapters.
- Any generated scaffold must include `.env.example`, local run commands, and a no-network test path.

---

## 2. Backend Defaults

- Python 3.12.
- FastAPI, SQLAlchemy 2 async, Alembic.
- `uv` for dependency management.
- Postgres local for integration tests; SQLite/in-memory only for narrow unit tests.
- Redis optional in Phase 0; use an adapter with inline fallback for local smoke tests.
- Celery interface is required, but worker execution may be inline locally until background workers are needed.
- Time-based background work (outbox drain, reveal expiry, job deadline auto-close)
  runs in a standalone stdlib-asyncio scheduler process (ADR-0003), not in the API
  process and not via Celery beat in V1. Default `BACKGROUND_WORKER_MODE=inline`
  leaves it off (and off in tests).

### Background scheduler run command

Run alongside the API in a separate terminal (it refuses to start unless
`BACKGROUND_WORKER_MODE=scheduler`):

```bash
cd backend && BACKGROUND_WORKER_MODE=scheduler uv run python -m app.worker
```

Cadences: `outbox.drain` 15s, `reveal.expire_sweep` 5min,
`opportunities.deadline_close` 10min. The loop ticks every
`SCHEDULER_BASE_TICK_SECONDS` (default 15) and runs each job at its own interval.
Run exactly one scheduler process in V1 (single-instance assumption; the outbox
claim uses `FOR UPDATE SKIP LOCKED` on Postgres for the future multi-worker path).

Do not choose heavyweight dependencies when a stable lightweight option exists.

---

## 3. Frontend Defaults

- Next.js App Router.
- TypeScript strict.
- Tailwind.
- next-intl for `vi` and `en`.
- Lightweight component primitives first; avoid importing a large UI framework unless it materially improves speed or quality.
- Browser QA uses Playwright/chrome-devtools MCP at 375, 768, 1024, and 1440 px.

---

## 4. OCR And Document Parsing

Default stack:

- PDF text/layout: PyMuPDF/PyMuPDF4LLM adapter when available; `pdfplumber`
  fallback for simple text PDFs.
- DOCX text: `python-docx`.
- OCR fallback: Tesseract with `vie+eng`.
- PDF render fallback: `pdf2image` only when OCR is needed.
- CV parsing: deterministic extraction first, LLM structuring second, human review always available.
- Broad layout/OCR engines such as Docling are feature-flagged; Marker requires
  ADR approval before becoming default because of heavier PyTorch/GPL/model
  tradeoffs.

Avoid by default:

- Always-on PaddleOCR.
- Always-on large local embedding/reranker models.
- GPU-only dependencies.
- Sending raw files directly to LLM providers.

---

## 5. AI Local Testing

- Unit tests use offline/fake provider.
- Manual smoke tests use low-cost/free OpenRouter or DeepSeek-compatible aliases.
- Real calls are opt-in with `AI_REAL_CALLS_ENABLED=true`.
- Maximum real calls per test run defaults to 3.
- AI write tools must still require confirmation, even in local dev.

---

## 6. Email And Notifications

- Local default: Mailpit or console email.
- No real outbound email in automated tests.
- Notification dispatch uses an outbox table and idempotent worker.
- The outbox is drained by the scheduler's `outbox.drain` job (every 15s) with
  exponential-backoff retry and a terminal `dead` dead-letter state after
  `OUTBOX_MAX_ATTEMPTS` (default 5) — see `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`
  §7.1. Start `python -m app.worker` (above) to actually deliver queued email.
- Email template preview and variable validation must work without sending real email.

---

## 6b. Demo Marketplace Seed (dev only)

The public career gateway (`/marketplace`, `/companies`) looks empty on a fresh
local DB. A clearly-marked, **synthetic, dev-only** seeder populates it with
fictional partner companies + active jobs so the gateway can be honestly
visually reviewed (`docs/DESIGN.md`: "seeded dev data only when explicitly
marked").

Run from `backend/`:

```bash
# Upsert ~12 fictional companies (mix of verified, ~60% with placeholder logos),
# ~30 active jobs (some sponsored/featured, 2 past-deadline), and ~8 published
# events (varied type/format, future dates, some sponsored/featured; one with
# capacity=2 filled by 2 synthetic demo students so a 3rd UI registration
# waitlists). Idempotent.
uv run python -m scripts.seed_demo_marketplace

# Remove ONLY the demo rows (slug prefix `demo-` + the demo `demo-…@demo.local`
# users), including demo events + their registrations, in FK-safe order.
uv run python -m scripts.seed_demo_marketplace --wipe
```

Guarantees: refuses to run unless `APP_ENV` is local/dev; every row is fictional
and tagged `demo-`; logos are obviously-synthetic placeholder marks generated
locally (no network, no secrets); `--wipe` never touches real/test accounts or
real seed data. Synthetic placeholder logos are stored through the same storage
backend the real logo pipeline uses, so `GET /api/v1/companies/{slug}/logo`
serves them. After (re)seeding, restart the dev server so pooled DB connections
pick up newly committed rows.

---

## 7. Acceptance For Phase 0

Phase 0 is not complete unless:

- Backend health works locally without Docker app runtime.
- Frontend shell works locally.
- Tests can run without real provider keys.
- OCR/parser tests have tiny fixtures in vi/en.
- Email template rendering test uses local renderer only.
