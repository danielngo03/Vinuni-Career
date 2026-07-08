# Platform Admin Console — Program Design Spec

- **Date:** 2026-07-07
- **Status:** Approved direction (brainstorming), pending spec review
- **Owner persona:** Platform Superadmin (primary) + University Governance (secondary, existing workspace upgraded separately)
- **Scope type:** Multi-phase program. This is the master spec. Each phase (P1–P7) gets its own detailed design spec + implementation plan before it is built. P0+P1 detail lives in `2026-07-07-admin-p0-p1-ai-operations-design.md`.

## 1. Problem & Intent

The platform has grown many operator surfaces (24 admin screens under the `(university)` workspace, ~13 API-wired) but lacks a coherent **platform-operations control plane** for a superadmin running a large system. Concretely missing today:

1. **AI observability & cost** — Langfuse keys exist in `backend/.env` but **zero integration code**; `ai_usage_log` is coarse (char-buckets, no org/provider/latency/trace_id); no operator dashboard for spend vs budget, reliability, or volume.
2. **Audit log viewer** — `AuditLog` table captures before/after for every write, but there is **no UI to read it**.
3. **System health / queue monitoring** — Celery scheduler runs ~15 jobs; no visibility into queue depth, last-run, or failures.
4. **Users & access** — only suspend/unsuspend; no session revoke, no impersonation, no user-360.
5. **Feature flags** — only hardcoded booleans in `AiSettings`; no registry.
6. **Analytics depth & export** — KPI + one hand-drawn trend only.
7. **Alerts & incidents** — none.

**Intent:** build a dedicated, beautiful, high-signal **Platform Admin Console** that feels like a real large-system control plane (Vercel/Datadog/Stripe-dashboard class), grounded in the existing design system and backend patterns, delivered in verified phases.

## 2. Architecture Overview

### 2.1 Placement & boundary
- **New frontend route group:** `frontend/src/app/[locale]/(admin)/admin/*` with its own `WorkspaceShell` instance and nav config. Separate from `(university)`.
- **RBAC:** the console is **superadmin-only** at the shell (route guard) AND at every service call (`principal.is_superadmin`), never router-only. University-scoped admin stays in `(university)`; a few read models (e.g. AI settings) are shared but gated by org-type as today.
- **Backend:** each section maps to an existing or new module under `backend/app/modules/` (or `app/ai/observability` for AI ops), exposing `/admin/...` routes. No cross-module DB reads; use application-layer facades / read models, following the existing `safe()`-wrapped read-model pattern.

### 2.2 Cross-cutting principles (non-negotiable)
- **Extend, don't rebuild.** AI ops instruments the existing `AiTaskRunner` chokepoint and reuses `cost_estimator`/`budget_guard`/circuit breaker; it adds a **separate admin-only `ai_ops_event`** table (+ `ai_usage_daily` rollup, `ai_model_price`) and leaves the PII-safe `ai_usage_log` unchanged. Audit console reads existing `AuditLog`.
- **Service-layer RBAC + audit on every write** (existing repo pattern via `PermissionChecker.require` + `write_audit`).
- **DB is the source of truth for cost/budget; Langfuse is best-effort trace/eval.** Telemetry failure must never fail a user request.
- **No prompt/response text or secrets, ever.** Neither `ai_ops_event` nor Langfuse stores prompt/response bodies, API keys, or base URLs. Provider/model identity + tokens/latency are **platform-superadmin-only**, never exposed to end users or org-scoped university admins — owner override recorded in `AI_PRODUCT_SPEC §5.6` / ADR-0011.2.
- **No fake dashboards.** Every panel is real-API-wired with skeleton / empty / error / permission states.
- **Consequential actions require human confirmation + audit:** impersonation, session revoke, moderation override, kill switch, key rotation, budget change.

## 3. Information Architecture (the console)

Sidebar nav groups (mirrors the existing `nav.ts` accordion idiom):

```
Platform Admin
├─ Overview                     (P0)  system-wide landing
├─ AI Operations                (P1)
│  ├─ Overview (spend/reliability/volume)
│  ├─ Traces (Langfuse explorer)
│  ├─ Models & Pricing
│  └─ Settings (providers/aliases/kill switch — moved in)
├─ Audit Log                    (P2)
├─ System Health                (P3)
│  ├─ Queues & Jobs
│  └─ Services (DB/Redis/outbox)
├─ Users & Access               (P4)
│  ├─ Users (360 / suspend / sessions / impersonate)
│  └─ Roles & Permissions
├─ Feature Flags & Config       (P5)
├─ Analytics                    (P6)
└─ Alerts & Incidents           (P7)
```

## 4. UI/UX Conventions (grounded in the real design system)

Reference implementations: `components/dashboards/university-dashboard.tsx`, `components/university/partner-review-screen.tsx`, `components/analytics/partner-analytics-screen.tsx`. Design tokens: `app/globals.css` (v9 Monochrome). Primitives: `components/ui/*` (custom Tailwind v4 — **not shadcn**).

### 4.1 Layout skeleton per screen
Every console screen follows this vertical rhythm (matches university-dashboard idiom):

1. **PageHeader** — title, one-line context, primary action(s) on the right (e.g. "Export", "Refresh", "Rotate keys").
2. **Filter/Control bar** — `SegmentedControl` for status/time-range, `Select` for scoped filters, search `Input`. Sticky on scroll for long tables.
3. **Metric tiles** — 4-column responsive grid (`lg:grid-cols-4`) of `.marketplace-card` stat tiles with icon-chip, big number (JetBrains Mono), delta badge (`StatusBadge` tonal), and a one-line `hotNote`. Collapses to 2-col / 1-col below breakpoints.
4. **Primary visualization** — see §4.2.
5. **Data region** — `DataTable` (with skeleton + empty states built in) or a 3-column ops grid of queue cards.
6. **Detail drill-in** — `Sheet` (side drawer) for a single record (audit entry, user 360, trace, job run), never a full page navigation for a row.

### 4.2 Which visualization where (explicit, per the request)

| Surface | Component idiom | Why |
|---|---|---|
| **KPI / counters** (spend today, error rate, queue depth, active users) | Metric tile grid + delta badge | Scannable at a glance; the operator's "is anything on fire" band |
| **Time-series** (spend over 30d, request volume, latency trend) | Lightweight **div/CSS bar + sparkline** (existing hand-drawn pattern) for v1; introduce a tiny inline SVG line renderer as a shared `<Sparkline/>` / `<BarSeries/>` primitive. **No heavy chart lib** unless a later phase justifies it. | Keeps bundle small, matches current idiom, avoids a 100kb+ dependency for simple series |
| **Distributions** (spend by feature/model, volume by provider) | Horizontal stacked bars + legend (partner-analytics funnel pattern) | Compares parts-of-whole without a chart lib |
| **Tabular records** (audit log, usage events, users, job runs) | `DataTable` + cursor pagination + column-level `StatusBadge`; **virtualized rows** when >200 loaded | Dense, sortable, familiar; virtualization keeps render fast |
| **Single record** (audit entry before/after, user 360, trace) | `Sheet` drawer with `Tabs` | Deep detail without losing list context |
| **Routing / workflow config** (AI routing graph, later flow builders) | **Canvas / node editor** (existing `routing-canvas-screen.tsx` idiom) — drag nodes, connect, dry-run | Config that is inherently a graph should be edited as a graph, not a form |
| **Config toggles** (feature flags, kill switch, budgets) | `Switch` + labeled rows in cards; staged-rollout uses a `SegmentedControl` (off / % / on) | Direct manipulation, immediate feedback |
| **Live feeds** (incidents, recent errors, queue events) | Reverse-chronological list with tonal left-border rows, auto-refresh | Operator watches the newest first |

### 4.3 Realtime & refresh strategy (explicit)
No WebSocket infra exists today (only SSE for AI chat). Strategy by tier:

- **Tier A — near-realtime (poll 5–10s, pause when tab hidden):** System Health queue depth, AI live-spend counter, Alerts/Incidents feed. Use React Query `refetchInterval` gated on `document.visibilityState`. Consider an SSE endpoint later only if polling proves insufficient.
- **Tier B — periodic (poll 30–60s):** Overview metric tiles, AI ops overview, moderation counts.
- **Tier C — on-demand (manual refetch / on filter change):** Audit log, analytics drill-down, config screens, trace explorer.

Never poll heavy aggregate queries directly — poll **pre-aggregated rollup tables / read models** only.

### 4.4 Rendering performance rules
- **Server-side pre-aggregation:** dashboards read rollup tables (`ai_usage_daily`) and `safe()`-wrapped read models, never live multi-domain joins on the request path.
- **Cursor pagination** for all logs/events; **virtualized** `DataTable` bodies for large sets.
- **Skeleton-first**: every panel renders its skeleton immediately; data streams in per-widget (independent React Query keys) so one slow widget never blocks the page.
- **Prefetch on hover / route intent** for drill-ins; cache with sensible `staleTime` per tier.
- **Code-split** the `(admin)` route group so it never ships in the student/partner bundles.
- **Debounce** search/filter inputs (250ms) before firing queries.

### 4.5 Visual language
v9 Monochrome only: ink `#171717` as the single action color, full gray ramp for hierarchy, semantic hues reserved for meaning — teal `#059669` = healthy/success, amber `#d97706` = warning/pending/paid, red `#c83538` = error/destructive. Metrics use JetBrains Mono. Cards are `.marketplace-card` (1px border, subtle shadow, no gradients). Icon-chips (`icon-chip-*`) for section headers. Light + dark themes. i18n: next-intl, vi/en parity, new namespace `messages/{locale}/admin/*.json`.

## 5. Phase Plan (each phase = own detailed spec → plan → implement → verify)

| Phase | Deliverable | Backend basis | Risk |
|---|---|---|---|
| **P0** | Console shell: `(admin)` route group, nav, superadmin guard, Overview landing (aggregates existing read models), move AI Settings in | new shell; reuse dashboards read models | low |
| **P1** ⭐ | AI Operations + admin `ai_ops_event` telemetry + Langfuse + per-org budget | instrument `AiTaskRunner`; new `ai_ops_event`/`ai_usage_daily`/`ai_model_price`; keep `ai_usage_log` PII-safe; reuse `cost_estimator`/`budget_guard`; owner override §5.6 | med |
| **P2** | Audit & Activity Log console (filters, actor timeline, resource history, CSV export) | read existing `AuditLog` + `audit_log_service` | low |
| **P3** | System Health: Celery queue/job visibility, outbox health, readiness, error feed | new inspector endpoints over Celery + existing probes/outbox | med |
| **P4** | Users & Access: user-360, session list/revoke, impersonation (audited), RBAC editor | extend `users`, `auth` sessions, `organization` rbac | **high (security)** |
| **P5** | Feature Flags & Config registry + staged rollout | new `platform_settings` flag registry | med |
| **P6** | Analytics depth + export (funnels, cohorts, growth) | extend `analytics`/`dashboards` read models | med |
| **P7** | Alerts & Incidents: threshold rules → email + in-app, incident log | new module + notification outbox reuse | med |

Sequencing rationale: P1 is highest value and answers the Langfuse question; P2 is cheap (data exists); P3 hardens operations; P4 is gated behind a mandatory security review; P5–P7 layer on governance and proactivity.

## 6. Per-section design intent (high level; detailed specs later)

- **Overview (P0):** operator landing — a top "system status" band (AI spend vs budget, AI error rate, queue health, outbox health, moderation pending, active users), an incidents strip, and a next-actions rail deep-linking into sections. Reuses `university-dashboard` composition.
- **AI Operations (P1):** see detailed spec. Four analytical panels (Spend/Budget, Reliability, Volume, Traces) + Models & Pricing table + absorbed AI Settings.
- **Audit Log (P2):** full-width `DataTable` with filters (actor, action, resource_type, time range); row → `Sheet` showing before/after JSON diff (highlighted add/remove); "actor timeline" and "resource history" views; CSV export via `apiDownload`.
- **System Health (P3):** Queues & Jobs tab (per-scheduled-job card: last run, duration, status, next run; Celery queue depth tiles; failed-task feed with requeue), Services tab (DB/Redis readiness, outbox health with dead-letter requeue — extends existing support-console outbox view).
- **Users & Access (P4):** user search → user-360 `Sheet`/page (identity, orgs/roles, activity, sessions, AI usage, moderation flags); actions: suspend/ban, **revoke session**, **impersonate** (time-boxed, banner in impersonated session, full audit), reset. Roles & Permissions editor reuses `organization` rbac endpoints with permission-preview.
- **Feature Flags & Config (P5):** flag registry table (key, description, state off/%/on, environments, owner, updated_by); staged rollout via `SegmentedControl`; audit on every change; typed flag evaluation service on the backend so flags are read consistently (replaces hardcoded `AiSettings` booleans over time).
- **Analytics (P6):** cross-platform funnels (guest→apply, post→hire), cohort retention, growth tiles; server-side read models; CSV/JSON export.
- **Alerts & Incidents (P7):** rule editor (metric, threshold, window, channel); evaluation job on the scheduler; incidents list with ack/resolve; delivery via existing notification outbox (email + in-app).

## 7. Testing & acceptance (program-level)
- Every phase: unit (services), integration (RBAC superadmin-only, read models, mutations + audit rows), and a browser-verified pass per `docs/UI_QUALITY_BAR.md`.
- Security-sensitive phases (P1 keys/budget, P4 impersonation/sessions) require `vinuni-security-review` before merge.
- Backend gates green (`ruff`, `mypy`) and frontend typecheck/build green per phase.
- Status tracked in `docs/IMPLEMENTATION_STATUS.md` with `implemented / API wired / browser verified / E2E verified` per screen.

## 8. Out of scope (this program)
- University workspace redesign (tracked separately; only shared read models touched).
- Payment gateway work (manual/bank-transfer default stands).
- Replacing Langfuse or adding a full metrics/tracing backend (Prometheus/OTel) — deferred; app-level structured logging + DB ledger + Langfuse cover current needs.

## 9. Open questions
- Impersonation policy: max duration, which actions are blocked while impersonating, and whether it is superadmin-only (assumed: 30-min box, write-actions audited with `impersonated_by`, superadmin-only). Confirm in P4 spec.
- Alert channels beyond email + in-app (Slack/webhook) — assumed later phase.
