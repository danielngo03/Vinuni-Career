# Task Routing — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026  
> Purpose: deterministic routing for Claude Code. The main Claude session is the orchestrator unless Agent Teams are explicitly enabled.

## Operating Model

- Default: main session delegates to subagents, receives summaries, and synthesizes.
- Subagents do not directly message each other by default.
- Agent Teams are optional and experimental. Use only when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is enabled and the user asks for coordinated teammates.
- Parallel work is allowed only when file ownership and data dependencies are disjoint.
- Backend/frontend implementation starts only after product scope, architecture, and API/data contracts are stable.
- For manual multi-terminal execution, use `docs/CLAUDE_MULTI_AGENT_TASKS.md`
  as the copy-ready prompt runbook and keep workstreams separated by ownership.

## Source Routing

| Task Type | Lead Agent | Supporting Agents | Sequence |
|---|---|---|---|
| New product feature | `product-owner-system-planner` | domain agent, `system-architect` | PO scope → domain flow → architecture → implementation → QA |
| Product gap / improvement discovered while coding | `product-owner-system-planner` | relevant domain agent, `system-architect`, `tester-qa` | gap statement → scope decision → contract update/backlog → implement only if in-scope |
| Architecture/module boundary | `system-architect` | backend/data/AI as needed | architect → affected implementers → QA |
| Backend API/service/DB | `backend-developer` | `system-architect`, `data-engineer`, `ai-engineer` if relevant | architecture contract → backend → tests |
| Frontend/page/component | `frontend-developer` | domain agent, `tester-qa` | UX/domain → API contract → frontend → QA |
| Paused build / product drift review | main orchestrator | `product-owner-system-planner`, relevant domain agent, `system-architect`, `frontend-developer`, `ai-engineer` if relevant, `tester-qa` | `/review-snapshot` → findings → status/doc corrections → continuation prompt |
| Product/business/AI realism audit | main orchestrator | `product-owner-system-planner`, relevant domain agent, `system-architect`, `ai-engineer`, `data-engineer`, `tester-qa` | `/product-reality-audit` + `docs/PRODUCT_REALITY_REBUILD_SPEC.md` → practical gaps → adjacent-flow/data contracts → acceptance criteria → fast-slice prompts |
| Persona workspace/UI quality | `frontend-developer` | `product-owner-system-planner`, relevant domain agent, `tester-qa` | persona job-to-be-done → screen contract → UI implementation/review → browser QA |
| System acceptance / definition of done | `tester-qa` | PO, architect, backend, frontend, data, AI, security/domain agents as relevant | acceptance bar → gaps → fix plan → release gate decision |
| AI feature/prompt/tool | `ai-engineer` | backend, frontend, student/employer/university, QA | AI spec → backend tool/API → frontend UX → AI review → QA |
| Local scaffold/runtime/env | `system-architect` | backend, frontend, QA | local stack contract → scaffold → gates |
| Notifications/email/templates | `university-domain-agent` | architect, backend, frontend, AI if drafting, QA | governance → contracts → implementation → QA |
| Account/security/device settings | `system-architect` | student-domain, university-domain, backend, frontend, QA | privacy contract → backend/frontend → security QA |
| Analytics/projection/export | `data-engineer` | backend, university-domain, QA | data spec → backend/export → QA |
| University governance/RBAC/moderation | `university-domain-agent` | PO, architect, backend, frontend, QA | governance spec → architecture → implementation → QA |
| Employer/recruiter journey | `employer-domain-agent` | PO, architect, backend, frontend, QA | domain spec → contracts → implementation |
| Student journey/CV/applications/AI UX | `student-domain-agent` | PO, architect, backend, frontend, AI, QA | domain spec → contracts → implementation |
| Test plan/quality gate | `tester-qa` | affected agents | acceptance criteria → tests → gate report |
| Bug fix | responsible implementation agent | `tester-qa` | reproduce → fix → regression tests |

## Feature Workflows

### Partner RBAC

1. `product-owner-system-planner`: confirm backlog IDs and scope.
2. `system-architect`: confirm shared configurable RBAC model and tenancy.
3. `backend-developer`: implement organization models, services, APIs, migrations.
4. `frontend-developer`: role matrix, departments, invite/member UI.
5. `tester-qa`: authorization matrix, cross-tenant isolation, audit tests.

### Phase 0 Local Scaffold

1. `system-architect`: confirm local-first architecture, adapters, env, and no-Docker app runtime.
2. `backend-developer`: scaffold FastAPI, DB, local worker adapter, lightweight OCR/parser, offline AI provider.
3. `frontend-developer`: scaffold Next.js, i18n, shell, design tokens, settings placeholders.
4. `tester-qa`: local run gates, no real keys, parser fixtures, type/lint/build.

### Account, Device, And Security Settings

1. `student-domain-agent`: student settings UX, notification preference needs, privacy expectations.
2. `university-domain-agent`: staff TOTP/device policy and mandatory security alert governance.
3. `system-architect`: session/device/security event model and privacy boundaries.
4. `backend-developer`: account preferences, sessions, remote logout, security events APIs.
5. `frontend-developer`: settings UI, device list, remote logout modal, security events.
6. `tester-qa`: remote logout, safe metadata, locale override, RBAC/security tests.

### Notifications And Email Template Builder

1. `university-domain-agent`: category policy, mandatory vs optional notifications, broadcast governance.
2. `system-architect`: notification outbox, template versioning, preference filtering, idempotent dispatch.
3. `ai-engineer`: optional AI-assisted template draft rules and eval/safety guardrails.
4. `backend-developer`: notification APIs, template renderer, outbox worker, local email adapter.
5. `frontend-developer`: bell center, preference center, template editor with variables/preview.
6. `tester-qa`: preference filtering, variable validation, no real outbound email, i18n templates.

### AI Career Assistant

1. `ai-engineer`: tool registry, prompt boundaries, safety, eval plan.
2. `student-domain-agent`: student use cases and confirmation UX.
3. `system-architect`: streaming, tool execution, session storage, data access boundaries.
4. `backend-developer`: `ai_assistant` API, SSE, tool executor, audit.
5. `frontend-developer`: chat UI, tool cards, confirmation cards, auth gate.
6. `tester-qa`: adversarial prompts, provider leakage, write-action confirmation.

### CV Studio

1. `student-domain-agent`: CV-first creation modes, template marketplace,
   quota states, job-fit UX, and application snapshot expectations.
2. `product-owner-system-planner`: confirm phase scope, tier/quota rules, backlog IDs.
3. `system-architect`: documents/recruitment/ai boundaries, versioning, snapshot invariants.
4. `data-engineer`: CV schema, analytics events, export/audit field privacy.
5. `ai-engineer`: extraction, template-fill/rewrite/tailor/recommend tools,
   no-fabrication rules, job-fit score explanation, eval plan.
6. `backend-developer`: `documents` CV APIs, imports, quota enforcement,
   versions, exports, CV-to-job fit, application snapshot service.
7. `frontend-developer`: CV library/template marketplace, upload/import
   recovery, editor, A4 preview, diff viewer, job-fit panel, mobile tabs.
8. `tester-qa`: creation modes, quota reached, autosave, version restore,
   export, snapshot immutability, job-fit fallback, AI safety.

### Multi-Round Pipeline

1. `employer-domain-agent`: recruiter flow, stage UX, candidate visibility.
2. `system-architect`: state machine, invariants, audit, SLA worker.
3. `backend-developer`: recruitment/pipeline services and APIs.
4. `frontend-developer`: kanban, scorecards, rollback modal, SLA indicators.
5. `tester-qa`: transitions, rollback, concurrency, bulk actions, SLA.

### Events

1. `product-owner-system-planner`: confirm v1 payment default and ticketing scope.
2. `university-domain-agent`: approval, sponsor labels, governance.
3. `system-architect`: seats, locks, registration states, waitlist, payment adapter boundary.
4. `backend-developer`: event/ticket/check-in/waitlist/manual payment APIs.
5. `frontend-developer`: event detail, tickets, seat map, registration, QR.
6. `tester-qa`: seat lock, online link, waitlist, check-in, labels.

### Public Career Gateway + Sponsored Discovery

1. `product-owner-system-planner`: confirm public discovery scope, guest gating,
   recommendation/personalization scope, monetization/ads requirements, and
   phase priority. Must read `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`.
2. `student-domain-agent`: review guest/student journey, search intent, login
   preservation, and applying/saving/registering gates.
3. `employer-domain-agent`: review employer/company discovery, sponsored jobs,
   and partner value without misleading organic placement.
4. `university-domain-agent`: review VinUni trust, moderation, ad approval, and
   public governance.
5. `system-architect`: define public jobs/events/companies/ad contracts,
   discovery-session/recommendation/ad contracts, analytics events, and
   visibility/tenant/privacy rules.
6. `backend-developer`: implement public APIs and ad delivery only after the
   contracts are stable.
7. `frontend-developer`: build search-first public gateway, jobs/events/company
   surfaces, recommendation rails, login-gated actions, ad slots, and disclosure
   labels.
8. `tester-qa`: responsive/browser QA, fake-data audit, ad disclosure audit,
   recommendation-source audit, privacy-safe guest-session tests, and
   guest/auth/persona gating tests.

### Visual/Product Rescue

Use when functionally correct surfaces still look generic, under-built, or
misaligned with `docs/DESIGN_EXAMPLE.png`. This workflow is a rescue checkpoint,
not a permission to blindly code every visual idea.

1. `product-owner-system-planner`: confirm rescue scope, resolve tagline/default
   asset decisions, decide whether a new feature is in scope or backlog-only.
2. `frontend-developer` + `vinuni-ui-polish`: compare public/dashboards against
   `docs/DESIGN_EXAMPLE.png`, `docs/DESIGN.md`, and `docs/SCREEN_SPECS.md`.
3. `system-architect`: define missing API/data/media contracts before any
   backend/frontend implementation begins.
4. `data-engineer`: define seed data and projections for metrics/trends without
   fake counts or fake company claims.
5. `backend-developer`: implement only the stable contracts approved above
   (logo/media delivery, metric trend read models, saved jobs, events, etc.).
6. `frontend-developer`: rebuild composition with real assets/contracts and
   honest disabled states where backend is not ready.
7. `tester-qa`: screenshot/browser pass at 375/768/1024/1440 and status wording
   that separates functional verification from visual-design verification.

Required handoff before implementation:

- Visual target and screenshot checklist.
- Product decisions: tagline, default assets, student signed-in top-nav IA, what
  is demo seed vs real data.
- API/data contracts: `logo_url`, media delivery, metrics trends, saved jobs,
  event cards, ad placements.
- Security/privacy constraints: no raw paths, no fake logos, no hidden ads.
- Explicit out-of-scope items to add to backlog instead of coding now.

### Persona Workspace Quality Review

Use when a workspace looks generic, visually weak, or product experience feels
wrong.

1. `product-owner-system-planner`: define the real job-to-be-done and success
   criteria for the persona surface.
2. Relevant domain agent:
   - `student-domain-agent` for dashboard, CV, jobs, applications, events, AI.
   - `employer-domain-agent` for recruiting ops, pipeline, team, ads, events.
   - `university-domain-agent` for moderation, governance, outcomes, templates.
3. `frontend-developer`: map the job-to-be-done into IA, layout, states,
   responsive behavior, and component/data needs.
4. `system-architect` only if missing APIs/read models block the UI.
5. `tester-qa`: browser screenshots, responsive checks, fake-data audit, a11y,
   and E2E readiness.

### System Acceptance Review

Use before updating `IMPLEMENTATION_STATUS.md` to `complete`, or when a slice is
green locally but may still be weak as a product.

1. Main orchestrator reads `docs/SYSTEM_ACCEPTANCE_BAR.md`.
2. `product-owner-system-planner`: product/business fit.
3. `system-architect`: boundaries, API/data contracts, scalability.
4. `backend-developer`: service correctness, RBAC, audit, migrations.
5. `frontend-developer`: persona surface and browser evidence.
6. `ai-engineer`: AI safety/eval/fallback/cost if AI is involved.
7. `data-engineer`: read models, projections, analytics/export if involved.
8. `tester-qa`: final pass/fail, missing tests, residual risk.

### Product Gap Review

Use when Claude notices a missing feature, weak workflow, or better UX/business
logic that the user did not explicitly request.

Start with `docs/PRODUCT_REALITY_REBUILD_SPEC.md`. The gap review must check
whether a visible UI issue also implies backend, data, AI, notification, quota,
audit, seed, support, or admin-governance changes. Do not treat isolated UI
polish as complete when the underlying real workflow is absent.

1. `product-owner-system-planner`: decide whether the gap is in-scope now,
   backlog later, or intentionally rejected.
2. Relevant domain agent: validate persona value and real-world edge cases.
3. `system-architect`: review API/data/security impact if the gap changes
   contracts.
4. Implementation agent: build only when the gap is low-risk and in-scope.
5. `tester-qa`: ensure the improvement has acceptance criteria and does not
   break existing slices.

### Excel Export

1. `data-engineer`: entity field catalog and field-level RBAC.
2. `backend-developer`: export service, presets, async threshold, download links.
3. `frontend-developer`: export modal and async notification UX.
4. `tester-qa`: permission filtering, field-level RBAC scoping, sync/async paths.

### Document Knowledge Base / RAG (M33)

1. `ai-engineer`: RAG tool spec, chunking strategy, scope resolution logic, citation prompt, eval plan.
2. `system-architect`: knowledge_base schema, pgvector index, ingestion pipeline architecture, storage boundaries.
3. `backend-developer`: `knowledge_base` module (API, ingestion Celery task, vector store), AI gateway embedding integration.
4. `frontend-developer`: admin KB upload UI (platform + partner), doc status badges, quota bar, chatbot KB-widget integration.
5. `tester-qa`: access control (cross-tenant chunk isolation), no-hallucination on no-result, citation accuracy, provider leakage.

### In-app Institutional Messaging (M25)

1. `employer-domain-agent`: partner → student messaging use cases, rate limits, moderation policy.
2. `system-architect`: thread model, WebSocket fan-out, Redis Pub/Sub, message persistence.
3. `backend-developer`: `messaging` module (API, WebSocket, rate limiter, outbox).
4. `frontend-developer`: slide-in panel (380px), thread list, real-time delivery, unread badge.
5. `tester-qa`: student→student block, rate limit enforcement, real-time delivery, moderation flag.

### Real-time Presence & Activity Audit (M28)

1. `system-architect`: Redis sorted set presence, WebSocket heartbeat, audit log feed pub/sub.
2. `backend-developer`: presence endpoint, heartbeat handler, audit feed WebSocket endpoint.
3. `frontend-developer`: presence dot on avatars, activity feed with Framer Motion animations.
4. `tester-qa`: TTL expiry, feed privacy (partner sees only their feed), heartbeat edge cases.

### Visual Workflow Builder (M26)

1. `employer-domain-agent`: which automation triggers/actions partners need.
2. `system-architect`: DAG model, execution state machine, Celery engine, DRAFT→TEST→ACTIVE lifecycle.
3. `backend-developer`: `workflow` module (flow CRUD, DAG validation, execution engine, history).
4. `frontend-developer`: React Flow canvas, node palette, DAG cycle detection, test mode overlay, execution history.
5. `tester-qa`: cycle detection, max-node enforcement, ACTIVE version constraint, failed step recovery.

## Handoff Packet Template

```markdown
## Handoff

**Goal:** ...
**Source docs read:** ...
**Decisions:** ...
**Contracts:** API/schema/data/event changes.
**Owned files/modules:** ...
**Tests:** required/added commands.
**Risks:** ...
**Open questions:** ...
**Next agent:** ...
```

## Parallelism Rules

- Safe parallel: backend and frontend after API contract; independent modules; data projection design and UI mock using stable contract.
- Unsafe parallel: architecture and implementation of same module; DB migration and service contract before data model approval; prompt changes without AI review.
- If two agents may edit the same file, run sequentially.

## Agent Teams Optional Mode

Use Agent Teams only for:

- Large cross-layer feature builds with disjoint file ownership.
- Parallel review lenses: security, performance, test coverage.
- Competing root-cause investigations.

When using teams:

- Name each teammate predictably.
- Give each teammate explicit owned files/modules.
- Require plan approval for risky DB/security/AI changes.
- Wait for teammates to finish before synthesizing.
- Avoid more than 3-5 teammates unless work is truly independent.
