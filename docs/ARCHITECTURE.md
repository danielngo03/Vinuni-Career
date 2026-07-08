# Architecture — VinUni Career Platform

> Phiên bản: 4.0 | Cập nhật: 26/06/2026
> Tài liệu này là nguồn sự thật cho mọi quyết định kiến trúc. Mọi thay đổi architectural PHẢI update file này trước khi implement.

---

## 1. Tổng quan hệ thống

```
┌────────────────────────────────────────────────────────────────┐
│                   Cloudflare CDN + WAF                         │
└───────────────────────┬────────────────────────────────────────┘
                        │
          ┌─────────────▼─────────────┐
          │   Next.js 15 App Router    │  ← SSR, RSC, i18n (vi/en)
          │   (Vercel / Docker+Nginx)  │
          └─────────────┬─────────────┘
                        │ REST/JSON + SSE (AI streaming)
          ┌─────────────▼─────────────┐
          │   FastAPI Backend          │  ← Python 3.12+, async
          │   (Gunicorn + Uvicorn)     │
          └──┬───────┬────────┬───────┘
             │       │        │
    ┌────────▼──┐ ┌──▼──────┐ ┌▼────────────┐
    │PostgreSQL │ │  Redis   │ │  Celery      │
    │(SQLAlchemy│ │  7.x     │ │  Workers     │
    │ async 2.x)│ │(cache +  │ │  (async jobs)│
    └───────────┘ │  broker) │ └─────────────┘
                  └──────────┘
             │
    ┌────────▼──────────────────────┐
    │         AI Gateway             │
    │   (Provider-agnostic router)   │
    └────────┬──────────────────────┘
             │
    ┌────────▼────────────────────────────────────┐
    │  AI Providers (pluggable, superadmin-managed)│
    │  OpenAI · Anthropic · Gemini · OpenRouter   │
    │  Ollama (local) · Any OpenAI-compatible     │
    └─────────────────────────────────────────────┘
```

**External integrations:**
```
FastAPI ←→ VinUni IdP (OIDC/SAML)
FastAPI ←→ VinUni SIS (REST/DB sync)
FastAPI ←→ Google Calendar / Microsoft Graph
FastAPI ←→ Google Meet / Zoom (link generation)
FastAPI ←→ S3-compatible (MinIO / R2) — file storage
FastAPI ←→ Payment adapters (manual/bank transfer in v1; VNPay/MoMo later)
```

---

## 2. Frontend Architecture

### 2.1 Tech Stack

| Layer | Choice | Version |
|-------|--------|---------|
| Framework | Next.js App Router | 15.x |
| Language | TypeScript (strict mode) | 5.x |
| Styling | Tailwind CSS v4 | 4.x |
| Package manager | pnpm | 9.x |
| Icons | Phosphor Icons (duotone) | 2.x |
| Server state | RSC/server fetch + TanStack Query | — |
| Client state | Zustand (auth, UI) | 5.x |
| Forms | React Hook Form + Zod | — |
| Charts | Recharts | 2.x |
| i18n | next-intl (vi/en) | 3.x |
| Animation | Framer Motion | 11.x |

### 2.2 Route Groups & Folder Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── [locale]/
│   │   │   ├── (public)/                    # Guest-accessible pages
│   │   │   │   ├── page.tsx                 # Homepage / marketplace
│   │   │   │   ├── jobs/
│   │   │   │   │   ├── page.tsx             # Public job board
│   │   │   │   │   └── [jobId]/page.tsx     # Job detail
│   │   │   │   ├── events/
│   │   │   │   │   ├── page.tsx             # Public events
│   │   │   │   │   └── [eventId]/page.tsx   # Event detail + register
│   │   │   │   ├── companies/
│   │   │   │   │   ├── page.tsx             # Company directory
│   │   │   │   │   └── [slug]/page.tsx      # Company page
│   │   │   │   └── auth/
│   │   │   │       ├── login/page.tsx
│   │   │   │       ├── register/page.tsx
│   │   │   │       └── sso/page.tsx         # VinUni SSO callback
│   │   │   │
│   │   │   ├── (student)/                   # Student career marketplace (auth required)
│   │   │   │   ├── layout.tsx               # Student signed-in top nav + contextual subnav
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── profile/page.tsx
│   │   │   │   ├── cv/
│   │   │   │   │   ├── page.tsx             # CV list + manage
│   │   │   │   │   └── builder/page.tsx     # CV builder
│   │   │   │   ├── jobs/
│   │   │   │   │   ├── page.tsx             # Job discovery
│   │   │   │   │   ├── [jobId]/page.tsx     # Job detail + apply
│   │   │   │   │   └── saved/page.tsx       # Bookmarked jobs
│   │   │   │   ├── applications/
│   │   │   │   │   ├── page.tsx             # All applications
│   │   │   │   │   └── [applicationId]/page.tsx
│   │   │   │   ├── interviews/page.tsx
│   │   │   │   ├── offers/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── [offerId]/page.tsx
│   │   │   │   ├── events/
│   │   │   │   │   ├── page.tsx             # Browse events
│   │   │   │   │   └── my-tickets/page.tsx  # My registrations
│   │   │   │   ├── ai-assistant/page.tsx    # Full AI chat
│   │   │   │   ├── interview-sim/
│   │   │   │   │   ├── page.tsx             # Start simulation
│   │   │   │   │   └── [sessionId]/page.tsx # Active session
│   │   │   │   ├── mentorship/
│   │   │   │   │   ├── page.tsx             # Find mentors
│   │   │   │   │   └── sessions/page.tsx
│   │   │   │   ├── subscriptions/page.tsx   # Buy packages
│   │   │   │   └── settings/page.tsx
│   │   │   │
│   │   │   ├── (partner)/                   # Partner workspace (auth required)
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── jobs/
│   │   │   │   │   ├── page.tsx             # Job list
│   │   │   │   │   ├── new/page.tsx         # Create job
│   │   │   │   │   └── [jobId]/
│   │   │   │   │       ├── page.tsx         # Job detail
│   │   │   │   │       ├── pipeline/
│   │   │   │   │       │   ├── page.tsx     # Kanban pipeline view
│   │   │   │   │       │   └── settings/page.tsx  # Pipeline config
│   │   │   │   │       └── analytics/page.tsx
│   │   │   │   ├── candidates/page.tsx      # All candidates (across jobs)
│   │   │   │   ├── talent-pool/page.tsx
│   │   │   │   ├── passive-search/page.tsx  # Browse student profiles
│   │   │   │   ├── interviews/page.tsx
│   │   │   │   ├── offers/page.tsx
│   │   │   │   ├── events/
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── [eventId]/
│   │   │   │   │       ├── page.tsx
│   │   │   │   │       └── attendees/page.tsx
│   │   │   │   ├── advertising/
│   │   │   │   │   ├── page.tsx             # Campaign list
│   │   │   │   │   └── new/page.tsx         # Create campaign
│   │   │   │   ├── analytics/page.tsx
│   │   │   │   ├── team/
│   │   │   │   │   ├── page.tsx             # Members list
│   │   │   │   │   ├── roles/page.tsx       # Roles management
│   │   │   │   │   └── departments/page.tsx
│   │   │   │   ├── billing/page.tsx
│   │   │   │   ├── company-profile/page.tsx
│   │   │   │   └── settings/page.tsx
│   │   │   │
│   │   │   └── (university)/                # University admin (auth required)
│   │   │       ├── layout.tsx
│   │   │       ├── dashboard/page.tsx
│   │   │       ├── moderation/
│   │   │       │   ├── page.tsx             # Queue overview
│   │   │       │   ├── jobs/page.tsx
│   │   │       │   ├── partners/page.tsx
│   │   │       │   ├── events/page.tsx
│   │   │       │   ├── ads/page.tsx
│   │   │       │   └── reviews/page.tsx
│   │   │       ├── users/
│   │   │       │   ├── page.tsx
│   │   │       │   └── [userId]/page.tsx
│   │   │       ├── partners/
│   │   │       │   ├── page.tsx
│   │   │       │   └── [partnerId]/page.tsx
│   │   │       ├── events/
│   │   │       │   ├── page.tsx
│   │   │       │   └── new/page.tsx
│   │   │       ├── advertising/page.tsx
│   │   │       ├── subscriptions/
│   │   │       │   ├── page.tsx             # Package management
│   │   │       │   └── revenue/page.tsx
│   │   │       ├── ai-settings/
│   │   │       │   ├── page.tsx             # Provider management
│   │   │       │   └── costs/page.tsx
│   │   │       ├── career-outcomes/
│   │   │       │   ├── page.tsx             # KPI dashboard
│   │   │       │   └── surveys/page.tsx
│   │   │       ├── analytics/page.tsx
│   │   │       ├── staff/
│   │   │       │   ├── page.tsx
│   │   │       │   ├── roles/page.tsx
│   │   │       │   └── departments/page.tsx
│   │   │       ├── integrations/page.tsx    # SIS, SSO, Calendar
│   │   │       └── settings/
│   │   │           ├── page.tsx             # System config
│   │   │           ├── theme/page.tsx
│   │   │           ├── tiers/page.tsx
│   │   │           ├── policies/page.tsx
│   │   │           └── legal/page.tsx
│   │   │
│   │   ├── api/                             # Next.js BFF routes (minimal)
│   │   └── globals.css                      # Design tokens
│   │
│   ├── components/
│   │   ├── ui/                              # Primitives (Button, Input, Card, Modal, Badge, Select, Tabs...)
│   │   ├── layout/                          # WorkspaceShell, Sidebar, TopBar, Footer
│   │   ├── forms/                           # FileUpload, RichTextEditor, DatePicker, TagInput
│   │   ├── charts/                          # FunnelChart, LineChart, BarChart, DonutChart
│   │   ├── data-table/                      # Sortable, filterable, exportable table
│   │   ├── export/                          # ExcelExportModal (field selection)
│   │   └── feedback/                        # Toast, Alert, Skeleton, EmptyState, ConfirmDialog
│   │
│   ├── features/                            # Domain feature modules
│   │   ├── auth/                            # Login, Register, SSO
│   │   ├── marketplace/                     # Public job board, hero, search
│   │   ├── student/
│   │   │   ├── dashboard/
│   │   │   ├── profile/
│   │   │   ├── cv/                          # Upload, builder, analysis
│   │   │   ├── applications/                # Tracking, timeline
│   │   │   ├── interviews/
│   │   │   └── offers/                      # Offer comparison
│   │   ├── partner/
│   │   │   ├── dashboard/
│   │   │   ├── jobs/                        # Job posting form
│   │   │   ├── pipeline/                    # Multi-round pipeline kanban
│   │   │   ├── candidates/                  # Candidate cards, comparison
│   │   │   ├── talent-pool/
│   │   │   ├── passive-search/
│   │   │   ├── offers/
│   │   │   ├── advertising/                 # Campaign builder
│   │   │   ├── events/
│   │   │   └── team/                        # RBAC management
│   │   ├── university/
│   │   │   ├── dashboard/
│   │   │   ├── moderation/                  # Queue UI
│   │   │   ├── ai-settings/
│   │   │   ├── subscriptions/
│   │   │   ├── career-outcomes/
│   │   │   ├── staff/
│   │   │   └── integrations/
│   │   ├── events/                          # Shared: event pages, ticket purchase, seat map, check-in
│   │   ├── ai-assistant/                    # Chat interface, tool cards
│   │   ├── interview-sim/                   # Simulator session
│   │   ├── mentorship/                      # Mentor browse, booking
│   │   └── notifications/                   # Notification center
│   │
│   ├── lib/
│   │   ├── api/                             # API client, type-safe fetchers
│   │   ├── auth/                            # Session, JWT, OIDC
│   │   ├── hooks/                           # useDebounce, useIntersection, usePagination...
│   │   └── utils/                           # formatDate, formatCurrency, truncate...
│   │
│   ├── store/                               # Zustand stores
│   │   ├── auth.store.ts
│   │   ├── notification.store.ts
│   │   └── chat.store.ts
│   │
│   ├── types/                               # Shared TypeScript types/interfaces
│   └── middleware.ts                        # i18n + auth routing guard
│
├── public/
│   ├── brand/                               # Logo, favicon, OG images
│   └── fonts/
├── next.config.ts
├── tailwind.config.ts
└── package.json
```

---

## 3. Backend Architecture

### 3.1 Tech Stack

| Layer | Choice | Version |
|-------|--------|---------|
| Framework | FastAPI | 0.115+ |
| Language | Python | 3.12+ |
| ORM | SQLAlchemy (async) | 2.x |
| Validation | Pydantic v2 | 2.x |
| Migrations | Alembic | — |
| Task queue | Celery | 5.x |
| Broker + Cache | Redis | 7.x |
| Auth | JWT + OIDC | — |
| Package manager | uv | — |
| Testing | pytest + httpx | — |

### 3.2 Module Structure (Domain-Driven)

Mỗi module theo pattern DDD:
```
backend/app/modules/{domain}/
├── api/
│   ├── router.py           # FastAPI router — chỉ HTTP concerns
│   ├── schemas.py          # Pydantic Request/Response models
│   └── dependencies.py     # Route-level DI (optional)
├── application/
│   └── {name}_service.py   # Use cases, orchestration, business rules
├── domain/
│   ├── models.py           # SQLAlchemy ORM models
│   ├── entities.py         # Pure domain entities (optional)
│   └── repository.py       # Abstract repository interface
├── infrastructure/
│   ├── repository.py       # Concrete SQLAlchemy implementation
│   └── external.py         # External service calls (optional)
└── __init__.py
```

### 3.3 Module Map

```
backend/
├── app/
│   ├── modules/
│   │   ├── auth/                   # JWT, OIDC, sessions, refresh, 2FA
│   │   ├── users/                  # User mgmt, tiers, limits, subscription grants
│   │   ├── organization/
│   │   │   ├── partner/            # Partner RBAC: roles, departments, permissions, members
│   │   │   └── university/         # University RBAC: roles, departments, permissions, staff
│   │   ├── opportunities/          # Job postings, visibility, advanced settings, referral
│   │   ├── recruitment/            # Applications, pipeline, interviews, scorecards, offers
│   │   │   ├── applications/
│   │   │   ├── pipeline/
│   │   │   ├── interviews/
│   │   │   ├── scorecards/
│   │   │   └── offers/
│   │   ├── talent/                 # Talent pool, passive search, contact requests
│   │   ├── documents/              # CV upload, CV Studio, multi-modal parsing, storage
│   │   ├── events/                 # Event CRUD, ticket types, seat maps, registration
│   │   │   ├── api/
│   │   │   ├── application/
│   │   │   │   ├── event_service.py
│   │   │   │   ├── ticket_service.py
│   │   │   │   ├── seat_service.py
│   │   │   │   └── checkin_service.py
│   │   │   └── domain/
│   │   │       └── models.py       # Event, TicketType, Seat, Registration, CheckIn
│   │   ├── advertising/            # Ad campaigns, targeting, approval, performance
│   │   ├── subscriptions/          # Packages, user subscriptions, payment records
│   │   ├── reviews/                # Company reviews, sentiment moderation
│   │   ├── qa_bank/                # Interview Q&A community bank
│   │   ├── mentorship/             # Mentor profiles, sessions, mentee requests
│   │   ├── alumni/                 # Alumni network, directory
│   │   ├── career_outcomes/        # Placement tracking, surveys, KPI
│   │   ├── notifications/          # Notification service, templates, channels
│   │   ├── ai_assistant/           # Chat API, tool registry, conversation history
│   │   ├── ai_settings/            # AI provider management, model config, health
│   │   ├── ai_operations/          # AI task execution (CV parse, match, moderate)
│   │   ├── institution/            # System config, theme, feature flags, tiers, legal
│   │   ├── integrations/           # VinUni SSO, SIS sync, calendar, webhooks
│   │   ├── reporting/              # Analytics, Excel export, read model projections
│   │   └── automation/             # Celery tasks, scheduled jobs
│   │
│   ├── ai/
│   │   ├── gateway/
│   │   │   ├── router.py           # Task → provider + model selection
│   │   │   ├── factory.py          # Provider adapter factory
│   │   │   ├── load_balancer.py    # Round-robin / priority / health-weighted
│   │   │   └── providers/
│   │   │       ├── base.py         # Abstract provider interface
│   │   │       ├── openai_compatible.py  # OpenAI, Azure, Ollama, OpenRouter
│   │   │       ├── gemini.py       # Google Gemini native
│   │   │       └── anthropic.py    # Anthropic native
│   │   ├── agents/
│   │   │   ├── cv_pipeline.py      # CV extraction agent
│   │   │   ├── react.py            # ReAct loop (MAX_ITERATIONS=8, MAX_TOOL_CALLS=12)
│   │   │   ├── runtime.py          # Tool execution runtime + confirmation protocol
│   │   │   └── workforce.py        # Multi-agent orchestration (Celery workers)
│   │   ├── extraction/
│   │   │   ├── ocr_engine.py       # Multi-modal document processing
│   │   │   ├── schemas.py          # Extraction output schemas
│   │   │   └── structured.py       # Structured data extraction
│   │   ├── matching/
│   │   │   └── skills.py           # CV ↔ JD skill matching
│   │   ├── moderation/
│   │   │   └── content.py          # Content safety, bias detection
│   │   ├── safety/
│   │   │   ├── input_guard.py      # Prompt injection, PII strip, rate limits
│   │   │   └── output_guard.py     # Provider leakage redaction, API key scrubbing
│   │   ├── evaluation/
│   │   │   ├── harness.py          # Offline eval runner
│   │   │   ├── datasets/           # {task_name}/ happy_path|adversarial|privacy_boundary|...
│   │   │   └── tracing.py          # Span/trace collection
│   │   ├── retrieval/
│   │   │   ├── rag_retriever.py    # Hybrid dense+BM25 search with RRF
│   │   │   ├── rerank.py           # Cross-encoder reranking (threshold ≥ 0.60)
│   │   │   ├── service.py          # Context assembly (MAX_RAG_CONTEXT_TOKENS=3000)
│   │   │   └── citation_formatter.py
│   │   └── ingestion/
│   │       └── gatekeeper.py       # Document ingestion pipeline
│   │
│   ├── bootstrap/
│   │   ├── lifespan.py             # Startup / shutdown hooks
│   │   └── routes.py               # Mount all module routers
│   │
│   ├── shared/
│   │   ├── exceptions.py           # Custom exception hierarchy
│   │   ├── dependencies.py         # Shared FastAPI dependencies (current_user, etc.)
│   │   ├── pagination.py           # Cursor + offset pagination
│   │   ├── permissions.py          # RBAC permission checker
│   │   ├── audit.py                # Audit log writer
│   │   └── export.py               # Excel export utilities
│   │
│   └── main.py                     # FastAPI app factory
│
├── alembic/
│   └── versions/                   # Migration files (named by date: YYYYMMDD_HHMM_description)
│
├── tests/
│   ├── unit/                       # Per module unit tests
│   ├── integration/                # DB + service integration tests
│   └── e2e/                        # End-to-end API tests
│
├── pyproject.toml
├── .env.example
└── Makefile
```

### 3.4 E36 Platform Trust — Support / Privacy / Abuse (ADR-0014)

See `docs/adr/ADR-0014-platform-trust-support-privacy-abuse.md` for full
rationale. Two new modules plus one extension, no breaking changes:

- **`platform_support`** (new) — support-console read/orchestration services
  only (account/org lookup, outbox health, requeue, package-override
  entrypoint, PII reveal wrapper, support-case resolve). No new ORM tables;
  writes only to `audit_logs` (`resource_type` prefixed `support_*`) and
  `human_review_queue` (`source="support_case"`). Naming follows the existing
  `platform_feedback` / `platform_settings` single-word convention.
- **`compliance`** (new) — owns `consents` and `privacy_requests` tables, the
  `/account/privacy` retention-constant read endpoint, and the scheduled
  retention-enforcement job (ADR-0003 pattern) that soft-deletes/anonymizes
  `application_snapshots` past a hardcoded constant via the `documents`
  facade.
- **`moderation`** (existing, extended) — gains `ContentReport`
  (`content_reports` table) beside `HumanReviewItem`, plus
  `application/report_service.py` (submit + anti-spam) and
  `application/triage_service.py` (merged `content_reports` +
  `human_review_queue` prioritized list, escalate, override). Abuse triage is
  a moderation concern; colocating avoids a cross-module join for the merge.
- `human_review_queue.source` gains code-level constants `support_case` and
  `user_report` (plain `String(32)` column, no DB enum/CHECK constraint — no
  migration needed for the vocabulary itself).
- RBAC: `PERMISSION_CATALOG` (`organization/domain/catalog.py`) gains
  `support: {read, act, escalate}`, `privacy: {read, process}`,
  `abuse: {read, triage, escalate, override}`. No new hardcoded role;
  services gate on these plus `org_reporting_facade.is_university_org`
  (mirrors `review_queue_service._require_university`) so only university-org
  roles can hold platform-trust powers.

---

## 4. Key Architectural Patterns

### 4.1 Pipeline Engine (Multi-round Interview State Machine)

The Pipeline Engine is a core module for managing multi-round interview workflows.

```
PipelineTemplate
  └── stages: [Stage] (ordered list)
        ├── id, order, name, type
        ├── assignee: {mode: DEPARTMENT|PERSON, target_ids}
        ├── required_action: SCORECARD|SCORE_THRESHOLD|MANUAL
        ├── sla_hours: optional
        ├── auto_advance: bool
        └── candidate_notify_template_id

CandidateStage (state machine node)
  ├── candidate_id + job_id + stage_id
  ├── status: ACTIVE|PASSED|REJECTED|ROLLED_BACK
  ├── entered_at, exited_at
  └── scorecard_id (optional)

Transitions:
  ADVANCE: current stage PASSED → create ACTIVE record for next stage
  ROLLBACK: current stage ROLLED_BACK → create ACTIVE record for target stage
  REJECT: current stage REJECTED → send rejection email
```

**State machine rules:**
- Chỉ 1 stage ACTIVE tại một thời điểm per candidate per job
- Rollback phải có reason (min 20 chars)
- Auto-advance chỉ khi required_action đã hoàn thành
- Mọi transition ghi audit log

**Phase 2 stage-engine foundation:** see **ADR-0004** (`docs/adr/ADR-0004-recruitment-pipeline-stage-engine.md`). The pipeline is configurable per org (PRD MODULE 7), but V1 ships the configurable schema (`pipeline_templates` / `pipeline_stages` / `candidate_stages`, migration `0012`) plus a single **seeded system-default 3-stage ladder** (Screening → Interview → Offer, all `required_action=manual`) — the template-builder UI and richer stage-type taxonomy are deferred. `applications.status` stays the **coarse** outcome (`submitted|under_review|rejected|withdrawn`, unchanged from the Phase-1.5 subset); fine position lives in the append-only `candidate_stages` history (one `ACTIVE` row, status `ACTIVE|PASSED|ROLLED_BACK|REJECTED`). The shipped `review`/`reject` decisions are reused, not replaced: `review` becomes the pipeline-entry trigger (materializes stage 1) and `reject` becomes the terminal exit (closes the open stage row); `/advance` + `/rollback` are new service-layer operations that inherit the same optimistic-version, illegal-transition-409, cross-org-404 RBAC, audit, anonymity, and neutral-notification invariants. Scorecards/required-action gating, interview scheduling, offers, the auto-advance worker (on the ADR-0003 scheduler), and bulk actions are explicitly later ADRs.

**Scorecards & required-action gating:** see **ADR-0005** (`docs/adr/ADR-0005-recruitment-scorecards.md`). Per-stage reviewer evaluations ship as `scorecards` + `scorecard_scores` (migration `0013`) with a fixed `DEFAULT_CRITERIA` set (1–5 per criterion), a 4-value `recommendation` (`strong_no|no|yes|strong_yes`), and a partner-only board aggregate. Scorecards are **partner-internal** (never in the student projection, notifications, or email — same privacy class as `rejection_reason`); one editable scorecard per `(application, stage, reviewer)`; the anchoring-bias rule hides other reviewers' scores until the caller submits their own. A stage whose `required_action=scorecard` **blocks `/advance`** until ≥1 scorecard exists, raising `409 scorecard_required` (the `manual` path is unchanged). The per-job criteria editor (`scorecard_templates`/`scorecard_criteria`), the assignee/department `required`-count + `score_threshold` gating, `scorecards.interview_id`, AI scorecard assist, and the §7.8 comparison view are deferred to the template-builder / ADR-0006 (interviews) / AI ADRs.

**Interviews, reviewer assignees & threshold gating:** see **ADR-0006** (`docs/adr/ADR-0006-recruitment-interviews-and-assignees.md`). Interview scheduling ships as `interviews` + `interview_assignees` (migration `0014`) bound to `(application, stage)` — one open interview per stage, PERSON-mode assignees, delivery `mode ∈ {onsite, online, phone}`, Fernet-encrypted `meeting_link`, editable in place. The single ADR-0005 `evaluate_advance_gate` seam is upgraded to be **assignee-aware** (a `scorecard` stage now requires **all assigned interviewers** to submit — `required = len(assignees)`, falling back to `1` with no interview) and to implement **`required_action=score_threshold`** (all assignees in **and** `avg overall_score ≥ pipeline_stages.score_threshold`), with new errors `409 score_below_threshold` and `409 reveal_required`. `scorecards.interview_id` (nullable, `ON DELETE SET NULL`) auto-links a scorecard to its interview. **Anonymity:** scheduling an interview for an anonymous application **requires an already-accepted reveal** (`reveal_approved_at`) — it never implicitly bypasses the student's consent; the handshake stays the only identity path. The candidate is notified of their own interview (identity-safe, no assignee identities); interviewers get partner-internal feed notifications; reminders (T-24h/T-1h) run on the ADR-0003 scheduler via a new idempotent `interview.reminder_sweep` job. DEPARTMENT assignee mode + fractional `threshold_pct`, self-scheduling/ICS calendar sync (PRD §6.6), interview SLA, video integration, and AI scorecard-from-notes are deferred.

**Offers — approval, send, accept/decline & the `hired` outcome:** see **ADR-0007** (`docs/adr/ADR-0007-recruitment-offers.md`). The terminal POSITIVE outcome ships as `offers` (migration `0015`) bound to `(application, stage)` — one LIVE offer per application, an 8-state machine `draft → pending_approval → approved → sent → accepted | declined | expired | rescinded` (editable only while `draft`, content frozen at submit), structured-minimal comp with **Fernet-encrypted `salary_amount`** (recruiter + student only, never in a notification body), no payment gateway (CLAUDE.md manual default). An **internal partner approval gate** (`send` requires `status='approved'`; permissions `create_offer`/`approve_offer`/`send_offer`/`withdraw_offer`, no SoD in V1) precedes send; the university does not approve individual offers. The student responds via `POST /offers/{id}/respond` (accept|decline); **accept moves `applications.status` to a new terminal coarse `hired`** (a pure domain widening — no `applications` DDL; `proj_partner_pipeline` already counts `hired_count`), closes the Offer-stage `candidate_stages` row (`exit_kind='hired'`), and emits a non-blocking `offer.accepted` event for the career-outcome `trust_level=4` (estimated) materializer. **Anonymity:** sending an offer for an anonymous application **requires an already-accepted reveal** (reuses ADR-0006's rule) — the student's own offer copy is identity-safe to them. Expiry/expiring (lazy + a new idempotent `offer.expire_sweep` 5-min ADR-0003 job) and the offer notifications follow the proven sweep+dedupe pattern. Counter-offer/request-extension, offer-letter PDF/template + e-signature (`offer_letter_path` omitted in V1), the multi-offer comparison tool, payment/bank-transfer reconciliation, and separation-of-duties are deferred.

### 4.2 Event Ticketing System

```
Event
  ├── format: ONSITE | ONLINE | HYBRID
  ├── ticket_types: [TicketType]
  │     ├── name, price, capacity
  │     ├── eligibility_tier_ids
  │     ├── sale_start, sale_end
  │     ├── early_bird_price, early_bird_until
  │     └── transfer_allowed, refund_policy
  ├── seat_map: SeatMap (optional)
  │     └── seats: [Seat] (row/col, section, status)
  └── online_link: (encrypted, only for confirmed registrations)

Registration
  ├── user_id + event_id + ticket_type_id
  ├── seat_id (optional)
  ├── status: PENDING_PAYMENT | CONFIRMED | CANCELLED | CHECKED_IN
  ├── qr_code: unique token
  └── payment_record_id (optional)
```

**Seat lock mechanism:**
- Seat selected → lock for 10 minutes (Redis TTL)
- Payment confirmed → permanent lock
- Lock expired → seat released automatically

**Events V1 foundation (registration / capacity / waitlist / check-in):** see **ADR-0008** (`docs/adr/ADR-0008-events-registration-and-checkin.md`). Events live **inside the `opportunities` module** beside jobs and **reuse the jobs patterns** — own `events` table with an event-appropriate lifecycle state machine (`draft → pending_review → published → cancelled | completed`, plus `rejected`; partner events need university moderation, university events auto-approve), the same university-only moderation gate, `is_sponsored`/`is_featured` marketplace flags, optimistic `version`, soft delete, per-write audit, and a dedicated `event_public_read`/`event_visibility` single-source facade the marketplace overview consumes (replacing the "coming soon" teaser, hide-if-empty). V1 is **free single-admission only** — `events.capacity` (nullable = unlimited) holds one number; `event_registrations` (states `confirmed|waitlisted|cancelled|attended|no_show`, one active row per `(event,user)`) enforce capacity atomically via an **event-row `SELECT … FOR UPDATE`** count-check + a partial-unique active-registration index (no overbooking under concurrency); **waitlist promotion is inline-on-cancel (FIFO) + a scheduler backfill safety net**. Check-in V1 is **staff-marks-attended** (no QR); the attendee list is organizer/university-only and PII-minimized (email to the organizer only, never in logs/audit) — events are NOT recruitment-anonymous because registration is a voluntary disclosure to the organizer. Five identity-safe notifications (confirmed / waitlisted / promoted / **T-24h reminder** / cancelled) use the outbox + in-app feed; reminder, waitlist-backfill, no-show, and auto-complete sweeps run on the **ADR-0003** scheduler. Migration `0016_events_registration_and_checkin` creates `events` + `event_registrations`. Ticketing/paid admission/promo codes, numbered-seat selection + Redis locks, QR check-in, encrypted online-link reveal, career-fair booths/sponsor tiers, certificates/surveys, calendar/ICS, recurring events, and the AI auto-approve toggle are explicitly deferred to later ADRs (FKs/columns named for forward-compat).

**Advertising — sponsored/featured placements (V1 manual-billed):** see **ADR-0009** (`docs/adr/ADR-0009-advertising-sponsored-placements.md`). A new `advertising` module (`/api/v1/advertising` + `/api/v1/admin/advertising`) lets a partner **request to sponsor/feature one of their own jobs or events** for a paid, date-windowed, university-approved period — the missing layer above the already-shipped `is_sponsored`/`is_featured` flags + non-removable disclosure infra. The placement entity is **`sponsored_placements`** (polymorphic `target_type {job,event}` + service-validated `target_id`, chosen `ad_packages` tier with a **frozen fixed price**, lifecycle `draft → pending_approval → approved → active → completed | rejected | cancelled`). University **approves disclosure + spend**; an admin records **manual/bank-transfer payment** (`mark_paid` — no gateway, CLAUDE.md default); activation requires **approved AND paid AND inside the window**. The **placement is the source of truth** for sponsorship and the shipped `is_sponsored`/`is_featured` columns become a **recomputed projection** — flipped only through one audited one-way `opportunities.sponsorship_facade.set_target_flags` setter (advertising → opportunities, never reverse), recompute-based so overlapping placements behave correctly. Date-window flips happen **inline + on the ADR-0003 scheduler** (`advertising.activation_sweep` / `completion_sweep` / `flag_reconcile`). **Disclosure stays mandatory and non-removable** — activation drives the exact flags the shipped label infra renders, so no advertising path can produce sponsored content without `Được tài trợ` / `Nổi bật`; the university sees all active placements and can disable any instantly. The marketplace contract is **unchanged** (still reads the now-placement-driven real flags); public never sees campaign internals. V1 limits are simple (display cap, per-org concurrency cap, 1-per-org strip dedupe, one in-flight per target). Migration `0017_advertising_sponsored_placements` creates `ad_packages` + `sponsored_placements`. CPM/CPC **bidding** + budget pacing (the DATA_MODEL §20 `ad_campaigns` end-state), audience **targeting**, banner/video/email-blast creatives, impression/click **analytics**, payment **gateways**, and AI brand-safety/complaint flows are explicitly deferred.

**Subscriptions & manual billing (V1 tiered plans + limit resolution):** see **ADR-0010** (`docs/adr/ADR-0010-subscriptions-and-manual-billing.md`). A new `billing` module (`/api/v1/billing` + `/api/v1/admin/billing`) lets a **student (own user) or partner Admin (own org) request a paid plan**, an admin record a **manual/bank-transfer payment** (`mark_paid` — no gateway, CLAUDE.md default) to activate it for a **fixed date window**, after which a tier's **limits override the platform defaults**. Entities (migration `0019`): a single **audience-typed `subscription_plans`** (`student`/`partner`, a structured **`limits` JSON map**, 4 seeded plans free/pro per audience — superseding the DATA_MODEL §19 per-persona split) and a **polymorphic `subscriptions`** (principal = user OR org, lifecycle `pending → active → expired | cancelled`, frozen `price_amount`, fields-on-row payment). The load-bearing integration is **`billing/application/limit_facade.resolve_limits(session, principal)`** — the **only** way other modules read tier limits (one-way `documents → billing`, never reverse, mirroring `advertising → opportunities`); its **first consumer is the shipped CV active-library cap**: `documents` `cv_service._active_cv_limit` now resolves the active plan's `cv_active_quota` (else the default 5), and every other quota (`pdf_exports_per_month`, `job_post_quota`, …) resolves through the **same** facade later. University **sees all subscriptions + a revenue roll-up** (`meta.revenue`, mirroring advertising `meta.spend`) and can mark-paid/cancel; expiry runs on the **ADR-0003 scheduler** (`billing.expiry_sweep` + `billing.expiring_notice`). Reuses every ADR-0009 invariant (university-only gate, frozen price, manual `mark_paid`, optimistic `version`, `404` masking, per-write audit, outbox+feed notifications). **Proration, scheduled downgrade, refund window, payment-failure grace/dunning, auto-renew, metered-quota *enforcement* beyond the CV cap (the `quota_usage` reset/carryover machinery), AI credits, a multi-payment ledger, and payment gateways are explicitly deferred** (BUSINESS_LOGIC §1.2–§1.6 / DATA_MODEL §19 reference end-state).

### 4.3 AI Gateway

```
Request → GatewayRouter
         ├── resolve task_type (from request context)
         ├── select model (from ai_task_model_configs DB table)
         ├── load_balance (round-robin / priority / health-weighted)
         ├── call provider adapter
         └── on error → fallback chain (provider A → B → C)
```

**Never expose to end users:** provider name, model name, API key, token count, latency, confidence scores.

### 4.3b CV Studio Architecture

`documents` owns CV Studio because it controls uploaded CVs, builder CVs, generated exports, watermarked downloads, and immutable application snapshots.

```text
CV Studio UI
  -> documents API
  -> creation mode: blank_template | confirmed_facts_import | uploaded_import | duplicate_existing | ai_assisted_draft
  -> cv_profiles / cv_sections / cv_versions
  -> optional import diff from uploaded CV extraction or existing CV version
  -> optional AI suggestion or CV-to-job recommendation via ai_assistant tool registry
  -> user accepts diff
  -> new cv_versions row + audit log
  -> export job creates PDF document
```

Boundaries:

- `documents` stores CV structure, versions, exports, and signed access.
- `documents` keeps uploaded CV originals separate from structured builder CVs.
- `ai_assistant` exposes CV AI tools and confirmation protocol.
- `backend/app/ai/` performs generation/rewrite/evaluation through gateway only.
- `recruitment` stores immutable `application_cv_snapshots` when a student applies.
- `reporting` reads aggregated CV readiness metrics only; no raw CV text in projections.

Rendering:

- Backend render service creates canonical PDF exports for applications/downloads.
- Frontend preview may render HTML/A4 preview, but submitted/downloadable files come from backend render output.
- Partner downloads always use the submitted snapshot or selected exported version with watermark.

### 4.4 RBAC Architecture

Both Partner and University use the same configurable RBAC model:

```
Organization (1) ──── (n) Departments
Organization (1) ──── (n) Roles
Role (1) ──── (n) Permissions
  Permission = { resource_type: str, action: str }
Member (n) ──── (m) Roles
Member (n) ──── (m) Departments
```

**RBAC enforcement:** Checked at service layer, NOT only at router. Every protected service method calls `permission_service.require(user, resource, action)`.

**Bootstrap rule (Partner):** First registrant = admin role with all permissions. Admin can create custom roles with any name.

**University RBAC:** Super Admin creates all roles — NOT predefined. Same model as Partner RBAC.

### 4.5 Async Job Architecture

```
Short tasks (< 3s)  → FastAPI async directly (match score, chat tool call)
Long tasks (> 3s)   → Celery worker (CV parsing, batch matching, email send)

API Request → return job_id immediately
           ↓
    Celery Queue (Redis)
           ↓
    Worker executes → update DB → publish outbox event
           ↓
    Notification task → WebSocket / Email / Push
```

**All Celery tasks must be idempotent** — safe to retry on failure.

**Periodic / time-based work (V1):** see **ADR-0003** (`docs/adr/ADR-0003-async-scheduler-and-periodic-jobs.md`). V1 runs a single standalone `python -m app.worker` asyncio scheduler (no APScheduler, no Celery beat yet) started with `BACKGROUND_WORKER_MODE=scheduler`. It drives three idempotent jobs — `outbox.drain` (15s), `reveal.expire_sweep` (5 min), `opportunities.deadline_close` (10 min) — by delegating to the `notifications`/`recruitment`/`opportunities` application services through the `automation/scheduler/jobs.py` registry. The scheduler lifecycle is decoupled from the API request path; the same registry becomes Celery beat entries in production without changing domain code. The outbox dispatch contract gains retry/backoff (`next_attempt_at`) and a `dead` dead-letter state (migration `0011`).

### 4.6 Outbox Pattern (Domain Events)

```sql
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_type VARCHAR NOT NULL,
  aggregate_id UUID NOT NULL,
  event_type VARCHAR NOT NULL,        -- "application.status_changed", "offer.sent"
  payload JSONB NOT NULL,
  actor_id UUID,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Worker polls outbox → publishes events → triggers notifications / webhooks.

### 4.7 Read Models (Dashboards)

Dashboards đọc từ materialized projections — **không JOIN nhiều domain tables live**.

```sql
-- Student dashboard projection (refresh on-demand + every 5 min)
CREATE TABLE proj_student_dashboard (
  student_id UUID PRIMARY KEY,
  profile_completion_pct INT,
  active_applications INT,
  upcoming_interviews INT,
  pending_offers INT,
  recommended_jobs JSONB,
  skill_gaps JSONB,
  updated_at TIMESTAMPTZ
);

-- Partner hiring overview (refresh on write)
CREATE TABLE proj_partner_pipeline (
  partner_id UUID,
  job_id UUID,
  stage_id UUID,
  candidate_count INT,
  sla_overdue_count INT,
  PRIMARY KEY (partner_id, job_id, stage_id)
);

-- University KPI (refresh daily)
CREATE TABLE proj_university_kpi (
  snapshot_date DATE PRIMARY KEY,
  placement_rate DECIMAL,
  avg_salary DECIMAL,
  time_to_hire_days INT,
  dau INT,
  mau INT,
  updated_at TIMESTAMPTZ
);
```

### 4.8 Excel Export

Exports chạy qua Celery worker cho large datasets:
- < 1,000 rows: synchronous response
- 1,000 – 50,000 rows: async job → download link via email/notification

Field selection serialized as JSON per export preset, stored per user.

---

## 5. Authentication Flow

```
VinUni Student:
  → SSO redirect to VinUni IdP (OIDC/SAML)
  → IdP returns id_token
  → Backend validates token, auto-creates/syncs user
  → Issue internal JWT

External users:
  → Email/password or Google SSO
  → Email verification (magic link)
  → Issue internal JWT

All requests:
  → Authorization: Bearer {access_token} (15 min TTL)
  → Refresh: POST /auth/refresh with refresh_token (7 days)
  → Revocation: Redis set of invalidated token JTIs
```

---

## 6. Data Analytics Events

All events follow this schema:

```python
{
  "event_id": UUID,
  "event_type": str,         # "job.viewed", "application.submitted", "ad.clicked"
  "aggregate_type": str,     # "job", "application", "campaign"
  "aggregate_id": UUID,
  "actor_id": UUID | None,   # user who triggered
  "actor_type": str,         # "student", "partner_member", "system"
  "occurred_at": datetime,
  "session_id": str | None,
  "properties": dict         # event-specific context
}
```

Events stored in `analytics_events` table. Aggregations via scheduled workers into projection tables.

---

## 7. Security Requirements

| Concern | Implementation |
|---------|---------------|
| Authentication | JWT (15 min) + Refresh (7 days), OIDC/SAML for VinUni |
| Authorization | RBAC at service layer, not just router |
| AI key storage | AES-256 encrypted in DB |
| CV files | Encrypted at rest (S3 SSE), access via signed URLs |
| CV downloads | Watermarked with partner name + timestamp |
| Rate limiting | Per IP + per user + per endpoint (Redis-based) |
| Brute force | Account lockout after 5 failed attempts |
| Audit logs | Every write action logged with actor, target, timestamp, IP |
| XSS | Content Security Policy headers, sanitize rich text |
| CSRF | SameSite cookies + CSRF tokens for state-changing requests |
| SQL injection | SQLAlchemy ORM only — no raw SQL in application code |

---

## 8. Architectural Constraints (Non-negotiable)

1. **No cross-module imports** — modules communicate via service interfaces only
2. **No business logic in routers** — routers validate HTTP, call services, return responses
3. **No ORM in domain layer** — SQLAlchemy only in `infrastructure/repository.py`
4. **No AI provider names in user-facing responses** — always proxy through gateway alias
5. **No raw enum codes to end users** — map to friendly labels in API schemas
6. **No live JOIN for dashboards** — use read model projections
7. **No direct external service calls from domain** — use outbox + Celery
8. **Idempotent Celery tasks** — every task safe to retry
9. **RBAC checked at service layer** — every protected service method enforces permissions
10. **Audit trail for all write operations** — no exceptions
11. **AI write actions require confirmation** — tool registry must classify tools
12. **Human final say on AI moderation** — no auto-approve without human review option
13. **CV Studio edits are versioned** — AI suggestions produce diffs; accepting creates a new version
14. **Submitted CV snapshots are immutable** — later CV edits never alter existing applications

---

## 9. Infrastructure

### Full Service Stack (Development)

```yaml
# docker-compose.yml — ALL services for local development
services:

  postgres:
    image: pgvector/pgvector:pg16    # includes pgvector extension
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: vinuni_career
      POSTGRES_USER: anhtuan
      POSTGRES_PASSWORD: anhtuan
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U anhtuan -d vinuni_career"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes: [redis_data:/data]

  minio:                             # local S3-compatible file storage
    image: minio/minio:latest
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    volumes: [minio_data:/data]
    # Access console at http://localhost:9001

  mailpit:                           # local email testing (SMTP + web UI)
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"                  # SMTP (use in SMTP_PORT)
      - "8025:8025"                  # Web UI: http://localhost:8025

  clamav:                            # virus scanning (required before any file is stored)
    image: clamav/clamav:stable
    ports: ["3310:3310"]
    volumes: [clamav_data:/var/lib/clamav]
    environment:
      CLAMAV_NO_FRESHCLAMD: "false"  # auto-update virus definitions
    # First startup: downloads definitions (~250MB), takes 1-2 min

volumes:
  postgres_data:
  redis_data:
  minio_data:
  clamav_data:
```

**PostgreSQL extensions** — applied in the baseline migration:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgvector";    -- vector similarity (RAG embeddings)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- trigram search (fuzzy company/job search)
CREATE EXTENSION IF NOT EXISTS "unaccent";    -- Vietnamese accent-insensitive search
CREATE EXTENSION IF NOT EXISTS "btree_gin";   -- composite GIN indexes
```

**Dev startup commands:**
```bash
# 1. Start all services
docker compose up -d

# 2. Backend
cd backend && uv sync
uv run alembic upgrade head          # runs migrations including extension creation
uv run uvicorn app.main:app --reload --port 8000

# 3. Celery worker (separate terminal)
cd backend && uv run celery -A app.modules.automation.workers.celery_app worker -l info

# 4. Frontend
cd frontend && pnpm install
pnpm dev --port 3000

# 5. Create MinIO bucket (first run only)
cd backend && uv run python scripts/setup_storage.py  # creates bucket, sets public rules
```

### Environment Variables
See `backend/.env.example` and `frontend/.env.example`. Never commit `.env` or `.env.local`.

### Production Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Vercel (primary) | Next.js optimized; or Docker + Nginx for self-host |
| Backend | Docker + Gunicorn + 4 Uvicorn workers | Behind Nginx reverse proxy |
| Database | Managed PostgreSQL + pgvector | Supabase / Neon / RDS with pgvector enabled |
| Cache + Queue | Managed Redis | Upstash / ElastiCache; 3 DBs (cache / celery broker / celery results) |
| File storage | Cloudflare R2 | S3-compatible, no egress fees, CDN included |
| CDN | Cloudflare | Frontend static assets + signed file delivery |
| Email | SendGrid or AWS SES | Transactional email |
| Push | Firebase Cloud Messaging | Mobile + web push |
| Virus scan | ClamAV on dedicated container | Or SaaS alternative in production |
| Error monitoring | Sentry | Frontend + Backend |
| Metrics | Prometheus + Grafana | Or Datadog for managed |
| Connection pooling | PgBouncer | Required at scale (>20 concurrent connections) |

---

## WebSocket & Real-time Architecture

### Connection Layer

```
Client (Browser)
    ↕ WebSocket (/ws?token=JWT)
FastAPI WebSocket Handler
    ↕ async
ConnectionManager (in-process dict + Redis Pub/Sub)
    ↕
Redis Pub/Sub (cross-process fan-out for multi-worker deploy)
```

Every Uvicorn worker has its own `ConnectionManager`. When user A (on worker 1) sends message to user B (on worker 2):
1. Worker 1 cannot find B's WebSocket locally
2. Worker 1 publishes to Redis channel `ws:user:{B_id}`
3. Worker 2 (subscribed to that channel) forwards to B's WebSocket

```python
# Redis subscriber per worker process (background task)
async def redis_subscriber():
    pubsub = redis.pubsub()
    await pubsub.psubscribe("ws:user:*")
    async for message in pubsub.listen():
        if message["type"] == "pmessage":
            user_id = UUID(message["channel"].split(":")[-1])
            connection_manager.send_local(user_id, json.loads(message["data"]))
```

### Message Persistence

> **Institutional messaging — V1 is REST + polling, not WebSocket (see ADR-0012,
> `docs/adr/ADR-0012-messaging-institutional.md`).** The `messaging` module ships
> persisted `message_threads` / `messages` / `message_thread_participants` (migration
> `0023`) with a REST send/list API and client polling for unread (mirroring the
> notification-bell `unread-count` pattern) — no WS infra in V1. Persist-before-deliver
> is honored by construction (a REST POST is the persist; a poll reads committed rows).
> The permission matrix (never student↔student; partner↔student only with a recruitment
> application, anonymity-masked until the reveal handshake; rate-limited) is enforced at
> the service layer on thread-create, every send, AND read/subscribe. A new message
> notifies through the **shipped notifications feed/outbox** (preference-gated,
> PII-safe). The `/ws/` + Redis pub/sub fan-out + presence design below is the
> **deferred follow-up** that attaches to the same tables and service-layer predicates;
> when built, it publishes only **after** the persist commits, re-checks identity+tenant
> on connect, and exposes presence only as coarse buckets (never to partners). The SQL
> sketch below uses `conversation_id` / `conversations` / `message_reads`; ADR-0012
> supersedes those names with `thread_id` / `message_threads` /
> `message_thread_participants.last_read_at`.

Messages are ALWAYS persisted to DB BEFORE sending to WebSocket. If WebSocket delivery fails, the message is not lost — client fetches on reconnect.

```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  sender_id UUID NOT NULL REFERENCES users(id),
  content TEXT NOT NULL,
  message_type VARCHAR NOT NULL DEFAULT 'text',  -- text | file | system
  attachments JSONB DEFAULT '[]',
  reply_to_id UUID REFERENCES messages(id),
  edited_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE message_reads (
  message_id UUID NOT NULL REFERENCES messages(id),
  reader_id UUID NOT NULL REFERENCES users(id),
  read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (message_id, reader_id)
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC);
```

### Presence & Online Status

```python
# Redis sorted set: key = "presence", member = user_id, score = unix_timestamp of last ping
# Pinged every 30s by client WebSocket

async def update_presence(user_id: UUID) -> None:
    await redis.zadd("presence", {str(user_id): time.time()})
    await redis.expire("presence", 300)  # auto-clean if server restarts

async def get_presence_status(user_id: UUID) -> str:
    last_seen = await redis.zscore("presence", str(user_id))
    if not last_seen:
        return "offline"
    delta = time.time() - last_seen
    if delta < 30:
        return "online"
    elif delta < 300:
        return "away"
    return "offline"
```

---

## Visual Workflow Builder Architecture

### Flow Storage

```sql
CREATE TABLE workflow_flows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  description TEXT,
  trigger_type VARCHAR NOT NULL,  -- "student_registered", "application_submitted", etc.
  graph JSONB NOT NULL,           -- React Flow node/edge format
  status VARCHAR NOT NULL DEFAULT 'DRAFT',  -- DRAFT | ACTIVE | PAUSED | ARCHIVED
  version INT NOT NULL DEFAULT 1,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  activated_at TIMESTAMPTZ
);

CREATE TABLE workflow_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id UUID NOT NULL REFERENCES workflow_flows(id),
  trigger_event JSONB NOT NULL,   -- what triggered this run
  status VARCHAR NOT NULL,         -- RUNNING | COMPLETED | FAILED | CANCELLED
  started_at TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  node_logs JSONB NOT NULL DEFAULT '[]'  -- [{node_id, entered_at, exited_at, decision, error}]
);
```

### Flow Execution Engine (Celery)

```python
@app.task(bind=True, max_retries=3)
def execute_flow(self, flow_id: str, trigger_payload: dict, execution_id: str) -> None:
    flow = load_flow(flow_id)
    execution = load_execution(execution_id)

    current_node = find_trigger_node(flow.graph)
    context = FlowContext(trigger=trigger_payload, variables={})

    while current_node:
        log_node_entry(execution_id, current_node.id)
        try:
            result = await execute_node(current_node, context)
            log_node_exit(execution_id, current_node.id, result.decision)
            context.update(result.output_variables)
            current_node = resolve_next_node(flow.graph, current_node, result.decision)
        except NodeExecutionError as e:
            log_node_failure(execution_id, current_node.id, str(e))
            if e.is_retryable:
                raise self.retry(exc=e, countdown=60)
            update_execution_status(execution_id, "FAILED")
            return

    update_execution_status(execution_id, "COMPLETED")
```

---

## Activity Audit Infrastructure

### Audit Table (all write actions)

```sql
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id UUID NOT NULL,
  actor_type VARCHAR NOT NULL,    -- "student" | "partner_member" | "university_staff" | "system"
  action VARCHAR NOT NULL,         -- "candidate.advanced" | "cv.downloaded" | "job.created" etc.
  target_type VARCHAR NOT NULL,
  target_id UUID,
  before_state JSONB,              -- JSON snapshot before change
  after_state JSONB,               -- JSON snapshot after change
  ip_address_hash VARCHAR,         -- SHA-256(IP) — never store raw IP
  user_agent_hash VARCHAR,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  org_id UUID                      -- which org context (partner or university)
);

-- Partition by month for performance
CREATE INDEX idx_audit_actor ON audit_logs(actor_id, occurred_at DESC);
CREATE INDEX idx_audit_org ON audit_logs(org_id, occurred_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, occurred_at DESC);
```

### Real-time Activity Feed

```python
# After writing audit_log → publish to relevant Redis channel
async def publish_activity(audit: AuditLog) -> None:
    if audit.org_id:
        # Partner feed: notify partner's admin users
        channel = f"activity:org:{audit.org_id}"
    else:
        # University feed: notify university admin
        channel = "activity:university"

    await redis.publish(channel, audit.to_feed_json())
```

---

## Push Notification Infrastructure

```
webpush-python (VAPID keys stored in settings)
    ↓
User's browser Service Worker
    ↓ (even if app is closed)
Notification appears on OS

Flow:
  1. User grants permission → JS gets PushSubscription object
  2. Frontend sends PushSubscription to POST /notifications/push-subscription
  3. Backend stores in user_push_subscriptions table
  4. On event (new message, SLA breach, etc.):
     → Celery task: load user's subscriptions → webpush.send_notification()
  5. Service Worker receives → shows OS notification
  6. User clicks → opens app to relevant page (deep link in notification)
```

```sql
CREATE TABLE user_push_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  endpoint TEXT NOT NULL,
  keys JSONB NOT NULL,  -- {p256dh, auth} — encrypted
  device_hint VARCHAR,  -- "chrome_desktop", "safari_mobile" (from UA)
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  UNIQUE(user_id, endpoint)
);
```

---

## Document Knowledge Base (RAG) Architecture

### Module Location

```
backend/app/modules/knowledge_base/
  api/          # upload, list, delete, status endpoints
  application/  # ingestion orchestration, query service, permission checks
  domain/       # chunk model, document lifecycle, visibility rules
  infrastructure/
    chunker.py         # paragraph-aware + sliding window chunking
    extractor.py       # PDF/DOCX/TXT text extraction
    embedder.py        # calls AI gateway embedding endpoint
    vector_store.py    # pgvector CRUD
    virus_scanner.py   # ClamAV integration

backend/app/ai/retrieval/
  rag_retriever.py     # cosine similarity search + scope filtering
  context_builder.py   # assembles top-K chunks into prompt context
  citation_formatter.py # formats source citations for end-user response
```

### Data Model

```sql
-- Knowledge base registry
CREATE TABLE knowledge_bases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope VARCHAR NOT NULL,          -- 'platform', 'partner', 'job'
  owner_id UUID,                   -- NULL for platform, org_id for partner, job_id for per-job
  owner_type VARCHAR,              -- 'organization', 'job'
  name VARCHAR(255) NOT NULL,
  total_size_bytes BIGINT DEFAULT 0,
  doc_count INT DEFAULT 0,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Individual documents
CREATE TABLE knowledge_base_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  filename VARCHAR(512) NOT NULL,
  original_mime_type VARCHAR(100) NOT NULL,
  storage_key TEXT NOT NULL,       -- internal S3 key, never exposed
  size_bytes BIGINT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',  -- PROCESSING, READY, FAILED
  error_message TEXT,
  chunk_count INT DEFAULT 0,
  extracted_text_preview TEXT,     -- first 500 chars for admin verification
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

-- pgvector chunks
CREATE TABLE knowledge_base_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES knowledge_base_documents(id) ON DELETE CASCADE,
  knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  section_heading TEXT,
  content TEXT NOT NULL,
  token_count INT NOT NULL,
  embedding VECTOR(1536),          -- dimension matches configured embedding model
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for fast cosine similarity search
CREATE INDEX knowledge_base_chunks_embedding_idx
  ON knowledge_base_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Composite index for KB-scoped search
CREATE INDEX knowledge_base_chunks_kb_idx
  ON knowledge_base_chunks (knowledge_base_id, chunk_index);
```

### Ingestion Pipeline (Celery)

```python
# backend/app/modules/knowledge_base/infrastructure/tasks.py

@celery_app.task(bind=True, max_retries=3)
def process_document(self, document_id: str) -> None:
    """Idempotent: safe to retry. Marks doc FAILED on terminal error."""
    doc = get_document(document_id)
    if doc.status == "READY":
        return  # already processed

    try:
        # 1. Download from object storage
        raw_bytes = storage.download(doc.storage_key)

        # 2. Virus scan
        virus_scanner.scan_or_raise(raw_bytes, doc.filename)

        # 3. Text extraction
        text = extractor.extract(raw_bytes, doc.original_mime_type)

        # 4. Chunk
        chunks = chunker.chunk(text, target_tokens=512, overlap_tokens=64)

        # 5. Embed in batches of 50
        for batch in batched(chunks, 50):
            vectors = embedder.embed_batch([c.content for c in batch])
            vector_store.upsert_chunks(document_id, batch, vectors)

        # 6. Mark READY
        update_document_status(document_id, "READY", chunk_count=len(chunks),
                                preview=text[:500])

    except TerminalError as e:
        update_document_status(document_id, "FAILED", error_message=str(e))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
```

### RAG Query Service

```python
# backend/app/ai/retrieval/rag_retriever.py

async def retrieve(
    query: str,
    permitted_kb_ids: list[UUID],
    top_k: int = 5,
) -> list[ChunkResult]:
    """Returns top-K chunks across all permitted knowledge bases."""
    query_embedding = await embedder.embed(query)

    rows = await db.execute("""
        SELECT
            c.id, c.content, c.section_heading, c.chunk_index,
            d.filename, d.id AS document_id,
            1 - (c.embedding <=> :query_vec) AS similarity
        FROM knowledge_base_chunks c
        JOIN knowledge_base_documents d ON c.document_id = d.id
        WHERE c.knowledge_base_id = ANY(:kb_ids)
          AND d.status = 'READY'
          AND 1 - (c.embedding <=> :query_vec) > 0.6   -- minimum relevance threshold
        ORDER BY similarity DESC
        LIMIT :top_k
    """, {"query_vec": query_embedding, "kb_ids": permitted_kb_ids, "top_k": top_k})

    return [ChunkResult(**row) for row in rows]
```

### Scope Resolution

```python
# Which KBs a user may query in a given context
async def resolve_permitted_kbs(
    user: User,
    context: QueryContext,
) -> list[UUID]:
    kb_ids = []

    # 1. Platform KB — all authenticated users
    platform_kb = await get_platform_kb()
    if platform_kb:
        kb_ids.append(platform_kb.id)

    # 2. Partner KB — browsing or has applied to this org
    if context.org_id:
        partner_kb = await get_partner_kb(context.org_id)
        if partner_kb and await user_can_access_partner_kb(user.id, context.org_id):
            kb_ids.append(partner_kb.id)

    # 3. Per-Job KB — active application required
    if context.job_id:
        job_kb = await get_job_kb(context.job_id)
        if job_kb and await user_has_active_application(user.id, context.job_id):
            kb_ids.append(job_kb.id)

    return kb_ids
```

### Storage & Security

- Original files stored at `kb/{kb_scope}/{owner_id}/{document_id}/{filename}` — never exposed directly
- Access via signed URL with 15-minute TTL (admin preview only)
- Virus scan is mandatory; any failure = reject upload, do NOT store
- Extracted text and embeddings stored in DB only (not re-downloadable from object storage by end users)
- Partner KB chunks only queryable by users with access to that partner (browsing profile or having applied)
- University Platform KB readable by all authenticated users, no guests

---

## Local-First Runtime Addendum

Phase 0/1 development should run backend and frontend directly on localhost.

- Docker is optional infrastructure only until the new scaffold explicitly regenerates it.
- Backend runtime uses direct `uv` commands.
- Frontend runtime uses direct package-manager commands.
- Postgres/Redis may run locally; SQLite is only for narrow unit tests.
- Background jobs go through a queue interface. Local default may run inline; Celery replaces it without changing domain code.
- Email uses Mailpit or console adapter locally.
- OCR/document parsing uses lightweight native extraction before OCR.
- AI tests use offline/fake provider by default; OpenRouter/DeepSeek-compatible real calls are opt-in and capped.

Do not introduce GPU-only, Docker-only, or heavy always-on dependencies for Phase 0/1.

## AI Settings Governance (ADR-0011)

The `ai_settings` module (`backend/app/modules/ai_settings/`) owns the admin-managed AI
governance surface: a **single platform-scoped settings row** holding active model **aliases**
per task family (chat/reasoning/embedding/eval), feature flags (`cv_llm_structuring_enabled`,
`job_fit_ai_explanation_enabled`), a per-day USD budget, and a DB `real_calls_enabled` toggle —
**never raw keys, provider names, model paths, or base URLs** (keys stay in env per
`docs/ENVIRONMENT.md`). A resolution facade (`ai_settings.application.resolver`) merges the DB
row with env + key-presence under a strict precedence — **env `AI_REAL_CALLS_ENABLED` + a
present key is the hard ceiling; the DB toggle can only restrict/select within it; no key forces
real calls off** — this V1 singleton row and its `/api/v1/admin/ai-settings` GET/PATCH
shape remains masked for ordinary university staff. Per ADR-0011.2 (see
`docs/API_CONTRACTS.md` / `docs/AI_PRODUCT_SPEC.md` §5.5), only platform
superadmins may view or manage raw provider/model identity in the future
multi-row routing/provider registry; ordinary university staff receive alias
handles and derived status only (never concrete model ids, provider names, keys,
or base URLs). The resolver **publishes** an immutable `EffectiveAiConfig` snapshot into the
gateway's pure in-memory holder (`app/ai/gateway/runtime_config.py`), one-way, mirroring the
`structuring.set_llm_structuring_adapter` and `advertising → sponsorship_facade` seams. The
shipped consumers (`gateway.factory.real_provider_active`/`get_provider`, `ai/cv/llm.py`,
`extraction/adapters/structuring.py`, `documents/job_fit_service.py`) read the snapshot — making
a future `OPENROUTER_API_KEY` activatable by **one admin PATCH, no code change**. Admin
endpoints (`/api/v1/admin/ai-settings`, university/superadmin only, audited) expose alias names +
**derived status only** (`key_configured`, `real_calls: offline|available|enabled`) plus a
kill-switch rollback. The metered `ai_usage_log` ledger + `402 BUDGET_EXCEEDED` + multi-row
`ai_task_model_configs` mapping are deferred at named seams. See ADR-0011.
