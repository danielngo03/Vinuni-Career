# Roadmap — VinUni Career Platform

> Phiên bản: 5.2 | Cập nhật: 08/07/2026
> Roadmap này theo sát `docs/PRODUCT_REQUIREMENTS.md` v5.0.
> Thứ tự ưu tiên: Core loops trước → Advanced features → AI → Monetization → University intelligence → Real-time + RAG.
>
> **Lưu ý về Module ID:** ROADMAP dùng M1–M33 theo thứ tự *ưu tiên giao hàng*. PRD dùng MODULE 1–24 theo thứ tự *nhóm tính năng*. Hai bộ số này KHÔNG đồng nhất — xem bảng cross-reference ở §Module ID Legend.

---

## Product correction — 08/07/2026

- **AI provider/model secrecy:** Students, partners, guests, and ordinary university staff must never know which provider or concrete model the platform uses. Only platform superadmins may view/create/update/delete provider records, concrete model bindings, pricing rows, fallback chains, health probes, and routing internals. API keys and base URLs are never returned by any API.
- **AI quota and credits:** quota is not only a sidebar percentage. Every AI-producing action that creates user/business value or provider cost must pass through a durable usage ledger: JD extraction, CV extraction/structuring, CV-JD fit/match explanation, missing-skill suggestions, CV rewrite/template fill, chatbot turns, interview simulator, partner JD tools, partner screening/briefing, moderation AI, workflow AI nodes, embeddings/rerank when billed, and proactive AI jobs. Cache hits, deterministic local logic, validation-only checks, and provider failures do not consume user credits, although provider-cost telemetry may still record internal spend.
- **Persona commercial model:** Students and partners can upgrade packages or buy credits. University usage is controlled by platform/university admins through limits, budgets, approvals, and internal request workflows, not an upgrade CTA.
- **Dashboards:** dashboard V2 work must use real read models, real empty/error/permission states, charts/flows appropriate to the job, and no fake demo metrics.

## Nguyên tắc phân pha

1. **Phụ thuộc trước** — không build feature B khi A chưa có
2. **Value delivery fast** — mỗi phase phải deliver working product cho ít nhất 1 user group
3. **AI ở mọi phase** — không tách AI thành phase riêng biệt hoàn toàn; tích hợp dần
4. **Testable milestones** — mỗi phase kết thúc có acceptance criteria rõ ràng

---

## Phase 0 — Foundation (Weeks 1–3)

**Mục tiêu:** Dự án mới hoàn toàn, nền tảng kỹ thuật vững chắc, zero legacy debt.

### Backend scaffold
- [ ] Python 3.12, FastAPI, uv, SQLAlchemy async 2.x, Pydantic v2
- [ ] Alembic migration setup
- [ ] Redis connection (cache + Celery broker)
- [ ] Celery worker setup
- [ ] AI Gateway router skeleton (provider-agnostic, no providers yet)
- [ ] Outbox events table
- [ ] Audit log table
- [ ] Shared RBAC permission checker (`shared/permissions.py`)
- [ ] Shared pagination, exceptions, dependencies

### Frontend scaffold
- [ ] Next.js 15 App Router, TypeScript strict, Tailwind v4
- [ ] pnpm, ESLint, Prettier
- [ ] next-intl setup (vi + en)
- [ ] Design system tokens (globals.css — color, typography, spacing)
- [ ] Base UI components: Button, Input, Card, Badge, Modal, Toast, Skeleton
- [ ] Shells by persona: public top nav, student signed-in marketplace top nav, partner/university ops sidebar + topbar
- [ ] Dark mode toggle (CSS custom property swap)

### Infrastructure
- [ ] Docker Compose: postgres + redis + backend + frontend
- [ ] `.env.example` files (backend + frontend)
- [ ] CI pipeline: lint + type-check + pytest + build
- [ ] DB backup script

**Exit criteria:** `docker compose up` → all services healthy; frontend renders shell; backend `/health` returns 200.

---

## Phase 1 — Core Loops (Weeks 4–8)

**Mục tiêu:** Users có thể đăng ký, login, đăng tin, nộp đơn. End-to-end flow hoạt động.

### Module 1: Authentication & Identity (M1)
- [ ] Email/password auth + JWT + refresh token
- [ ] VinUni OIDC/SAML SSO (VinUni students)
- [ ] 4 user tiers: VinUni Student / Alumni / External / General
- [ ] Email verification (magic link)
- [ ] Password reset
- [ ] Account lockout after 5 failed attempts

### Module 2: User Profiles (M2)
- [ ] Student profile: personal info, education, skills, languages, interests
- [ ] Profile completion % (real-time)
- [ ] Avatar upload
- [ ] Privacy settings (who can see what)
- [ ] Partner company profile: logo, description, industry, website, verified badge
- [ ] First partner registrant = admin (auto-grant all permissions)

### Module 3: CV Management (M3)
- [ ] CV upload (PDF, DOCX, images)
- [ ] AI CV extraction (background Celery task) — structured data from document
- [ ] Multiple CVs per student (max by tier)
- [ ] CV version history
- [ ] CV preview in-browser (PDF viewer)
- [ ] CV Studio manual template builder: blank template, profile import, uploaded CV import, duplicate existing CV
- [ ] CV Studio A4 preview, page-break warning, autosave, version restore
- [ ] CV Studio PDF export v1
- [ ] Immutable application CV snapshot for both uploaded CVs and builder CVs
- [ ] CV download by partner: watermark (partner name + timestamp)

### Module 5: Partner RBAC (M5)
- [ ] Custom roles (free naming, no hardcoded)
- [ ] Departments
- [ ] Permission matrix: resource × action
- [ ] Invite member by email
- [ ] Member role/department assignment
- [ ] Permission check at service layer

### Module 6: Job Posting Basic (M6)
- [ ] Post job: title, description, requirements, salary, deadline, location
- [ ] Job type: full-time, part-time, internship, remote
- [ ] Job visibility: Public (Phase 1) — other levels in Phase 2
- [ ] Job status: draft → pending review → active → closed
- [ ] University moderation queue (simple, Phase 1: manual only)
- [ ] Job expire notification (D-3)

### Module 9: Application Flow (M9)
- [ ] Student apply to job (single CV selection)
- [ ] Application status: submitted → reviewing → interviewing → offer → rejected
- [ ] Application history per student
- [ ] Withdraw application
- [ ] Partner: view applications list, update status
- [ ] Basic notification: email on status change

### Module 22: Notifications Basic (M22)
- [ ] In-app notification center
- [ ] Email notifications: application status, interview invite, job deadline
- [ ] Mark read / mark all read
- [ ] Notification preferences per user

### Dashboards Basic
- [ ] Student dashboard: stats cards + recent applications + upcoming interviews
- [ ] Partner dashboard: stats cards + recent applications list
- [ ] University dashboard: basic stats

**Exit criteria:** Student can register via SSO, upload CV, apply to job; Partner can post job and view applications.

---

## Phase 2 — Advanced Hiring Flows (Weeks 9–14)

**Mục tiêu:** Multi-round pipeline, advanced job settings, talent pool.

### Module 7: Multi-round Interview Pipeline (M7) ⭐
- [ ] Pipeline template: create/edit/delete named stages
- [ ] Per-job pipeline configuration at posting time
- [ ] Stage types: HR screen, technical test, interview, assessment, reference check
- [ ] Assignee: department or specific person
- [ ] Required action per stage: scorecard / score threshold / manual advance
- [ ] SLA per stage (hours)
- [ ] Auto-advance on SLA (optional)
- [ ] Candidate visibility toggle (what student sees per stage)
- [ ] Custom email template per stage transition
- [ ] Rollback to any previous stage (with reason, min 20 chars)
- [ ] Pipeline kanban view
- [ ] SLA overdue alerts (red in kanban)
- [ ] Scorecard per stage (custom questions, rating scales)
- [ ] Bulk actions: advance / reject multiple candidates

### Module 8: Job Posting Advanced (M8) ⭐
- [ ] 5 visibility levels: Public / Authenticated / Students Only / VinUni Students Only / Invitation Only
- [x] ~~Anonymous apply toggle / reveal handshake~~ **REMOVED product-wide (owner decision 2026-07-10)** — applications are always identified; CV access stays RBAC-gated + watermarked + audited
- [ ] Job posting permissions: partner admin can restrict posting to specific departments only
- [ ] Job referral tracking (ref= query param)
- [ ] Auto-close when quota filled
- [ ] Job duplication (clone existing job)
- [ ] Pipeline templates library (reuse across jobs)

### Module 11: Talent Pool & Shortlisting (M11)
- [ ] Add candidate to talent pool (from any source)
- [ ] Talent pool lists (custom named)
- [ ] Notes per candidate in pool
- [ ] Tag candidates
- [ ] Bulk add to job pipeline

### Module 12: Talent Pool — AI Semantic Candidate Discovery (M12) ⭐
> Reframed by owner decision 2026-07-10: AI semantic search, not anonymized cards.
> Contract: `docs/PARTNER_RBAC_ANALYTICS_SPEC.md` + `docs/AI_PRODUCT_SPEC.md` §3.3.
- [ ] Student opt-in: "Cho phép doanh nghiệp tìm kiếm hồ sơ của tôi" (opt-out ⇒ removed from index, not masked)
- [ ] pgvector embeddings over consented candidate CVs + refresh on active-CV change
- [ ] Semantic search + structured filters (skills, experience, major, cohort, location/work-mode, availability, tier)
- [ ] LLM rerank returning human-readable match reasons + evidence gaps (no raw similarity exposed)
- [ ] **External-JD search**: paste/upload a JD not yet posted → find matching candidates
- [ ] Candidates shown identified to authorized recruiters; CV view/download via `candidate_access` RBAC + watermark + audit
- [ ] Deterministic keyword+filter fallback when AI/embeddings unavailable
- [ ] Partner sends contact request → student approves/declines
- [ ] Anti-spam quota (max requests per partner per day/week)
- [ ] Student notification: X doanh nghiệp đã xem hồ sơ của bạn

### Module 13: Company Reviews (M13)
- [ ] Student submits review (star rating + text categories)
- [ ] Eligibility: interviewed or worked at company
- [ ] Anonymous option
- [ ] AI-assisted moderation (flag inappropriate)
- [ ] Partner can respond publicly
- [ ] University can remove violating reviews
- [ ] Rating display on company profile

### Module 19: Excel Export (M19)
- [ ] Export modal: field selection UI
- [ ] Presets: save/load per user
- [ ] Export types: Applications, CVs, Job listings, Pipeline stages, Talent pool, Interviews
- [ ] Sync export for < 1,000 rows; async + download link for > 1,000 rows
- [ ] Data includes only fields user has permission to see

### University RBAC (M5-like)
- [ ] Same configurable model as Partner RBAC
- [ ] Super Admin creates all roles/departments/permissions
- [ ] University permission resources (see university-domain-agent spec)

**Exit criteria:** Partner can configure 4-stage pipeline per job; student applies (always identified); partner runs AI semantic talent-pool search (incl. external-JD).

---

## Phase 3 — AI Intelligence (Weeks 15–20)

**Mục tiêu:** AI làm tăng đáng kể value cho mọi user. AI đi vào mọi feature quan trọng.

### AI Gateway (infra)
- [ ] Platform superadmin-only AI provider/model registry; ordinary university AI settings are masked governance controls only
- [ ] Provider adapter: OpenAI, Anthropic, Gemini, Ollama, OpenRouter
- [ ] Internal function-slot/task-type routing from DB config; non-superadmin views see only masked alias/status/budget fields
- [ ] Load balancer: round-robin, priority, health-weighted
- [ ] Fallback chain (provider A → B → C on error)
- [ ] Provider cost telemetry per task type + billable AI usage ledger per actor/org/session/resource
- [ ] Budget alerts
- [ ] Health monitoring dashboard: concrete provider/model identity superadmin-only; ordinary university views get derived status only
- [ ] Provider/model identity never exposed to students, partners, guests, exports, notifications, or ordinary university staff

### Module 4: AI Career Assistant (M4) ⭐
- [ ] Full-page chat UI
- [ ] 25+ tools: job search, apply, withdraw, profile update, CV tips, company info...
- [ ] Streaming response (SSE)
- [ ] Tool use cards in chat (visible tool execution)
- [ ] Write action confirmation (never auto-execute)
- [ ] Conversation history (per user, per session)
- [ ] Context-aware (reads user's profile, applications, CV)
- [ ] Guest: login modal when trying to use chat
- [ ] Proactive nudges: stale CV, missing preferences, application deadline approaching

### Module 10: AI Interview Simulator (M10) ⭐
- [ ] Job-specific or general practice mode
- [ ] Turn-by-turn: AI asks → student answers → AI gives per-answer feedback
- [ ] Question generation from JD + common patterns
- [ ] Feedback: content, clarity, confidence, what to improve
- [ ] Session summary: overall score + category breakdown
- [ ] Progress tracking across sessions
- [ ] Practice for specific company/role

### CV Intelligence (extends M3)
- [ ] AI CV analysis: score, strengths, improvement suggestions
- [ ] AI grammar/clarity checker for CV text
- [ ] Keyword optimization for ATS
- [ ] Missing skills detection vs. target role
- [ ] AI fills selected CV template from profile, uploaded CV extraction, existing CV, and raw notes
- [ ] AI CV builder: generate bullet points from user-provided raw experience
- [ ] AI CV rewrite/tailor suggestions are pending diffs with accept/edit/reject
- [ ] CV fabrication check: flags unsupported claims and requires student confirmation

### Job Intelligence (extends M6/M8)
- [ ] AI job description writer (for partners)
- [ ] AI JD bias detector (flags biased language)
- [ ] AI JD requirements validator (realistic? too restrictive?)
- [ ] AI job–CV match score for partners (shown in pipeline)
- [ ] AI job recommendation for students (homepage + email digest)

### Moderation AI (extends M20-University)
- [ ] AI content moderation for job posts
- [ ] AI partner document verification (human confirms)
- [ ] AI fraud detection (fake companies, fake applications)
- [ ] Human always has final say — AI is suggestion only
- [ ] Confidence shown in admin UI; low confidence items flagged for human

### Module 23: AI Settings (M23)
- [ ] Platform superadmin: add/remove/edit AI providers and concrete model bindings
- [ ] Platform superadmin: set model/fallback/rotation per internal task type
- [ ] University AI governance view: feature flags, budgets, masked alias handles, derived health, and limit requests only
- [ ] Superadmin AI cost dashboard (per task type, per day/month); ordinary university views never reveal provider/model identity
- [ ] Superadmin-only health probe/test prompt per provider/model; no prompt/response bodies stored
- [ ] AI audit log (what feature/task was called, by whom, charged to which scope, at what cost — no content)

### Module 32: Superadmin AI Provider Hub Visual Management (M32) ⭐
- [ ] Provider cards UI: real provider/model names visible only to platform superadmins, with status indicator, response time avg, monthly cost, models, tasks assigned
- [ ] Health check auto-runs every 60s; auto-skip unhealthy providers
- [ ] Priority mode: drag to reorder fallback chain
- [ ] Round-robin mode: weight sliders per provider
- [ ] Task-based routing: select provider per task_type via table UI
- [ ] "Test" button: send test prompt → show latency + sample output to superadmin only; prompt/response never persisted
- [ ] Cost cap per provider per day (auto-disable + alert on breach)

### Module 33: Document Knowledge Base / RAG (M33) ⭐
- [ ] University admin uploads platform KB docs (PDF/DOCX/TXT, 50 MB/file, 5 GB total, 200 docs max)
- [ ] Partner admin uploads company KB + per-job KB (500 MB/org, 50 docs/org, 10 docs/job)
- [ ] Ingestion pipeline: virus scan → text extraction → paragraph-aware chunking → embedding → pgvector
- [ ] `knowledge_base_chunks` table with IVFFlat cosine index
- [ ] RAG query: scope resolution → embed query → top-K retrieval → inject context → answer with citations
- [ ] Mandatory source citations: document name + section (never expose file paths or chunk IDs)
- [ ] No-result graceful fallback (never hallucinate)
- [ ] Admin UI: doc list, status badge, preview, quota bar, delete
- [ ] Chatbot auto-scopes to relevant KB by page context (platform / company / job)

**Exit criteria:** Student can have full conversation with AI; complete 1 mock interview with feedback; partner can see AI match score in pipeline; university admin can upload policy doc and student can ask chatbot about it.

---

## Phase 4 — Events + Monetization (Weeks 21–27)

**Mục tiêu:** Revenue-generating features live; events system fully operational.

### Module 14: Events System (M14) ⭐
- [ ] Event CRUD: title, description, format (onsite/online/hybrid), capacity
- [ ] Multiple ticket types per event (name, price, capacity, eligibility tier)
- [ ] Early bird pricing + promo codes
- [ ] Seat map: import venue layout, assign sections
- [ ] Seat selection UI (interactive map)
- [ ] Seat lock mechanism (Redis TTL 10 min)
- [ ] Online link management (encrypted, visible only to confirmed registrants)
- [ ] Waitlist + auto-promotion when seat freed
- [ ] QR code generation per registration
- [ ] QR check-in (scan + verify identity)
- [ ] Paid ticket checkout via manual/bank transfer confirmation; VNPay/MoMo gateway adapters remain later-phase extension points
- [ ] Refund policy per ticket type
- [ ] Ticket transfer (if enabled)
- [ ] Post-event certificate PDF (auto-generated, emailed)
- [ ] Career Fair special: booth system, partner booths
- [ ] Hybrid: separate capacity for onsite vs online
- [ ] Event approval flow (university or partner-hosted)
- [ ] Export attendee list (Excel)

### Module 15: Partner Subscriptions & Packages (M15)
- [ ] Package tiers: posting quota, spotlight slots, passive search quota, email blasts
- [ ] University admin defines package names + features + prices
- [ ] Partner upgrades in billing section
- [ ] Auto-notify partner when quota 80% used
- [ ] Package history + invoices

### Module 16: Advertising System (M16)
- [ ] Banner ads: header, sidebar, email digest positions
- [ ] Sponsored job cards (amber "Được tài trợ" label — mandatory)
- [ ] Sponsored events
- [ ] Targeting: automatic allocation or manual targeting by surface, role/category, industry, location/region, graduation year, interests, and campaign objective — NEVER PII/health/religion/sensitive traits
- [ ] Ad campaign builder (partner)
- [ ] Creative upload (image/HTML)
- [ ] University approval before live, with workflow rules for auto-approve/hold/escalate to department or named reviewer
- [ ] Budget + bid setup with pacing, caps, fraud/risk checks, and spend guardrails
- [ ] Performance dashboard: impressions, clicks, CTR
- [ ] Invoice / revenue reporting

### Module 18: Student Subscriptions (M18)
- [ ] University admin creates packages (name, price, features, duration)
- [ ] Student purchases: AI credits, CV builder premium, priority apply
- [ ] Manual/bank transfer confirmation; payment gateway adapter later
- [ ] Subscription active until expiry date
- [ ] Tier-based limits enforced at service layer

### Excel Export — Phase 4 additions
- [ ] Export events + attendees
- [ ] Export ad campaign performance
- [ ] Export subscription revenue

**Exit criteria:** Partner can create paid event with seat selection; student can complete a manual-payment registration flow; sponsored job appears with mandatory label.

---

## Phase 4b — Real-time, Engagement & Advanced UX (Weeks 21–27, parallel with Phase 4)

**Mục tiêu:** Real-time communication, bulk workflows, and immersive partner UX. Can be built in parallel with Phase 4 events/monetization track.

### Module 25: In-app Institutional Messaging (M25) ⭐
- [ ] Partner → Student messaging (1:1 direct message from pipeline or profile)
- [ ] University → Student/Partner broadcast or direct message
- [ ] **Student → Student: NEVER ALLOWED** (enforced at service layer)
- [ ] Messages table with thread model (message_threads, messages, message_reads)
- [ ] Slide-in panel UI (380px, fixed right)
- [ ] Real-time delivery via WebSocket (Redis Pub/Sub multi-worker fan-out)
- [ ] Unread badge in nav
- [ ] Per-day rate limit: 50 messages per sender per recipient
- [ ] Message content moderation (AI-flagged, human review)

### Module 26: Visual Workflow Builder (M26)
- [ ] React Flow (@xyflow/react) canvas for building automation flows
- [ ] Node types: trigger, action, condition, wait, loop
- [ ] DAG validation (no cycles) at save time — frontend + backend
- [ ] Max 50 nodes per flow
- [ ] Flow states: DRAFT → TEST → ACTIVE; only 1 ACTIVE version per flow name
- [ ] Celery execution engine: polls active flows, executes step-by-step
- [ ] Test mode: dry run with sample data, shows step-by-step trace
- [ ] Execution history with per-step status overlay on canvas
- [ ] Partner-visible flows only (no student-created automation)

### Module 27: Bulk Apply / Job Cart (M27)
- [ ] Job Cart: add up to 20 jobs before applying
- [ ] Cart badge in navbar
- [ ] Apply all cart items: select CV per job, preview cover letter
- [ ] AI cover letter generation per job (CV × JD × company context)
- [ ] Partial apply: apply what quota allows, show clear success/failure per job
- [ ] Weekly apply quota per tier (enforced at service layer)
- [ ] Cover letter saved in application record

### Module 28: Real-time Presence & Activity Audit (M28)
- [ ] Online presence: green dot on user avatar (Redis sorted set, TTL 90s)
- [ ] Heartbeat from frontend every 30s
- [ ] Activity feed: real-time stream of audit events for admins/partners
- [ ] WebSocket push for new audit events (partner feed + university feed)
- [ ] Framer Motion animations for activity feed items
- [ ] Audit log viewer: filter by action type, date range, actor

### Module 29: Video Interview Integration (M29)
- [ ] Interview type selector: "Video" when scheduling
- [ ] Auto-generate meeting link (Google Meet or Zoom via API) on schedule
- [ ] Meeting link in interview detail for both parties
- [ ] One-click join button (no copy-paste)
- [ ] Optional recording toggle (dual consent required)
- [ ] Consent prompt to candidate before joining if recording enabled
- [ ] Video provider configurable per university (ai_settings)
- [ ] Recording auto-expires after 30 days

### Module 30: Smart Reminders & Enhanced Push (M30)
- [ ] Web Push (VAPID) subscription with explicit permission request
- [ ] Service Worker + PWA manifest
- [ ] Student reminders: interview (24h + 1h), deadline (3d + 1d)
- [ ] Partner alerts: new applications batch, SLA overdue, subscription expiring
- [ ] University alerts: moderation queue > SLA threshold
- [ ] Do Not Disturb: user sets quiet hours
- [ ] Notification preference settings per category + per channel (in-app / email / push)
- [ ] Weekly job match digest email (Tuesday 9am batch job)

### Module 31: Partner Flexible Dashboard (M31)
- [ ] 12-column widget grid layout
- [ ] Drag-to-reorder widgets (@dnd-kit sortable)
- [ ] Widget size selector: S / M / L
- [ ] Add/remove widgets from catalog
- [ ] Layout saved per user (Zustand persist → backend sync)
- [ ] Reset to default layout
- [ ] Widgets: Pipeline Summary (Kanban mini), Quick Stats, Upcoming Interviews (7-day), Quota Usage (with upgrade CTA)
- [ ] Mobile: single column, stack vertically

**Exit criteria:** Partner can send student a message and it arrives in real time; student can add 5 jobs to cart and apply in one action; partner dashboard has draggable widgets; push notification fires on new application.

---

## Phase 5 — Mentorship, Alumni & University Intelligence (Weeks 28–36)

**Mục tiêu:** Long-term platform stickiness + university reporting + accreditation support.

### Module 17: Mentorship Program (M17)
- [ ] Alumni register as mentor (skill tags, availability, limit)
- [ ] Student browse mentors (search by skill, industry)
- [ ] Mentorship request + accept/decline
- [ ] Session scheduling (integrated calendar)
- [ ] Session notes (private to pair)
- [ ] Progress tracking per student
- [ ] University overview: mentorship engagement stats

### Module 21: Alumni Network (M21)
- [ ] Alumni directory (searchable, with privacy control)
- [ ] Alumni profile: graduation year, current role, company, city
- [ ] Connection requests (LinkedIn-like)
- [ ] Alumni feed: posts, milestones, job shares
- [ ] Alumni job referrals (internal to platform)
- [ ] Alumni mentorship auto-enroll option

### Module 20: Career Outcomes & University Intelligence (M20) ⭐
- [ ] Placement tracking per graduate
- [ ] Post-graduation surveys (3 / 6 / 12 months post-grad)
- [ ] KPI dashboard: placement rate, avg salary, time-to-hire, by department/major
- [ ] Accreditation report generator (ABET, AUN-QA templates)
- [ ] Curriculum intelligence: which skills employers demand vs what courses teach
- [ ] Faculty dashboard (read-only): their department's career outcomes

### Module 24: VinUni Integrations (M24) ⭐
- [ ] VinUni SIS sync: enrollment status, graduation date, major, GPA (read-only)
- [ ] VinUni IdP OIDC/SAML: SSO setup + attribute mapping
- [ ] Academic calendar API: job alert timing, internship suggest timing
- [ ] Faculty dashboard: read-only placement stats by course/department
- [ ] SIS → platform: auto-update student tier on enrollment change (graduated = Alumni)

### Module 10 Advanced: Interview Simulator Enhancements
- [ ] Video answer recording (optional)
- [ ] AI sentiment + body language hints (for video)
- [ ] Company-specific question banks (from real partner input)
- [ ] Peer practice mode (2 students practice together)

### Reporting & Analytics
- [ ] Advanced analytics: funnel analysis, cohort retention, A/B test framework
- [ ] Partner analytics: application source attribution, time-in-stage analysis
- [ ] University reports: weekly digest email to admins, monthly PDF export

**Exit criteria:** University admin generates accreditation report from real data; alumni network has profiles + mentorship connections; SIS sync auto-upgrades graduated students to Alumni tier.

---

## Ongoing (All phases)

| Track | Cadence |
|-------|---------|
| Security audit | Every phase end |
| Performance review (LCP, API p99) | Monthly |
| Accessibility audit (WCAG 2.1 AA) | Every phase end |
| AI prompt quality review | Monthly |
| AI cost review | Monthly |
| User feedback review | Weekly |
| Dependency updates | Monthly |
| Backup & recovery drill | Quarterly |

---

## Timeline Summary

| Phase | Duration | ROADMAP Modules | Key Deliverable |
|-------|----------|-----------------|-----------------|
| 0 — Foundation | Weeks 1–3 | (scaffold only) | Dev environment, CI, design system |
| 1 — Core Loops | Weeks 4–8 | M1, M2, M3, M5, M6, M9, M22 + Dashboards | Working end-to-end: register → upload CV → apply → review pipeline |
| 2 — Advanced Hiring | Weeks 9–14 | M7, M8, M11, M12, M13, M19 + University RBAC | Multi-round pipeline, passive search, advanced jobs, talent pool |
| 3 — AI Intelligence | Weeks 15–20 | M4, M10, M23, M32, M33 + CV/Job AI extensions | AI chat, interview sim, CV intelligence, RAG knowledge base |
| 4 — Events + Monetization | Weeks 21–27 | M14, M15, M16, M18 | Event ticketing, advertising, subscriptions |
| 4b — Real-time & UX | Weeks 21–27 | M25, M26, M27, M28, M29, M30, M31 | Messaging, bulk apply, workflow builder, push notifications |
| 5 — University Intelligence | Weeks 28–36 | M17, M20, M21, M24 | Alumni, mentorship, career outcomes, SIS |

> Timelines assume 1 full-stack team (2–3 engineers + 1 AI engineer). Phase 4 and 4b can run in parallel with separate tracks. Adjust for team size.

---

## Module ID Legend

ROADMAP module IDs (M1–M33) are ordered by **delivery priority** and differ from PRD MODULE 1–24 which are ordered by **feature group**.

| ROADMAP ID | ROADMAP Name | PRD Module |
|------------|--------------|------------|
| M1 | Authentication & Identity | MODULE 1 |
| M2 | User Profiles | MODULE 3 |
| M3 | CV Management | MODULE 4 |
| M4 | AI Career Assistant | MODULE 9 |
| M5 | Partner RBAC | Part of MODULE 18 |
| M6 | Job Posting Basic | Part of MODULE 5 |
| M7 | Multi-round Interview Pipeline | MODULE 7 |
| M8 | Job Posting Advanced | MODULE 8 |
| M9 | Application Flow | MODULE 6 |
| M10 | AI Interview Simulator | MODULE 10 |
| M11 | Talent Pool & Shortlisting | Part of MODULE 11 |
| M12 | Passive Talent Discovery | MODULE 12 |
| M13 | Company Reviews | MODULE 15 |
| M14 | Events System | MODULE 14 |
| M15 | Partner Subscriptions & Packages | Part of MODULE 18 |
| M16 | Advertising System | MODULE 13 |
| M17 | Mentorship Program | Part of MODULE 17 |
| M18 | Student Subscriptions | Part of MODULE 2.3 |
| M19 | Excel Export | MODULE 19 |
| M20 | Career Outcomes & University Intelligence | MODULE 20 |
| M21 | Alumni Network | Part of MODULE 17 |
| M22 | Notifications Basic | MODULE 21 |
| M23 | AI Settings (admin) | Part of MODULE 2.4 |
| M24 | VinUni Integrations | MODULE 24 |
| M25 | In-app Institutional Messaging | Not explicitly in PRD (derived from BUSINESS_LOGIC.md) |
| M26 | Visual Workflow Builder | Not in PRD v5.0 (planned for Phase 4b) |
| M27 | Bulk Apply / Job Cart | Not explicitly in PRD (derived from MODULE 5) |
| M28 | Real-time Presence & Activity Audit | Not explicitly in PRD |
| M29 | Video Interview Integration | Part of MODULE 22 |
| M30 | Smart Reminders & Enhanced Push | Part of MODULE 21 |
| M31 | Partner Flexible Dashboard | Part of Dashboard specs |
| M32 | AI Provider Hub Visual Management | Part of MODULE 2.4 |
| M33 | Document Knowledge Base / RAG | Not in PRD v5.0 (added via AI_PRODUCT_SPEC.md) |

> M25–M33 are extensions derived from PRD feature descriptions, BUSINESS_LOGIC.md, and AI_PRODUCT_SPEC.md. They are not explicitly numbered in PRD v5.0 but represent distinct engineering modules.
