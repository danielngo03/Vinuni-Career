# Product Operating Model — VinUni Career Platform

> Updated: 2026-07-08  
> Purpose: product-management source of truth for AI usage accounting, billing
> entitlements, university admin limits, advertising/events monetization, and
> persona dashboard quality. Use with `PRODUCT_REQUIREMENTS.md`,
> `BUSINESS_LOGIC.md`, `AI_PRODUCT_SPEC.md`, `DESIGN.md`, and
> `SCREEN_SPECS.md`.

## 1. Product Position

VinUni Career Platform is a career operating system for a university, not a
generic job board. The product has four operating surfaces:

- **Public marketplace:** jobs, companies, events, search, recommendations,
  sponsored/curated inventory, and login-gated actions.
- **Student command center:** CV-first career actions, job fit, applications,
  events, interviews, AI support, and subscription/credit usage.
- **Partner recruiting OS:** jobs, pipeline, candidates, events, ads, team RBAC,
  analytics, package usage, and billing.
- **University operations center:** moderation, partner governance, workflow
  automation, career outcomes, AI/cost operations, support/privacy/abuse, and
  institutional reports.

All features must answer a real workflow question:

- What decision does this screen help the user make?
- What queue, list, chart, or editor does the user act on?
- What data is real, missing, stale, low-signal, or permission-gated?
- What happens on empty, error, offline, quota-exhausted, and approval states?

## 2. Current Reality Snapshot

As of 2026-07-08, the repo already contains substantial backend/frontend
surface area: jobs, CVs, CV-JD fit, advertising placements/creatives, events,
workflow, AI settings/ops, billing, dashboards, moderation, platform admin,
and persona shells.

The biggest product/accounting gap is not "no quota exists"; it is that quota
is not yet a universal AI entitlement ledger:

- `ai_assistant.application.usage_service` counts DB rows in `ai_usage_log` for
  daily/weekly user request meters and gates.
- `AiTaskRunner` writes `ai_usage_log`, `ai_ops_event`, and `ai_usage_daily`
  for calls that go through it.
- Several AI helpers still call providers through `generate_json_note`,
  `get_provider`, `get_provider_for_alias`, embedding/rerank helpers, or
  semantic/translation helpers. Some of these only call the sync logger
  `log_ai_usage()` and may not create the DB rows that user/org quota reads.
- Therefore a model call can be operationally logged but not reliably counted
  against the correct student, partner org, university budget, feature, and
  billing entitlement.

This must be fixed before AI credits, plan upgrades, or enterprise budget
controls are treated as production-ready.

## 3. AI Accounting Model

AI accounting has three separate layers. Do not collapse them into one meter.

| Layer | Owner | Purpose | User-facing behavior |
|---|---|---|---|
| Provider cost budget | Superadmin/platform admin, with masked university budget views where needed | Prevent runaway provider spend and monitor reliability | Superadmin sees provider/model ops; everyone else sees only masked budget/status |
| Billable entitlements / credits | Student plan or partner org package | Monetization and fair usage | Student/partner sees credit/package usage and upgrade/request actions |
| Abuse/rate throttles | Platform policy | Stop spam, loops, or accidental bursts | Clear retry/cooldown message; not an upsell by default |

### 3.1 Ledger Contract

Every billable AI call must create a durable usage ledger entry, even if the
provider telemetry also writes `ai_usage_log` or `ai_ops_event`.

Minimum fields:

```text
id
created_at
actor_user_id
actor_persona
org_id
billing_scope: user | org | department | platform
feature_key: chatbot | jd_extraction | cv_fit_explanation | ...
task_type: internal AI task name
resource_type/resource_id
session_id
idempotency_key
units_charged
provider_cost_usd
result_status: success | provider_failed | validation_failed | cached | blocked
ai_usage_log_id / ai_ops_event_id (nullable links)
```

The ledger is the source for plan/package limits. `ai_usage_log` remains the
PII-safe AI call log; `ai_ops_event` remains the superadmin operations log.

### 3.2 Charging Rules

Do not charge user/partner credits for:

- deterministic parsing, deterministic scoring, local OCR, local validation,
  local filtering, local ranking, or rule-based moderation;
- validation failures before a model call;
- cache hits or reused explanations for the same resource/version;
- provider failures that produce no useful user-visible output;
- university/system safety checks that are internal governance only.

Do count internal provider cost for:

- any real provider call that consumed tokens or vision/embedding capacity,
  even when the user is not charged credits;
- failed provider calls when the provider reports usage;
- background/system jobs attributed to a department/org/platform budget.

Charge credits only after a successful, user-visible AI output or a configured
billable background result.

### 3.3 Billable AI Task Taxonomy

| Persona | Task | Charging policy |
|---|---|---|
| Student | AI assistant chat turn | Charge per completed assistant turn; session/day/week throttles still apply |
| Student | CV upload extraction | Free for native text/local OCR; charge only for vision-LLM or text-LLM structuring that succeeds |
| Student | CV draft/fill/rewrite/bullets/canvas edit | Charge per generated suggestion/diff, not per accepted edit |
| Student | CV-JD fit | Deterministic score is free; AI explanation/improvement suggestions charge once per `(cv_version, job_version)` and then cache |
| Student | Cover letter/interview simulation/learning gap plan | Charge on successful generated output |
| Partner | JD upload extraction | Free for native text/local parser; charge package credits when AI fallback succeeds |
| Partner | JD writer, bias rewrite, outreach draft | Charge per generated draft/suggestion |
| Partner | Screening brief, scorecard suggestion, candidate matching narrative | Charge org package credits; RBAC-gated and audit-backed |
| Partner | Advertising creative assistant | Charge only for AI-generated copy/variants, not manual campaign setup |
| University | Moderation/fraud/market intelligence/AI workflow nodes | Charged to university/platform/department budgets, not to upgrade packages |
| System | Embeddings, rerank, scheduled summaries | Charged to platform/org budget unless explicitly tied to a paid feature |

### 3.4 Persona Policy

**Students**

- Students can upgrade plans or buy/add AI credit packs if enabled.
- Credit exhaustion should show upgrade/buy/request-more actions.
- Daily/weekly/session throttles still protect abuse even if credits remain.
- Fit scoring basics and deterministic application safety must not disappear
  just because AI credits are exhausted.

**Partners**

- Partner usage is org-scoped. Package entitlements control job posts, featured
  slots, candidate access, passive search, email/outreach, ads, and AI credits.
- Partner admins can allocate team quotas by user/role/department where useful.
- Exhaustion routes to billing/package upgrade, not to university admin by
  default, unless the org is on a manually managed enterprise contract.

**University**

- University users do not see "upgrade plan" CTAs for AI usage because the
  platform belongs to the university.
- Superadmins configure platform, org, department, workflow, and user limits.
- Staff exhaustion should say "request more from admin" or route to an internal
  approval/workflow, not to billing.
- Real provider/model identity and provider/model registry CRUD are
  superadmin-only. Ordinary university staff may see masked budget/usage status
  if granted, but never concrete provider/model names or ids.

### 3.5 Required Architecture Change

All real provider calls must go through one usage-aware path:

```text
UsageContext(principal, org_id, feature_key, resource, session_id, billing_scope)
  -> preflight entitlement + budget + throttle check
  -> model call through AiTaskRunner or a UsageTrackedAiClient
  -> output guard
  -> durable ledger write with idempotency
  -> user-safe response
```

Direct provider calls in domain/application code are allowed only for pure
offline tests or deterministic adapters. If a helper cannot accept
`AsyncSession`, `Principal`, `org_id`, and `feature_key`, it cannot be the final
production path for a billable AI feature.

## 4. Advertising And Sponsored Business Model

Advertising is a real partner monetization workflow, not a static sponsored
badge.

Campaign objectives:

- promote one or more job posts;
- promote an employer/company profile;
- promote a partner event or career fair presence;
- promote a university-curated strategic partner spotlight.

Targeting modes:

- **Automatic:** platform allocates to eligible inventory using relevance,
  pacing, budget, frequency cap, and fairness constraints.
- **Manual:** partner selects location/region, industry/category, role family,
  work mode, student segment, degree/major/year, event interest, and language.
- **University restricted:** university can block sensitive categories, cap
  exposure, or require manual review.

Approval workflow:

- Partner submits campaign + creative + target settings.
- University workflow trigger runs policy checks: disclosure, image dimensions,
  banned claims, off-platform contact, job/event/company status, budget/package.
- If rules pass, campaign can auto-approve only when the workflow explicitly
  allows it.
- Otherwise route to a named department, queue, or user with SLA and audit.
- Paid placements always retain `Sponsored`/`Quảng cáo` disclosure. University
  curated content is labeled differently and never mixed into paid reporting.

Core metrics:

- impressions, clicks, apply starts, registrations, saves, spend/credit usage,
  pacing, frequency, target coverage, creative rejection reasons.
- No third-party ad IDs, no raw PII targeting, no exact student identity export.

## 5. Events Product Gap

Events must become a first-class career surface:

- public event discovery with search, filters, capacity, location/online state;
- partner event creation with moderation and attendee management;
- university event creation for career fairs, workshops, mock interviews, and
  employer sessions;
- student registration, waitlist, reminders, check-in, cancellation/no-show;
- event recommendations based on privacy-safe interests and career goals;
- post-event analytics for university and partner organizers;
- sponsored/strategic event placements that follow the advertising policy.

AI can help draft event copy, extract agenda information, summarize attendee
feedback, and recommend audiences, but registration/approval/check-in remain
deterministic and auditable.

## 6. Dashboard Quality Model

Dashboards are not welcome pages plus KPI cards. Each persona dashboard needs
real operating views and the right visualization for the decision.

| Persona | Dashboard job | Required views | Good chart types |
|---|---|---|---|
| Student | Decide what career action to take next | CV readiness, best jobs, application timeline, interviews/events, AI credit state | timeline, progress rings, recommendation rail, fit distribution, calendar strip |
| Partner | Manage hiring operations and package ROI | job health, pipeline aging, interviews, scorecards, team activity, ads/events, quota/package usage | funnel, kanban summary, stacked bars, time series, aging heatmap, conversion table |
| University | Operate the marketplace and reduce risk | moderation SLA, partner health, outcomes, AI spend/reliability, workflow tasks, incidents | queue table, SLA heatmap, cohort trend, spend time series, funnel, incident timeline |
| Superadmin | Keep the platform healthy | API/jobs/workers/outbox/AI ops/users/access/feature flags | status matrix, p95 trend, error-rate line, queue depth, incident timeline |

Rules:

- Every metric must name its source and stale/error state.
- Aggregates must be backed by read models or safe server-side queries, not
  client-side multi-domain joins.
- Empty charts show useful recovery or low-signal copy; never fake numbers.
- Drilldown links must take the operator to the queue/list that explains the
  metric.
- Mobile dashboards prioritize queues and next actions over dense charts.

## 7. P0 Product Slices

1. **Universal AI usage ledger:** add billable usage table/facade, `UsageContext`,
   idempotency, and API summaries for user/org/admin scopes.
2. **Route all AI calls through the usage-aware path:** JD extraction, CV-JD
   semantic explanation, skill translation, scorecard/screening brief, cover
   letter, assistant, embedding/rerank, and workforce jobs.
3. **Persona quota UX:** student credit meter with upgrade/buy/request-more;
   partner org package meter with admin allocation; university admin budget
   controls with no upgrade CTA.
4. **Dashboard V2 contracts:** student/partner/university dashboards get
   queue-first layouts, read-model-backed charts, stale/error states, and
   drilldowns.
5. **Advertising campaign workflow:** campaign entities, targeting policy,
   creative moderation, workflow routing, pacing/frequency caps, and reporting.
6. **Events V2:** event discovery, organizer tools, reminders/check-in,
   analytics, sponsorship, and recommendation hooks.
