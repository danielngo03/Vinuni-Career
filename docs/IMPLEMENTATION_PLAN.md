# Implementation Plan — VinUni Career Platform

> Phiên bản: 5.0 | Cập nhật: 27/06/2026  
> Purpose: delivery plan for the clean greenfield rebuild after deleting the previous `backend/` and `frontend/` implementations.

---

## 1. Current Strategy

Build the platform from scratch from:

- `CLAUDE.md`
- `.claude/agents/`, `.claude/rules/`, `.claude/skills/`, `.claude/commands/`
- `docs/`

Do not reuse the previous backend/frontend folders, previous git history, or remembered implementation status.

If `backend/` or `frontend/` are absent, Claude must scaffold them from the source-of-truth docs.
If they exist with only `.env` / `.env.example`, treat them as env seeds, not as implemented code.

Root legacy files may remain temporarily during reset. Claude should not treat existing root `docker-compose.yml`, `pyrightconfig.json`, old Makefiles, or old README content as source of truth until they are regenerated or explicitly verified for the new scaffold.

---

## 2. Source-Of-Truth Roles

| File | Role |
|---|---|
| `CLAUDE.md` | Claude Code entrypoint and operating rules |
| `docs/PRODUCT_REQUIREMENTS.md` | Product/persona/module scope |
| `docs/CV_STUDIO_SPEC.md` | CV upload, template builder, AI-assisted fill/rewrite, exports, snapshots |
| `docs/BUSINESS_LOGIC.md` | Deep business rules and edge cases |
| `docs/ARCHITECTURE.md` | Technical architecture, module boundaries, infra, ADR notes |
| `docs/API_CONTRACTS.md` | API, auth, error, pagination, SSE, event contracts |
| `docs/DATA_MODEL.md` | Canonical entities, tenancy, audit, soft delete, projections |
| `docs/SECURITY_PRIVACY.md` | RBAC, PII, CV access, AI safety, ads compliance, audit |
| `docs/AI_PRODUCT_SPEC.md` | AI task matrix, model aliases, tools, eval, fallback, rollback |
| `docs/DESIGN.md` | Visual/UI source of truth |
| `docs/UI_QUALITY_BAR.md` | UI polish, responsiveness, accessibility, browser QA release gate |
| `docs/SCREEN_SPECS.md` | Screen-level UX for critical workflows |
| `docs/SYSTEM_ACCEPTANCE_BAR.md` | Cross-functional completion gate for product/backend/frontend/AI/data/security |
| `docs/LOCAL_DEV_STACK.md` | Local-first runtime, lightweight dependencies, OCR/parser defaults |
| `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` | Notification/email/push/template/preference rules |
| `docs/EDGE_CASES_FAILURE_MODES.md` | Failure taxonomy, invalid inputs, recovery, user-safe error rules |
| `docs/TEST_STRATEGY.md` | Test pyramid, phase gates, E2E expectations |
| `docs/ENVIRONMENT.md` | Local/dev env variable names and secret policy |
| `docs/TASK_ROUTING.md` | Agent routing, sequence/parallel rules, handoff packet |
| `docs/BACKLOG.md` | Prioritized story IDs |
| `docs/ROADMAP.md` | Phase order and exit criteria |
| `docs/IMPLEMENTATION_STATUS.md` | Verified implementation facts only |
| `docs/CLAUDE_CODE_SETUP.md` | Claude Code memory/agent/hook/plugin/MCP setup |

---

## 3. Build Principles

1. Start from working foundations, not fake pages.
2. Core loops first: student activation, employer hiring, university governance.
3. Product scope and architecture precede implementation.
4. API/data contracts precede frontend implementation.
5. AI features require eval, fallback, rollback, confirmation, cost controls, and safety review.
6. RBAC, audit, tenant isolation, privacy, and PII-safe logs are baseline requirements.
7. UI must be modern, credible, responsive, accessible, and browser-verified before being called complete.
8. V1 payment default is manual/bank transfer adapter; online gateway adapters are later-phase.
9. Local dev is app-localhost first; Docker is optional infrastructure only until explicitly regenerated.
10. Notification/email/account-device settings are core platform UX, not afterthoughts.
11. Edge cases are part of the feature contract, not QA cleanup.
12. Every frontend slice must define the persona surface it serves: public
    marketplace, student command center, partner recruiting ops, or university
    operations center.
13. Design plugins can assist exploration, but completion requires product-owner,
    domain, frontend, and tester-qa review against screenshots and real workflow
    states.
14. Use `docs/SYSTEM_ACCEPTANCE_BAR.md` before status updates; a slice is not
    complete until product, business, backend, data, frontend, AI, security, and
    verification gates pass or documented gaps remain open.

---

## 4. AI Provider And Cost Policy

- Never write real API keys into docs, code, tests, `.env.example`, or tracked config.
- Root `.env` / `.env.example` are reserved for AI hook logging only.
- Backend local/dev keys live in `backend/.env`.
- Frontend local/dev config lives in `frontend/.env` and may expose only `NEXT_PUBLIC_*` values.
- Standard env names:
  - `OPENROUTER_API_KEY`
  - `AI_DEFAULT_PROVIDER=openrouter`
  - `AI_DEFAULT_MODEL_ALIAS=chat_cheap`
  - `AI_EMBEDDING_MODEL_ALIAS=embedding_cheap`
  - `AI_EVAL_MODEL_ALIAS=eval_cheap`
- Use low-cost/free OpenRouter or DeepSeek-compatible models for manual smoke tests.
- Prefer offline/fake providers for unit tests and CI.
- Make real model calls only after offline tests pass and the test records why a real call is needed.
- End users never see provider names, model names, token counts, latency, prompts, raw confidence, or internal status codes.

---

## 5. Phase 0 — Clean Scaffold

Backend:

- FastAPI app factory, settings, structured logging, CORS, exception handlers.
- Health/readiness endpoints.
- SQLAlchemy 2 async session, Alembic baseline, Postgres + pgvector.
- Redis and Celery skeleton.
- Local worker adapter with inline mode for early smoke tests.
- Shared response/error/pagination utilities.
- Permission checker, audit writer, outbox/event table.
- AI gateway skeleton with offline provider and OpenAI-compatible adapter.
- Lightweight extraction stack: PyMuPDF/PyMuPDF4LLM adapter when available,
  pdfplumber fallback, python-docx, Tesseract `vie+eng` fallback.
- CV upload validation for blank/not-CV/password/corrupt/low-quality/duplicate files.
- Notification outbox, template renderer, and local email preview adapter.
- Backend test/lint/type-check setup.

Frontend:

- Next.js App Router, TypeScript strict, Tailwind, i18n.
- Design tokens from `docs/DESIGN.md`.
- App shell family: public marketplace top nav, student signed-in marketplace
  top nav, partner/university ops sidebar + topbar, responsive nav.
- Base UI primitives: Button, Input, Select, Modal/Sheet, Tabs, Toast, Skeleton, EmptyState, StatusBadge, DataTable.
- Locale detection and language switcher for `vi`/`en`.
- Account settings, notification preferences, and security/device sessions shell.
- Browser QA setup using Playwright/chrome-devtools MCP.

Exit criteria:

- Backend health endpoint passes tests.
- Frontend shell builds and renders.
- Quality gates pass.
- `docs/IMPLEMENTATION_STATUS.md` updated with verified facts.

---

## 6. Phase 1 — Core Activation Loop

Student:

- Auth, email verification/reset, session refresh.
- Student profile, education, experience, skills, privacy.
- Account settings: devices/sessions, notification preferences, email language, security events.
- CV Studio P0: upload existing CV with preview-first ingestion/review,
  create from blank/template, import from profile/uploaded CV, AI-assisted
  fill/rewrite, A4 preview, PDF export, version history.
- Public job discovery and apply flow with immutable application CV snapshot.

Partner:

- Partner registration.
- Organization RBAC.
- Partner profile.
- Job creation and university moderation submission.
- Application list/detail.

University:

- Staff RBAC foundation.
- Moderation queue.
- Notification/email template builder with versioned variables.
- Audit trail.

Exit criteria:

- Student can register, create/upload/manage CVs without a mandatory profile
  form, receive CV-to-job recommendation, and apply with an immutable CV
  snapshot.
- Partner can register, create org, submit job, and view applications.
- University can moderate with audit.
- Browser/E2E core flow verified.

---

## 7. Phase 2 — Strong Product Workflows

- Multi-round recruitment pipeline, scorecards, interview scheduling.
- AI Career Assistant with tool cards and confirmation for write actions.
- AI CV review, job matching, interview simulator.
- Passive candidate search with privacy controls.
- Events with registration/check-in/waitlist.
- Notifications and messaging baseline.
- University AI settings and cost dashboard.
- Knowledge base/RAG foundation with citations.

---

## 8. Phase 3+ — Platform Depth

- Subscriptions, quota, manual billing reconciliation, later gateway adapters.
- Advertising/sponsored placement with mandatory labels.
- Reviews and moderation.
- Mentorship and alumni network.
- Career outcomes/reporting/Excel export.
- Workflow automation builder.
- Advanced analytics, experiments, continuous AI eval.

---

## 9. Autopilot Usage

When a build has been paused because product/UI quality feels wrong, run a
review snapshot before continuing:

```text
/review-snapshot Review the current implementation before continuing. Focus on product fit, all persona surfaces (public marketplace, student command center, partner recruiting ops, university operations), jobs/events/companies discovery, sponsored/ad placements, UI/UX quality, AI workflow safety, data/edge cases, and whether IMPLEMENTATION_STATUS over-claims completion. Do not edit backend/frontend code during this review. Produce severity-ordered findings, per-persona surface scores, and the exact continuation prompt.
```

Recommended overnight prompt:

```text
/autopilot-build Continue from the latest /review-snapshot findings and SYSTEM_ACCEPTANCE_BAR. First fix product/UI drift: public search-first career marketplace with public jobs/events/companies/sponsored inventory, persona-specific student/partner/university workspaces, dashboard read models, notification center, navigation cleanup, browser evidence, and security P2 items (httpOnly refresh cookies, enforced/encrypted TOTP). Then continue Phase 1 and Phase 2 in small verified slices. Use Product Gap Review when you discover missing practical features or weak business logic. Use low-cost/free AI model calls only when offline tests pass and a real smoke test is necessary.
```

Claude should work in small verified slices: select priority, read docs, plan, implement, run gates, fix failures, update status, continue.
