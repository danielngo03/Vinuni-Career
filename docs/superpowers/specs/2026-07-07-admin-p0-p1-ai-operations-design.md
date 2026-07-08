# P0 + P1 — Admin Console Shell + AI Operations & Cost Observability

- **Date:** 2026-07-07
- **Status:** Approved direction, pending spec review
- **Parent:** `2026-07-07-platform-admin-console-design.md`
- **Persona:** Platform Superadmin only

This spec details the first buildable slice: the console shell (P0) and AI Operations with cost ledger enrichment + Langfuse (P1). It **extends** the existing AI gateway/observability stack rather than rebuilding it.

## A. Grounding — what already exists (do not rebuild)

| Concern | Existing asset | File |
|---|---|---|
| Single LLM chokepoint | `AiTaskRunner.complete()/.stream()/.embed()` | `app/ai/gateway/task_runner.py` |
| Usage ledger | `AiUsageLog` (task_type, model_alias, success, char-buckets, user_id, session_id, cost_usd) | `app/ai/observability/models.py`, migration `0040_ai_usage_log` |
| Cost estimate | `estimate_cost_usd()` + hardcoded per-alias price table | `app/ai/observability/cost_estimator.py` |
| Budget enforcement | `budget_guard.check_async()` — 402 BUDGET_EXCEEDED, platform + per-user | `app/modules/ai_settings/application/budget_guard.py` |
| Provider resolution | `get_provider_for_alias()`, built-in routes | `app/ai/gateway/factory.py`, `runtime_config.py` |
| Circuit breaker + fallback | `_CircuitState`, `FallbackChainProvider` | `factory.py`, `fallback_chain.py` |
| AI settings admin | providers/aliases/kill switch/budget CRUD + audit | `app/modules/ai_settings/*` |
| Request id ctx | `request_id_ctx` | `app/core/logging.py` |
| Superadmin gate | `Principal.is_superadmin`, `get_current_auth` | `app/shared/permissions.py`, `app/modules/auth/api/deps.py` |

**Gaps P1 fills:** no org_id / real tokens / latency / provider+model / trace_id in ledger; no rollup table; price table is in code not DB; budget is not per-org; Langfuse is not wired.

## B. P0 — Console Shell

### B.1 Frontend
- New route group `frontend/src/app/[locale]/(admin)/admin/` with `layout.tsx` mounting `WorkspaceShell`. **Nav note (self-check fix):** `WORKSPACE_NAV_GROUPS` is keyed by `Persona`, and there is **no "admin" persona** — superadmin is a boolean flag on the user, not a persona. So the console uses a **dedicated `ADMIN_NAV_GROUPS` list** resolved by `is_superadmin`, not the persona map. Nav items here use `absolute: true` paths under `/admin/*`.
- **Route guard:** server-side check that the current principal `is_superadmin`; otherwise redirect to `/` (or a 403 screen). Client also hides the console from non-superadmins.
- **Overview page** `admin/page.tsx` → `PlatformOverviewScreen`: system status band (reuses existing dashboards read models + new AI ops summary), incidents strip (placeholder empty state until P7), next-actions rail deep-linking to sections that exist.
- New i18n namespace `messages/{locale}/admin/*.json` (en + vi parity).

### B.2 Backend
- New read model `GET /admin/overview` (superadmin-only) composing: AI spend-vs-budget summary (from P1 rollup), AI error rate (rollup), outbox health (existing), moderation pending count (existing), active users count (existing). Each sub-query `safe()`-wrapped with fallback.
- Move AI Settings surface into the console nav (same endpoints; new frontend location under `admin/ai-operations/settings`). The `(university)` AI settings entry is removed from that nav once the console is superadmin-reachable (university retains org-scoped AI settings if org-type=university — keep endpoint, adjust nav only).

### B.3 RBAC
- All `/admin/*` routes call a shared dependency `require_superadmin(principal)` that raises `PermissionDeniedError` unless `principal.is_superadmin`. No org-scoped bypass.

## C. P1 — AI Operations

### C.1 Data model changes

**Privacy reconciliation (owner decision 2026-07-08):** `AI_PRODUCT_SPEC §5.4/§9` forbids persisting provider name, model name, raw token counts, or raw latency in `ai_usage_log` (a deliberate PII-safe, end-user-protection invariant). We DO NOT mutate that table. Instead we add a **separate superadmin-only operational telemetry table** (`ai_ops_event`). Provider/model identity is readable only by platform superadmins in AI Operations, per ADR-0011.2; ordinary university staff never receive it even with `ai_settings:read`/`manage`. This keeps prompts/responses/keys out. `AI_PRODUCT_SPEC §5.4` records this override. `ai_usage_log` stays exactly as-is (still the PII-safe cost aggregate; budget guard keeps reading it).

**New table `ai_ops_event`** (admin-only; migration `00xx_ai_ops_event`, `down_revision = 0075_skill_translation_cache`):
- `id`, `created_at`.
- `task_type: str`, `alias: str` — mirror the usage-log grain.
- `provider: str | None`, `model: str | None` — concrete provider+model resolved at call time. **Platform-superadmin-only; never surfaced to students, partners, guests, ordinary university staff, exports, notifications, or non-superadmin logs.**
- `prompt_tokens: int | None`, `completion_tokens: int | None` — real token counts from provider `usage`.
- `latency_ms: int | None`.
- `status: str` default `"ok"` — one of `ok | error | fallback | blocked` (blocked = budget/guard rejection).
- `fallback_used: bool` default false; `circuit_open: bool` default false.
- `cost_usd: Numeric | None`; `unpriced: bool` default false (true when no price row matched).
- `org_id: UUID | None` (indexed), `user_id: UUID | None`, `session_id: UUID | None`, `request_id: str | None`, `langfuse_trace_id: str | None`.
- **No prompt/response text, ever.** Retention: configurable (default 90d), a scheduled prune job trims old rows (raw per-request ops data need not live forever; rollups persist).
- Indexes: (`created_at`), (`org_id`,`created_at`), (`task_type`,`created_at`), (`model`,`created_at`).

**New table `ai_model_price`** (admin-editable pricing; migration `00xx_ai_model_price`):
- `id`, `provider`, `model`, `input_usd_per_1k`, `output_usd_per_1k`, `active`, `updated_by`, `updated_at`, unique(`provider`,`model`).
- Seed from the current hardcoded `cost_estimator` table so behavior is unchanged on day one. `estimate_cost_usd()` is refactored to read `ai_model_price` (cached, with the code table as fallback) → sets `unpriced=true` when it falls back.

**New table `ai_usage_daily`** (rollup; migration `00xx_ai_usage_daily`):
- Grain: (`day` date, `feature`/task_type, `provider`, `model`, `org_id`). Columns: `requests`, `errors`, `fallbacks`, `blocked`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms_sum`, `latency_ms_count` (for avg), `p95_latency_ms` (approx via reservoir or recomputed nightly). Upsert idempotently on each event (`INSERT ... ON CONFLICT DO UPDATE`).
- Indexes on (`day`), (`org_id`,`day`), (`task_type`,`day`).

### C.2 Instrumentation (single chokepoint)
Inside `AiTaskRunner` (`complete`/`stream`/`embed`), after the provider call resolves (or errors), assemble one record and, in the observability write path (which **never raises** — existing contract: telemetry failure downgrades to a log, never breaks the AI call):
1. Keep the existing `log_ai_usage_async` write to `ai_usage_log` **unchanged** (PII-safe cost aggregate; budget guard depends on it).
2. Compute cost from `ai_model_price` (sets `unpriced`).
3. Write one **`ai_ops_event`** row (the enriched admin-only telemetry) **and** upsert `ai_usage_daily` from it.
4. Fire Langfuse trace (best-effort, §C.3); store returned `trace_id` on the `ai_ops_event` row (prefer create-trace-first so `langfuse_trace_id` is present on insert).

`org_id` and `request_id` are passed into `AiTaskRunner` at construction (add `org_id` param) sourced from the caller's `Principal` + `request_id_ctx.get()`. Callers that already pass `user_id`/`session_id` add `org_id` — a mechanical, low-risk change; missing `org_id` degrades to platform-level attribution.

### C.3 Langfuse integration
- New module `app/ai/observability/langfuse_client.py`: thin wrapper reading `LANGFUSE_SECRET_KEY/PUBLIC_KEY/BASE_URL` from settings.
- **No-op if keys absent** (dev/test): all methods become cheap no-ops; nothing imported at module top that hard-fails without keys.
- One trace per AI call with metadata: `feature/task_type`, `alias`, `provider`, `model` (owner-approved for the superadmin-only Langfuse project — no API keys, no base URLs), `org_id` (id only), `user_id` (id only), `request_id`, token counts, latency, status. **No prompt/response bodies**. The Langfuse project is superadmin-operated; provider/model identity must not be mirrored into any ordinary university, partner, student, export, or notification surface.
- **Best-effort & non-blocking:** wrap in try/except that logs a warning on failure; use the SDK's async/background flush so request latency is unaffected. Langfuse being down must never fail or slow the user request beyond a bounded timeout.
- Return `trace_id` for deep-linking from the console.

### C.4 Per-org budget
- Extend `budget_guard.check_async()` to also read today's `ai_usage_daily` for the caller's `org_id` and compare against a new optional `AiSettings.per_org_daily_budget_usd` (or a small `org_ai_budget` override table if per-org values needed). Platform + per-user checks remain. Same 402 `BUDGET_EXCEEDED` semantics; degrade silently on infra error (policy-only block). Blocked calls record a `status="blocked"` usage row for visibility.

### C.5 Admin API (superadmin-only, new router `app/modules/ai_ops` or `app/ai/observability/api`)
All under `/admin/ai-ops`, gated by `require_superadmin`:
- `GET /overview?range=today|7d|30d` → spend vs budget (today + range), error rate, p95 latency, total requests, top features/models. Reads `ai_usage_daily`.
- `GET /spend?range&groupBy=feature|model|provider|org` → time series + distribution.
- `GET /reliability?range&groupBy` → error rate, fallback rate, latency percentiles, current circuit-breaker states (from `factory` in-process state, exposed read-only).
- `GET /volume?range&groupBy` → request counts series + distribution + top consumers.
- `GET /events?cursor&filters` → paginated `ai_ops_event` rows (recent calls) with `langfuse_trace_id` for deep-linking. Endpoint is platform-superadmin-only; provider/model columns are never returned to non-superadmin callers. No prompt bodies.
- `GET /prices` / `POST /prices` / `PATCH /prices/{id}` → CRUD `ai_model_price` (audited via `write_audit`).
- Langfuse deep-link base URL exposed to the frontend via a config endpoint or env-derived setting (public base URL only).

### C.6 Frontend — AI Operations section
Route `admin/ai-operations/` with `Tabs`: **Overview · Traces · Models & Pricing · Settings**.

**Overview tab** (`AiOperationsOverviewScreen`), top-to-bottom per §4.1 of the master spec:
- Control bar: `SegmentedControl` time range (Today / 7d / 30d), optional org `Select`.
- Metric tiles (4-col): Spend today vs budget (with % burn + tonal badge: teal <70%, amber 70–90%, red >90%), Requests, Error rate, p95 latency.
- **Spend vs Budget** panel: `<BarSeries/>` daily spend for the range with a budget reference line; burn-down note; a "Kill switch" quick action linking to Settings (red, confirm dialog).
- **Reliability** panel: error-rate + latency-percentile mini series per top feature; a compact table of current **circuit-breaker states** (alias, state open/closed, failures, recovers-in) with tonal badges.
- **Volume** panel: horizontal stacked bars — requests by feature and by model — plus a "top consumers" list (org/feature).
- Each panel is an independent React Query key (skeleton-first, Tier B 30–60s poll, paused when tab hidden). `unpriced` models surface an amber "pricing missing" inline note.

**Traces tab** (`AiTracesScreen`): platform-superadmin-only `DataTable` of recent `ai_ops_event` rows (time, feature, provider/model, tokens, cost, latency, status badge). Row → `Sheet` with the record detail + a prominent "Open in Langfuse" external-link button built from the deep-link base + `langfuse_trace_id` (disabled with tooltip if no trace id). Cursor pagination, virtualized body.

**Models & Pricing tab** (`AiPricingScreen`): `DataTable` of `ai_model_price` rows; inline edit / add via `Sheet` form (provider, model, input/output USD per 1k, active). Save → mutation + toast + audit. Amber banner listing any models seen in usage with no price row (drives the operator to fill gaps).

**Settings tab**: the existing AI Settings surface (providers/aliases/rollout/kill switch/budget) relocated here, plus the new **per-org budget** control. Reuses existing `ai-settings` components/endpoints.

### C.7 Error handling
- Langfuse down / slow → warn-log, bounded timeout, request unaffected.
- Ledger/rollup write fails → warn-log, AI result still returned; a nightly reconcile job recomputes `ai_usage_daily` from `ai_usage_log` to correct drift.
- Model missing price → `unpriced=true`, cost best-effort, UI amber note.
- Non-superadmin hits `/admin/*` → 403; console route redirects.
- Empty ranges → empty states, never blank panels.

### C.8 Security / privacy
- Superadmin-only end to end (route + service). `ai_ops_event` reads, provider/model identity columns, price rows, health probes, and routing internals require platform superadmin. There is no org-scoped university permission that reveals raw identity.
- `ai_ops_event` and Langfuse store IDs + counts + cost + provider/model + latency — **no prompt/response text, no keys, no base URLs**. `ai_usage_log` remains fully PII-safe and untouched.
- Provider/model names admin-visible only; never leak to student/partner surfaces.
- Price changes, budget changes, kill switch, key rotation all audited.
- Langfuse metadata carries ids/counts only by default.

### C.9 Tests
- **Unit:** cost from `ai_model_price` (+ fallback → `unpriced`); `ai_usage_daily` upsert idempotence; budget guard reads platform + org + user rollups; Langfuse client no-ops without keys.
- **Integration:** an AI call through `AiTaskRunner` still writes the unchanged `ai_usage_log` row **and** one `ai_ops_event` row + upserts `ai_usage_daily`; blocked call records `status="blocked"`; `/admin/ai-ops/*` returns 403 for non-superadmin; `/events` masks provider/model to alias when `view_provider_identity` absent; price CRUD writes audit rows; reconcile job recomputes rollups; retention prune trims old `ai_ops_event`.
- **AI-safety:** assert no prompt/response text is persisted in `ai_usage_log` or `ai_ops_event` or sent to Langfuse; provider/model absent from any end-user response and absent from `ai_usage_log`.
- **Frontend:** each panel renders skeleton→data→empty→error; Langfuse deep-link built correctly / disabled when absent; typecheck + build green.

### C.10 Migrations & rollout
- Additive migrations only (new nullable columns + two new tables); no destructive changes. Seed `ai_model_price` from the current code table.
- Ship instrumentation behind graceful degradation so a missing Langfuse key or empty price table never breaks AI calls.
- Verify `ruff`, `mypy`, backend tests, frontend build; browser-verify the AI Operations screens before marking P1 done in `docs/IMPLEMENTATION_STATUS.md`.

## D. Acceptance (P0+P1)
- Superadmin can open `/admin`, see a real Overview, and navigate AI Operations.
- Every AI call produces an enriched ledger row + rollup update + (when keys present) a Langfuse trace deep-linkable from Traces.
- Spend vs Budget / Reliability / Volume panels show real data with correct empty/error states; per-org and platform budgets enforce.
- Models & Pricing is admin-editable and drives cost accuracy; unpriced models are surfaced.
- No PII/secret leakage; all sensitive writes audited; non-superadmin fully blocked.
