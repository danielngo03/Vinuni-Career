# ADR-0003: Async Scheduler and Periodic Jobs (V1 Local-First)

**Status:** Accepted (Proposed for implementation in the next backend slice)
**Date:** 2026-06-27
**Owner:** system-architect
**Related:** `docs/ARCHITECTURE.md` §4.5/§4.6, `docs/LOCAL_DEV_STACK.md`,
`docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` §7, `docs/BUSINESS_LOGIC.md` §2.2,
`docs/EDGE_CASES_FAILURE_MODES.md`

## Context

The platform has **no running background worker**. `app.core.worker` only ships
the `InlineTaskQueue` (runs enqueued handlers in-process at call time), and
`app.modules.automation.workers.celery_app` is a skeleton with `health.ping` and
**no beat schedule**. Nothing drains time-based work, so three correctness bugs
are live in any deployment:

1. **Outbox never drains.** Product writes call `enqueue_notification` (writes a
   `notification_outbox` row in their own transaction) but nothing ever calls
   `dispatch_service.process_outbox`. Verification, reset, reveal, and job-close
   emails are written and never sent.
2. **Reveal requests never expire.** `reveal_service` only flips
   `pending → expired` *lazily* when the student happens to respond after 72h
   (`respond_reveal`). A request the student ignores stays `pending` forever.
   Because `request_reveal` treats any pending row for the org as an idempotent
   re-hit and any non-pending row as `already_requested`, a **stale pending row
   permanently blocks the partner from re-requesting** — the documented
   "re-request after expiry" behavior is unreachable.
3. **Jobs never auto-close.** `BUSINESS_LOGIC.md` §2.2 requires a job to close
   when `application_deadline` passes, but nothing transitions `active → closed`,
   so expired jobs stay in public listings indefinitely.

Constraints that bound the decision: local-first / **no-Docker-first** runtime
(`LOCAL_DEV_STACK.md`), Redis *is* available locally but optional in Phase 0,
minimize new heavy dependencies, a **single documented run command**, the worker
lifecycle must **not** be coupled to the API request path (so we can scale the API
horizontally later without spawning N schedulers), and the choice must be
reversible toward the production Celery path.

## Decision

### 1. Scheduler mechanism — standalone asyncio process (option a, no new dep)

Adopt a **standalone process** `python -m app.worker` running a small asyncio
periodic loop. **No APScheduler, no Celery beat for V1.**

| Option | Verdict | Why |
| --- | --- | --- |
| **(a) Standalone `python -m app.worker` asyncio loop** | **Chosen** | Zero new deps (stdlib `asyncio`); single run command; lifecycle fully decoupled from API; trivially reversible; reuses the existing async `AsyncSession`/services. |
| (b) Celery beat + worker | Deferred to prod | Correct end-state but adds a beat process + broker hard-dependency and a serialization boundary now; over-weight for Phase 0/1 local-first. |
| (c) FastAPI lifespan in-process task | Rejected | Couples the scheduler to the API process — every Uvicorn worker would run its own copy of every periodic job (duplicate sends, races) the moment we scale out. Violates the "do not couple worker lifecycle to request path" constraint. |

**Shape (no business logic in the scheduler):**

- `backend/app/worker.py` — entrypoint: builds settings, opens the async engine,
  runs `scheduler.run_forever()`. Guarded so it refuses to start when
  `BACKGROUND_WORKER_MODE != "scheduler"`.
- `backend/app/modules/automation/scheduler/runner.py` — the loop + a
  **`tick(now)` entrypoint** that runs every job whose interval is due exactly
  once and returns a per-job result dict. The forever-loop is just
  `while True: await tick(now()); await asyncio.sleep(BASE_TICK)`.
- `backend/app/modules/automation/scheduler/jobs.py` — a static registry of
  `(name, interval_seconds, coro)` entries. Each `coro` opens its **own**
  `AsyncSession`, calls a **domain application service**, commits, and returns
  counts. The scheduler never contains domain rules — it only delegates to
  `notifications`, `recruitment`, and `opportunities` services.

**Production migration path:** when we move to multi-instance, the *same* job
functions in `jobs.py` register as Celery beat schedule entries against the
existing `celery_app` (broker already `redis://…/1`). The asyncio `runner` is
deleted; `jobs.py` and the domain services are unchanged. This is the reversible
seam.

### 2. Periodic jobs

V1 runs **exactly one scheduler process** (single-instance assumption — stated and
acceptable for local-first / single-VM Phase 1). Concurrency safety is therefore
provided by *idempotent, status-gated* claim queries; for forward-compat with the
Celery/multi-worker prod path, the outbox claim **additionally** uses
`FOR UPDATE SKIP LOCKED` on PostgreSQL (applied only when
`session.bind.dialect.name == "postgresql"`, so SQLite unit tests skip it).

| Job | Cadence | Action | Idempotency (at-least-once safe) | Concurrency safety |
| --- | --- | --- | --- | --- |
| `outbox.drain` | every **15s** | `dispatch_service.process_outbox(session, limit=50)` | Only `status='pending'` rows are claimed; terminal states (`sent`/`failed`/`skipped`/`dead`) are never reprocessed; `dedupe_key` prevents duplicate enqueue upstream | Single-instance + status gate; PG-only `with_for_update(skip_locked=True)` on the claim select for prod-readiness |
| `reveal.expire_sweep` | every **5 min** | new `reveal_service.sweep_expired(session)`: `UPDATE application_reveal_request SET status='expired', responded_at=now() WHERE status='pending' AND expires_at <= now()` | Re-running after the sweep finds no `pending`-and-overdue rows → no-op; setting an already-expired row is idempotent | Single-instance + status/`expires_at` gate; a row only transitions out of `pending` once |
| `opportunities.deadline_close` | every **10 min** | new `job_service.sweep_deadline_closures(session)`: for `status='active' AND application_deadline IS NOT NULL AND application_deadline <= now()` apply the existing `active → closed` transition, remove from listings, enqueue partner + saved-student notifications | Already-`closed` jobs are excluded by the `status='active'` gate; notifications are deduped via `dedupe_key=f"job.auto_closed:{job_id}"` | Single-instance + status/deadline gate |

**Reveal re-request bug fix (required companion change, not part of the sweep):**
after the sweep moves a stale row to `expired`, `request_reveal` must allow a
**new** request when the org's prior request is terminal-non-accepted. Change
`request_reveal`: keep idempotent return only while `existing.status == PENDING`;
for `existing.status in {EXPIRED, DECLINED}` **allow a fresh request** (insert a
new row) instead of raising `already_requested`; keep `already_requested` only for
an in-flight `PENDING` (now impossible to be stale because the sweep retires it)
and `ACCEPTED` (already revealed → `already_revealed`). This restores the
documented "partner may re-request after expiry" rule.

**Auto-close target state (doc conflict resolved):** `BUSINESS_LOGIC.md` §2.2 says
deadline auto-close sets `status = CLOSED`; `opportunities/domain/lifecycle.py`
comments that the worker sets `expired`. **Decision: deadline auto-close uses
`active → closed`** (the existing transition + the existing "Tin đã đóng" partner
copy), per source-of-truth precedence (business rule > code comment). The
`expired` state is left unused in V1; flag the lifecycle.py comment as stale for
reconciliation. (Reusing `close` avoids inventing a new transition + relist copy.)

### 3. Outbox robustness contract

Current `process_outbox` (a) does **not** catch adapter `send()` exceptions — a
single SMTP error rolls back the whole batch — and (b) has no retry/backoff or
dead-letter, so a transient failure either loses the batch or (if forced to
`failed`) silently drops the email. Fix the contract:

- **Permanent failures stay terminal `failed`** (no retry): `TEMPLATE_NOT_FOUND`,
  `TEMPLATE_VARIABLE_ERROR` (current behavior — keep).
- **Transient send failures retry with backoff:** wrap `adapter.send(...)` in
  `try/except`. On failure, **do not** set `sent`; keep `status='pending'`,
  increment `attempts`, set `error_code='SEND_FAILED'`, and set
  `next_attempt_at = now() + backoff(attempts)` where
  `backoff = min(BASE * 2**(attempts-1), CAP)` (BASE=60s, CAP=1h).
- **Dead-letter terminal state:** when `attempts >= MAX_ATTEMPTS` (config, default
  **5**), set `status='dead'` (terminal; never reclaimed). `dead` is added to the
  status vocabulary `pending|sent|failed|skipped|dead`.
- **Claim query gains a time gate:**
  `WHERE status='pending' AND (next_attempt_at IS NULL OR next_attempt_at <= now())`.

**Migration needed? YES — one migration `0011_outbox_retry_backoff`.**

| Table | Column | Type | Notes |
| --- | --- | --- | --- |
| `notification_outbox` | `next_attempt_at` | `TIMESTAMPTZ NULL` | NULL = eligible immediately; set on transient failure |

- `status` widens its value set to include `dead` (column is `String(20)` with no
  DB enum/check, so **no DDL** for the value — code/comment change only).
- `attempts` and `error_code` already exist — reused, no change.
- Migration must include `upgrade` (add column) **and** `downgrade` (drop column).
- Add partial index `idx_outbox_due` on `(status, next_attempt_at)` for the claim.

### 4. Config + run command

- Env flag (reuse existing): `BACKGROUND_WORKER_MODE`. New accepted value
  **`scheduler`** alongside `inline`. `app.worker` refuses to start unless mode is
  `scheduler`. Default stays **`inline`** (settings default, and all tests), so the
  scheduler is **off by default** and the inline path is unchanged.
- New optional settings (defaults given): `outbox_max_attempts=5`,
  `scheduler_base_tick_seconds=15`.
- **Documented local run command** (separate terminal, alongside API):
  ```bash
  cd backend && BACKGROUND_WORKER_MODE=scheduler uv run python -m app.worker
  ```
- **Off in tests:** the test settings keep `background_worker_mode='inline'`; the
  pytest harness never spawns `app.worker` and the FastAPI lifespan never starts
  the loop. Tests exercise scheduling only through the `tick()`/job-registry
  entrypoint (see §5), never a live loop.

### 5. Test strategy (SQLite, no direct service call)

Goal: prove each scheduled job *as scheduled* without a test calling the domain
function directly — the test calls the scheduler's single-tick entrypoint and
asserts the side effect.

- **Entrypoint under test:** `scheduler.runner.tick(now)` runs all due jobs once
  against an injected session factory and returns `{job_name: result}`. Tests call
  `tick()` (or `runner.run_job("outbox.drain")` for isolation) — never
  `process_outbox`/`sweep_*` directly.
- `outbox.drain`: seed an active template + a `pending` outbox row → `await
  tick(now)` → assert row `status='sent'`, `sent_at` set, console adapter captured
  the message. Second `tick` → no change (idempotent).
- **Retry/dead-letter:** inject a stub adapter that raises → `tick` → assert row
  still `pending`, `attempts==1`, `next_attempt_at` in the future. Drive `tick`
  with a forced `now` past `next_attempt_at` for 5 attempts → assert `status='dead'`.
- `reveal.expire_sweep`: seed a `pending` reveal with `expires_at` in the past →
  `tick(now)` → assert `status='expired'`. Then call `request_reveal` for the same
  org → assert a **new** pending row is created (re-request bug regression test).
- `opportunities.deadline_close`: seed an `active` job with
  `application_deadline` in the past → `tick(now)` → assert `status='closed'` and a
  partner notification outbox row exists with `dedupe_key='job.auto_closed:{id}'`.
  Second `tick` → no duplicate notification.
- All run on the SQLite unit path; the PG-only `skip_locked` branch is dialect-
  guarded so it is inert under SQLite.

## Consequences

- **Positive:** emails actually send; reveals expire and become re-requestable;
  expired jobs leave listings — all three live bugs closed. Zero new runtime deps;
  one documented command; scheduler fully decoupled from the API (safe to scale the
  API to N Uvicorn workers without N schedulers). The `jobs.py` registry is the
  clean seam to Celery beat in production with no domain-code change.
- **Cost / limits:** V1 assumes **one** scheduler process — running two would
  double-process the non-`skip_locked` jobs (reveal/job sweeps are idempotent so
  this is safe-but-wasteful; outbox is protected on PG). Documented as a single-
  instance assumption to retire at the Celery migration. One small migration
  (`0011`) and a `dead` state added to the outbox vocabulary.
- **Reversibility:** delete `runner.py` + flip `jobs.py` registration to Celery
  beat; no API or domain-service signature changes.

## Implementation checklist (next backend slice)

1. Migration `0011_outbox_retry_backoff`: add `notification_outbox.next_attempt_at`
   (`TIMESTAMPTZ NULL`) + `idx_outbox_due (status, next_attempt_at)`; upgrade +
   downgrade. Add `next_attempt_at` to the ORM model.
2. `dispatch_service.process_outbox`: wrap `adapter.send` in try/except; implement
   backoff (`next_attempt_at`), `MAX_ATTEMPTS` dead-letter (`status='dead'`), and
   the `next_attempt_at` claim gate + PG `with_for_update(skip_locked=True)`.
3. `recruitment/application/reveal_service.py`: add `sweep_expired(session)`; fix
   `request_reveal` to allow re-request when the org's prior request is
   `expired`/`declined`.
4. `opportunities/application/job_service.py`: add `sweep_deadline_closures(session)`
   reusing the `close` transition + partner/saved-student notifications (deduped).
5. `automation/scheduler/jobs.py` (registry) + `runner.py` (`tick` + `run_forever`)
   + `app/worker.py` entrypoint guarded on `BACKGROUND_WORKER_MODE='scheduler'`.
6. Config: accept `background_worker_mode='scheduler'`; add `outbox_max_attempts`,
   `scheduler_base_tick_seconds`; update `backend/.env.example`.
7. Tests per §5 (SQLite) for all three jobs + retry/dead-letter + reveal
   re-request regression.
8. Docs: update `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` §7 (retry/dead-letter
   states), `docs/LOCAL_DEV_STACK.md` (run command), reconcile the stale
   `opportunities/domain/lifecycle.py` `expired` comment.
