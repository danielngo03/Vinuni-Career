# Product Backlog — VinUni Career Platform

> Phiên bản: 4.2 | Cập nhật: 04/07/2026
> Nguồn sự thật duy nhất cho product priorities.
> Format ID: B-{number} | Priorities: P0 (must-have) / P1 (high) / P2 (medium) / P3 (nice-to-have)

---

## Epics

| ID | Epic | Phase |
|----|------|-------|
| E1 | Foundation & Infrastructure | 0 |
| E2 | Authentication & Identity | 1 |
| E3 | User Profiles & CV Management | 1 |
| E4 | Partner RBAC & Organization | 1–2 |
| E5 | Job Posting & Discovery | 1–2 |
| E6 | Application Flow | 1 |
| E7 | Multi-round Pipeline Engine | 2 |
| E8 | Talent Pool & Passive Search | 2 |
| E9 | AI Career Assistant | 3 |
| E10 | AI Interview Simulator | 3 |
| E11 | AI Job & CV Intelligence | 3 |
| E12 | Events System | 4 |
| E13 | Subscriptions & Packages | 4 |
| E14 | Advertising System | 4 |
| E15 | Mentorship & Alumni | 5 |
| E16 | Career Outcomes & University Intelligence | 5 |
| E17 | VinUni Integrations | 5 |
| E18 | Excel Export & Reporting | 2–5 |
| E19 | Company Reviews | 2 |
| E20 | University Moderation & Governance | 1–5 |
| E21 | Notifications | 1–3 |
| E33 | Partner RBAC & Recruiting Intelligence | 2–4 |
| E34 | Visual CV Studio & Template Operations | 1–3 |
| E35 | Student Job Fit & Competition Intelligence | 2–3 |
| E36 | Platform Reality Hardening & Data Quality | 1–5 |

---

## E1 — Foundation & Infrastructure

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-001 | Backend scaffold: FastAPI + SQLAlchemy + Alembic + Redis | P0 | 0 |
| B-002 | Celery worker setup with Redis broker | P0 | 0 |
| B-003 | AI Gateway router skeleton (no providers yet) | P0 | 0 |
| B-004 | Frontend scaffold: Next.js 15 + TypeScript strict + Tailwind v4 | P0 | 0 |
| B-005 | next-intl setup (vi + en) + locale routing | P0 | 0 |
| B-006 | Design system: CSS custom properties (colors, typography, spacing) | P0 | 0 |
| B-007 | Base UI components: Button, Input, Card, Badge, Modal, Toast, Skeleton | P0 | 0 |
| B-008 | Persona shells: public top nav, student signed-in marketplace top nav, partner/university ops sidebar + topbar | P0 | 0 |
| B-009 | Docker Compose: all services (postgres, redis, backend, frontend) | P0 | 0 |
| B-010 | CI pipeline: lint + type-check + pytest + Next.js build | P0 | 0 |
| B-011 | Shared audit log table + writer utility | P0 | 0 |
| B-012 | Shared RBAC permission checker (service layer) | P0 | 0 |
| B-013 | Outbox events table + processor | P1 | 0 |
| B-014 | Dark mode toggle (CSS custom property swap) | P1 | 0 |
| B-015 | PWA manifest + service worker (offline cache) | P2 | 5 |

---

## E2 — Authentication & Identity

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-020 | Email/password registration with email verification | P0 | 1 |
| B-021 | JWT access token (15 min) + refresh token (7 days) | P0 | 1 |
| B-022 | Token revocation via Redis JTI set | P0 | 1 |
| B-023 | VinUni OIDC/SAML SSO (VinUni students) | P0 | 1 |
| B-024 | User tier assignment: VinUni Student / Alumni / External / General | P0 | 1 |
| B-025 | Password reset (magic link, 1-hour expiry) | P0 | 1 |
| B-026 | Account lockout after 5 failed login attempts | P0 | 1 |
| B-027 | Partner registration: company info + first registrant = admin | P0 | 1 |
| B-028 | University staff login (separate from student login) | P0 | 1 |
| B-029 | Google OAuth for External/General users | P1 | 1 |
| B-030 | 2FA (TOTP) for university admin accounts | P1 | 2 |
| B-031 | Session device list + remote logout | P2 | 3 |

---

## E3 — User Profiles & CV Management

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-040 | Student profile: personal info, education, skills, languages | P0 | 1 |
| B-041 | Profile completion percentage (real-time, drives recommendation quality) | P0 | 1 |
| B-042 | Avatar upload (crop + resize) | P1 | 1 |
| B-043 | Privacy settings: who can see profile, opt-in to passive search | P0 | 1 |
| B-044 | CV upload: PDF/DOCX/images, max by tier | P0 | 1 |
| B-045 | AI CV extraction (Celery task, structured fields) | P0 | 1 |
| B-046 | Multiple CVs per student (version management) | P1 | 1 |
| B-047 | CV version history + restore | P2 | 2 |
| B-048 | CV preview in-browser (PDF.js or iframe) | P1 | 1 |
| B-049 | CV download by partner: watermark (partner name + timestamp) | P0 | 1 |
| B-050 | Partner company profile: logo, description, industry, website, verified badge | P0 | 1 |
| B-051 | Company page (public): logo, about, jobs, reviews, events | P1 | 1 |
| B-052 | AI CV analysis: score, strengths, improvement suggestions | P1 | 3 |
| B-053 | AI grammar/clarity checker for CV text | P2 | 3 |
| B-054 | AI keyword optimization: ATS compatibility tips | P1 | 3 |
| B-055 | CV Studio template builder: blank/profile/uploaded import, duplicate existing CV, section editor | P0 | 1 |
| B-056 | CV Studio AI: fill template, generate bullets, rewrite, tailor to job with pending diff | P1 | 3 |
| B-057 | Portfolio links: GitHub, Behance, personal website | P2 | 2 |
| B-058 | Skills endorsement (from alumni/mentor connections) | P3 | 5 |
| B-059 | Immutable application CV snapshot for uploaded CVs and builder CV versions | P0 | 1 |

---

## E4 — Partner RBAC & University RBAC

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-060 | Partner: create custom roles (free naming, no hardcoded) | P0 | 1 |
| B-061 | Partner: create departments | P0 | 1 |
| B-062 | Partner: assign permissions (resource × action matrix) | P0 | 1 |
| B-063 | Partner: invite member by email | P0 | 1 |
| B-064 | Partner: assign member to roles + departments | P0 | 1 |
| B-065 | Partner: RBAC permission check at service layer (not just router) | P0 | 1 |
| B-066 | Partner: restrict job posting to specific departments only | P0 | 2 |
| B-067 | University: Super Admin creates roles, departments, permissions (fully configurable) | P0 | 1 |
| B-068 | University: invite staff by email | P0 | 1 |
| B-069 | University: staff role/department management | P0 | 1 |
| B-070 | University: staff has same configurable model as partner RBAC | P0 | 1 |
| B-071 | Partner admin: transfer admin to another member | P1 | 2 |
| B-072 | Audit log for RBAC changes (who changed what role when) | P0 | 1 |

---

## E5 — Job Posting & Discovery

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-080 | Post job: title, description, requirements, salary, deadline, location | P0 | 1 |
| B-081 | Job type: full-time / part-time / internship / remote | P0 | 1 |
| B-082 | Job status workflow: draft → pending review → active → closed | P0 | 1 |
| B-083 | Job visibility level 1: Public (guest-accessible) | P0 | 1 |
| B-084 | Job visibility levels 2–5: Authenticated / Students Only / VinUni Only / Invitation Only | P0 | 2 |
| B-085 | Invitation-only job: partner sends invite to specific users/emails | P1 | 2 |
| B-086 | Anonymous apply toggle per job (partner setting) | P0 | 2 |
| B-087 | Anonymous apply: student chooses at apply time | P0 | 2 |
| B-088 | University admin: configure which fields hidden in anonymous apply | P0 | 2 |
| B-089 | Partner: request reveal anonymous applicant (with reason, needs student approval) | P1 | 2 |
| B-090 | Job duplication (clone with new deadline) | P1 | 2 |
| B-091 | Auto-close job when application quota filled | P1 | 2 |
| B-092 | Job expire D-3 / D-1 notifications to partner | P1 | 1 |
| B-093 | Job referral tracking (ref= query param → attribution) | P2 | 2 |
| B-094 | Guest: view Public jobs without login; all actions → login modal | P0 | 1 |
| B-095 | Job search: keyword, location, type, salary range, category | P0 | 1 |
| B-096 | Job filters: experience level, skills, posted date, remote | P1 | 1 |
| B-097 | Save/bookmark job (student) | P1 | 1 |
| B-098 | AI-powered job recommendations (student homepage + email digest) | P1 | 3 |
| B-099 | AI JD writer for partners | P1 | 3 |
| B-100 | AI JD bias detector (flags gendered/ageist/elitist language) | P1 | 3 |
| B-101 | AI JD requirements validator (overly restrictive detection) | P2 | 3 |
| B-102 | Sponsored job (promoted, amber label — non-removable) | P0 | 4 |

---

## E6 — Application Flow

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-110 | Student applies: select CV, optional cover letter | P0 | 1 |
| B-111 | Application confirmation email to student | P0 | 1 |
| B-112 | Duplicate application prevention (same job) | P0 | 1 |
| B-113 | Student: view all applications with status + timeline | P0 | 1 |
| B-114 | Student: withdraw application (before certain stage) | P1 | 1 |
| B-115 | Partner: view applications list per job (sortable, filterable) | P0 | 1 |
| B-116 | Partner: view application detail (CV + profile) | P0 | 1 |
| B-117 | Partner: update application status manually | P0 | 1 |
| B-118 | Application status email notification to student on change | P0 | 1 |
| B-119 | Mass apply to multiple jobs (Phase 3 with AI validation) | P2 | 3 |
| B-120 | AI match score shown to partner in application list | P1 | 3 |
| B-121 | Application source tracking (direct / referral / passive / invitation) | P1 | 2 |

---

## E7 — Multi-round Pipeline Engine

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-130 | Pipeline template: create named stages (free name, type, order) | P0 | 2 |
| B-131 | Pipeline template library: save and reuse across jobs | P1 | 2 |
| B-132 | Per-job pipeline config at posting time (select or create template) | P0 | 2 |
| B-133 | Stage assignee: department or specific person | P0 | 2 |
| B-134 | Required action per stage: scorecard / score threshold / manual | P0 | 2 |
| B-135 | SLA per stage (hours, optional) | P1 | 2 |
| B-136 | Auto-advance on SLA completion (optional toggle per stage) | P2 | 2 |
| B-137 | Candidate visibility toggle per stage (what student sees) | P1 | 2 |
| B-138 | Custom email template per stage transition | P1 | 2 |
| B-139 | Stage transition: advance candidate to next stage | P0 | 2 |
| B-140 | Stage transition: reject candidate (with rejection reason + email) | P0 | 2 |
| B-141 | Rollback to any previous stage (with reason, min 20 chars) | P0 | 2 |
| B-142 | Pipeline kanban view (column per stage, cards per candidate) | P0 | 2 |
| B-143 | SLA overdue indicator (red in kanban column header) | P1 | 2 |
| B-144 | Scorecard per stage: custom questions, rating scales, text notes | P0 | 2 |
| B-145 | Bulk actions: advance or reject multiple candidates at once | P1 | 2 |
| B-146 | Pipeline analytics: avg time per stage, drop-off rate per stage | P1 | 3 |
| B-147 | All pipeline transitions logged in audit trail | P0 | 2 |
| B-148 | Student view: which stage they're in (if candidate_notify enabled) | P1 | 2 |

---

## E8 — Talent Pool & Passive Search

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-150 | Partner: create talent pool lists (named) | P0 | 2 |
| B-151 | Add candidate to talent pool from any source | P0 | 2 |
| B-152 | Tag candidates in talent pool | P1 | 2 |
| B-153 | Notes per candidate in pool | P1 | 2 |
| B-154 | Bulk-add talent pool candidates to job pipeline | P1 | 2 |
| B-155 | Student: opt-in to passive search visibility | P0 | 2 |
| B-156 | Passive search: profiles anonymized (name/email hidden) by default | P0 | 2 |
| B-157 | Partner passive search: filter by skills, tier, GPA range, availability | P0 | 2 |
| B-158 | Semantic search via pgvector embeddings | P1 | 2 |
| B-159 | Partner sends contact request with message | P0 | 2 |
| B-160 | Student receives contact request: accept / decline | P0 | 2 |
| B-161 | Reveal profile info only after student accepts | P0 | 2 |
| B-162 | Anti-spam quota: max contact requests per partner per day/week | P0 | 2 |
| B-163 | Student: "X doanh nghiệp đã xem hồ sơ của bạn" notification | P1 | 2 |

---

## E9 — AI Career Assistant

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-170 | Full-page chat UI (streaming SSE) | P0 | 3 |
| B-171 | Conversation history per user (stored, searchable) | P1 | 3 |
| B-172 | Tool: search jobs by criteria | P0 | 3 |
| B-173 | Tool: view job details | P0 | 3 |
| B-174 | Tool: apply to job (with explicit user confirmation) | P1 | 3 |
| B-175 | Tool: withdraw application (with confirmation) | P1 | 3 |
| B-176 | Tool: view my applications list | P1 | 3 |
| B-177 | Tool: analyze my CV | P1 | 3 |
| B-178 | Tool: update profile field (with confirmation) | P1 | 3 |
| B-179 | Tool: check upcoming interviews | P1 | 3 |
| B-180 | Tool: search companies | P1 | 3 |
| B-181 | Tool: get company review summary | P1 | 3 |
| B-182 | Tool: get career advice (goal-based) | P2 | 3 |
| B-183 | Tool: simulate interview question for given role | P2 | 3 |
| B-184 | Tool: search events | P2 | 3 |
| B-185 | Tool: register for event (with confirmation) | P2 | 3 |
| B-186 | Tool: get salary market data | P2 | 3 |
| B-187 | Write-action confirmation card (never auto-execute) | P0 | 3 |
| B-188 | Tool use card: visible in chat with expand/collapse | P1 | 3 |
| B-189 | Guest: AI chat triggers login modal (preserves message intent) | P0 | 3 |
| B-190 | Proactive nudges: stale CV, missing preferences, deadline approaching | P2 | 3 |
| B-191 | Partner AI assistant: search candidates, get pipeline summary | P2 | 3 |

---

## E10 — AI Interview Simulator

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-200 | Job-specific or general practice mode selection | P0 | 3 |
| B-201 | Question generation from JD or common patterns | P0 | 3 |
| B-202 | Turn-by-turn: AI asks → student answers text → AI feedback per answer | P0 | 3 |
| B-203 | Per-answer feedback: content, clarity, what to improve | P0 | 3 |
| B-204 | Session summary: overall score + category breakdown chart | P0 | 3 |
| B-205 | Progress tracking: score trend across sessions | P1 | 3 |
| B-206 | Practice for specific company: uses company's known question patterns | P2 | 5 |
| B-207 | Video answer recording (optional) | P3 | 5 |
| B-208 | Peer practice mode (2 students, turn-based) | P3 | 5 |

---

## E11 — AI Job & CV Intelligence

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-210 | AI job–CV match score (shown to partner in pipeline) | P1 | 3 |
| B-211 | AI job recommendations for student (homepage) | P1 | 3 |
| B-212 | AI weekly job digest email (personalized) | P2 | 3 |
| B-213 | AI missing skills detection: what student needs for target role | P1 | 3 |
| B-214 | AI fraud detection: fake companies, fake CVs, fake applications | P1 | 3 |
| B-215 | AI sentiment analysis on company reviews | P2 | 3 |

---

## E12 — Events System

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-220 | Event CRUD: title, description, format (onsite/online/hybrid), capacity | P0 | 4 |
| B-221 | Multiple ticket types: name, price, capacity, eligibility by user tier | P0 | 4 |
| B-222 | Early bird pricing (price + deadline) | P1 | 4 |
| B-223 | Promo codes (% or flat discount, usage limit) | P1 | 4 |
| B-224 | Seat map: define venue layout (rows, sections, seats) | P0 | 4 |
| B-225 | Seat selection UI: interactive map (click to select) | P0 | 4 |
| B-226 | Seat lock mechanism: Redis TTL 10 min while in checkout | P0 | 4 |
| B-227 | Online link management: encrypted, visible only after confirmed registration | P0 | 4 |
| B-228 | Waitlist: auto-promote when seat/ticket freed | P1 | 4 |
| B-229 | QR code generation per registration (unique token) | P0 | 4 |
| B-230 | QR check-in: scan → verify identity → mark attended | P0 | 4 |
| B-231 | Paid ticket checkout: VNPay / MoMo gateway | P1 | 4 |
| B-232 | Refund policy per ticket type (no refund / partial / full before date) | P1 | 4 |
| B-233 | Ticket transfer to another user (if enabled) | P2 | 4 |
| B-234 | Post-event certificate PDF auto-generated and emailed | P1 | 4 |
| B-235 | Career Fair: booth system, partner booth registration | P2 | 4 |
| B-236 | Hybrid events: separate onsite/online capacity tracks | P0 | 4 |
| B-237 | Event approval flow (university moderates partner-hosted events) | P0 | 4 |
| B-238 | Guest: view Public events without login; register → login modal | P0 | 4 |
| B-239 | Export attendee list to Excel | P1 | 4 |
| B-240 | Event analytics: registrations by day, check-in rate, no-shows | P1 | 4 |
| B-241 | Sponsored event label ("Nhà tài trợ" — mandatory amber badge) | P0 | 4 |
| B-242 | University creates events (independent of partner) | P1 | 4 |
| B-243 | Multiple hosts per event (partner + university co-host) | P2 | 4 |

---

## E13 — Subscriptions & Packages

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-250 | Partner packages: university admin creates tiers (name, price, features) | P0 | 4 |
| B-251 | Package features: posting quota, spotlight slots, passive search quota, email blasts | P0 | 4 |
| B-252 | Partner upgrade in billing section | P0 | 4 |
| B-253 | Auto-notify partner at 80% quota usage | P1 | 4 |
| B-254 | Package history + invoice download | P1 | 4 |
| B-255 | Student subscription packages: university admin creates (name, price, features, duration) | P1 | 4 |
| B-256 | Student buys subscription: VNPay / MoMo payment | P1 | 4 |
| B-257 | Student subscription limits enforced at service layer | P0 | 4 |
| B-258 | Subscription active/expired status shown in student profile | P1 | 4 |
| B-259 | Revenue dashboard for university admin (MRR, churn, active subs) | P1 | 4 |

---

## E14 — Advertising System

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-260 | Ad positions: banner header, sidebar, email digest | P0 | 4 |
| B-261 | Sponsored job cards (must have "Được tài trợ" amber label) | P0 | 4 |
| B-262 | Sponsored events | P1 | 4 |
| B-263 | Ad targeting: role, interest, graduation year (NEVER PII/health/religion) | P0 | 4 |
| B-264 | "Tại sao tôi thấy quảng cáo này?" explanation (non-PII only) | P0 | 4 |
| B-265 | Ad campaign builder (partner): creative upload, targeting, budget, bid | P0 | 4 |
| B-266 | University approval before ad goes live | P0 | 4 |
| B-267 | Ad performance dashboard: impressions, clicks, CTR | P1 | 4 |
| B-268 | User can dismiss ad (records dismissal, reduces frequency) | P1 | 4 |
| B-269 | Ad frequency cap per user | P1 | 4 |
| B-270 | University revenue from ads (invoicing, reconciliation) | P1 | 4 |

---

## E15 — Mentorship & Alumni

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-280 | Alumni register as mentor: skills, availability, max mentees | P0 | 5 |
| B-281 | Student browse mentors: search by skill, industry, role | P0 | 5 |
| B-282 | Mentorship request: student sends → mentor accepts/declines | P0 | 5 |
| B-283 | Session scheduling (integrated with calendar) | P1 | 5 |
| B-284 | Session notes (private to mentorship pair) | P1 | 5 |
| B-285 | Progress tracking per student mentorship journey | P2 | 5 |
| B-286 | University mentorship engagement stats | P2 | 5 |
| B-287 | Alumni directory: searchable, privacy control | P0 | 5 |
| B-288 | Alumni profile: graduation year, current role, company, city | P0 | 5 |
| B-289 | Connection requests between users | P2 | 5 |
| B-290 | Alumni feed: posts, milestones, job shares | P2 | 5 |
| B-291 | Alumni job referral (internal) | P2 | 5 |
| B-292 | Skills endorsement between connections | P3 | 5 |
| B-293 | Auto-upgrade student to Alumni tier on graduation (SIS trigger) | P1 | 5 |

---

## E16 — Career Outcomes & University Intelligence

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-300 | Placement tracking per graduate: company, role, salary (with consent) | P0 | 5 |
| B-301 | Post-graduation surveys: 3 / 6 / 12 months | P0 | 5 |
| B-302 | Survey automated email cadence | P1 | 5 |
| B-303 | KPI dashboard: placement rate, avg salary, time-to-hire, by dept/major | P0 | 5 |
| B-304 | Placement rate trend chart (12 months, filterable by cohort) | P1 | 5 |
| B-305 | Accreditation report generator (ABET, AUN-QA templates) | P1 | 5 |
| B-306 | Curriculum intelligence: employer-demanded skills vs. course coverage | P1 | 5 |
| B-307 | Faculty dashboard (read-only): their dept's career outcomes | P1 | 5 |
| B-308 | Monthly university digest email (auto-generated summary) | P2 | 5 |

---

## E17 — VinUni Integrations

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-310 | VinUni OIDC/SAML SSO integration (attribute mapping: student ID, major, year) | P0 | 1 |
| B-311 | VinUni SIS read-only sync: enrollment status, graduation date, major, GPA | P0 | 5 |
| B-312 | SIS-driven tier update: graduated → auto-upgrade to Alumni | P0 | 5 |
| B-313 | Academic calendar API: inform job alert timing, internship suggestions | P1 | 5 |
| B-314 | Faculty dashboard access via university role (read-only) | P1 | 5 |
| B-315 | SIS sync failure alert to university admin | P1 | 5 |

---

## E18 — Excel Export & Reporting

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-320 | Export modal: field selection UI with checkboxes | P0 | 2 |
| B-321 | Export presets: save, load, rename per user | P1 | 2 |
| B-322 | Export: Applications list | P0 | 2 |
| B-323 | Export: CVs metadata | P0 | 2 |
| B-324 | Export: Job listings | P1 | 2 |
| B-325 | Export: Pipeline stages (candidates per stage) | P0 | 2 |
| B-326 | Export: Talent pool | P1 | 2 |
| B-327 | Export: Interviews schedule | P1 | 2 |
| B-328 | Export: Event attendees | P1 | 4 |
| B-329 | Export: Ad campaign performance | P2 | 4 |
| B-330 | Export: Subscription revenue | P2 | 4 |
| B-331 | Export: Career outcomes (university) | P1 | 5 |
| B-332 | Sync export < 1,000 rows (direct response) | P0 | 2 |
| B-333 | Async export > 1,000 rows (Celery → download link notification) | P0 | 2 |
| B-334 | Export includes only fields user has RBAC permission to see | P0 | 2 |

---

## E19 — Company Reviews

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-340 | Student submits review: rating (5 dimensions) + text | P0 | 2 |
| B-341 | Eligibility: must have interviewed or worked at company | P0 | 2 |
| B-342 | Anonymous option for review author | P1 | 2 |
| B-343 | AI moderation: flag inappropriate content for human review | P1 | 3 |
| B-344 | Partner can respond publicly to review | P1 | 2 |
| B-345 | University can remove reviews violating policy | P0 | 2 |
| B-346 | Review aggregate: rating display on company profile | P0 | 2 |
| B-347 | Verified badge on reviews from confirmed employees | P2 | 3 |

---

## E20 — University Moderation & Governance

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-350 | Moderation queue: partner registrations, job posts, events, ads, reviews | P0 | 1 |
| B-351 | SLA indicators: green / amber / red by time remaining | P0 | 1 |
| B-352 | Reject action: mandatory reason category + explanation text (min 20 chars) | P0 | 1 |
| B-353 | Bulk approve for same-category items | P1 | 1 |
| B-354 | AI-assisted review suggestion (confidence shown; human always decides) | P1 | 3 |
| B-355 | AI suggestion audit log: human decision + AI suggestion + agreement | P1 | 3 |
| B-356 | Partner suspension with reason | P0 | 1 |
| B-357 | Partner package assignment by university | P0 | 1 |
| B-358 | System configuration: theme, feature flags, policies, legal text | P0 | 1 |
| B-359 | University super admin: manage all user accounts | P0 | 1 |

---

## E21 — Notifications

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-360 | In-app notification center (bell icon, grouped by today/yesterday/older) | P0 | 1 |
| B-361 | Mark read / mark all read | P0 | 1 |
| B-362 | Email: application status change | P0 | 1 |
| B-363 | Email: interview invite | P0 | 1 |
| B-364 | Email: job deadline (D-3, D-1) | P1 | 1 |
| B-365 | Email: offer received | P0 | 1 |
| B-366 | Email: event registration confirmed | P1 | 4 |
| B-367 | Email: event reminder (D-1) | P1 | 4 |
| B-368 | Email: waitlist promotion | P1 | 4 |
| B-369 | Push notification (PWA) — requires explicit permission | P2 | 5 |
| B-370 | Notification preferences: choose which types to receive | P1 | 2 |
| B-371 | Broadcast notification (university admin → all / segment) | P1 | 3 |
| B-372 | Proactive AI nudge: "Profile completion at 60% — complete to get matched" | P2 | 3 |

---

## E22 — In-app Institutional Messaging (M25)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-373 | Direct message: University admin → any user | P0 | 3 |
| B-374 | Direct message: Partner → candidate (recruitment context) | P1 | 3 |
| B-375 | Direct message: Student → University (support) | P1 | 3 |
| B-376 | Student reply to partner message (không initiate) | P1 | 3 |
| B-377 | Group messaging: University creates student group | P1 | 3 |
| B-378 | Group messaging: Partner internal team | P2 | 3 |
| B-379 | Broadcast: University → all students / alumni / segment | P1 | 3 |
| B-380 | WebSocket real-time delivery | P0 | 3 |
| B-381 | Read receipts (sent/delivered/read) | P2 | 3 |
| B-382 | File attachment in message (PDF, image, max 20MB) | P2 | 4 |
| B-383 | Message edit/delete within 10 minutes | P2 | 4 |
| B-384 | Reply-to message (quote) | P2 | 4 |
| B-385 | Emoji reactions (6 basic) | P3 | 4 |
| B-386 | Anti-spam: partner max 3 msg/day to candidate without active application | P0 | 3 |
| B-387 | Block sender (student → report to university) | P1 | 4 |
| B-388 | Message search within conversation | P2 | 5 |
| B-389 | Chat panel slide-in UI (not full-page) | P0 | 3 |

---

## E23 — Visual Workflow Builder (M26)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-390 | React Flow canvas — university admin view | P1 | 4 |
| B-391 | Node palette: Trigger, Condition, AI Process, Human Review, Action, Delay, End | P1 | 4 |
| B-392 | Flow persistence (save/load JSON graph to DB) | P1 | 4 |
| B-393 | DRAFT → TEST → ACTIVE status transitions | P1 | 4 |
| B-394 | Test mode: dry-run with sample data + node highlight | P1 | 4 |
| B-395 | Flow execution engine (Celery) with per-node logging | P1 | 4 |
| B-396 | Cycle detection (DAG enforcement, frontend + backend) | P0 | 4 |
| B-397 | Execution history view: step-by-step log per run | P2 | 4 |
| B-398 | Preconfigured flow templates (student verification, moderation pipeline) | P2 | 4 |
| B-399 | Failed execution inspector: admin can inspect + replay | P2 | 5 |
| B-400 | Flow versioning: edit creates new version, old version preserved | P2 | 5 |

---

## E24 — Bulk Apply / Job Cart (M27)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-401 | Add job to cart button (job card + detail page) | P1 | 3 |
| B-402 | Cart icon in navbar with badge count | P1 | 3 |
| B-403 | Cart page: list of selected jobs + AI match % | P1 | 3 |
| B-404 | AI cover letter generation per job (CV × JD × company) | P1 | 3 |
| B-405 | Cover letter preview + edit inline before applying | P1 | 3 |
| B-406 | Apply all selected (with confirmation modal) | P1 | 3 |
| B-407 | Weekly apply quota enforcement (per tier) | P0 | 3 |
| B-408 | Quota bar UI: "Còn X lượt apply tuần này" | P1 | 3 |
| B-409 | Cart max 20 jobs — show warning when approaching | P2 | 3 |
| B-410 | Smart suggestions: "Đây là 3 job có match >85%" | P3 | 4 |
| B-411 | Quota purchase (student subscription) | P2 | 4 |

---

## E25 — Real-time Presence & Activity Audit (M28)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-412 | Partner admin: team presence indicator (online/away/offline) | P2 | 3 |
| B-413 | Partner admin: live activity feed (who did what, when) | P2 | 3 |
| B-414 | Partner admin: audit filter (by member, date, action) | P2 | 3 |
| B-415 | Partner admin: audit export to Excel | P2 | 4 |
| B-416 | University admin: system activity feed (new regs, jobs, flags) | P1 | 3 |
| B-417 | University admin: full audit search (all actors + all actions) | P1 | 3 |
| B-418 | University admin: audit export (2-year retention, Excel) | P2 | 4 |
| B-419 | Student: view own activity history (applications, AI, events) | P2 | 4 |
| B-420 | IP stored as SHA-256 hash (privacy compliance) | P0 | 3 |
| B-421 | Before/after state snapshots on all write operations | P1 | 3 |

---

## E26 — Video Interview Integration (M29)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-422 | Video interview scheduling: select "Video" type when creating interview | P1 | 4 |
| B-423 | Auto-generate meeting link on schedule (Google Meet or Zoom API) | P1 | 4 |
| B-424 | Meeting link in interview detail page for both parties | P1 | 4 |
| B-425 | One-click join button (no copy-paste) | P1 | 4 |
| B-426 | Recording toggle (optional, dual consent required) | P2 | 4 |
| B-427 | Consent prompt shown to candidate before joining if recording enabled | P0 | 4 |
| B-428 | Recording link attached to scorecard post-interview | P2 | 5 |
| B-429 | Auto-expiry of recordings after 30 days | P1 | 5 |
| B-430 | Video provider configurable in university AI Settings | P1 | 4 |

---

## E27 — Push Notifications & Smart Reminders (M30)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-431 | Web Push subscription (explicit permission request) | P2 | 4 |
| B-432 | Service Worker setup (PWA) | P2 | 4 |
| B-433 | Push: student — interview reminder (24h + 1h before) | P1 | 4 |
| B-434 | Push: student — application deadline (3d + 1d) | P1 | 4 |
| B-435 | Push: partner — new applications batch | P2 | 4 |
| B-436 | Push: partner — SLA overdue | P1 | 4 |
| B-437 | Push: partner — subscription expiring (7d, 3d, 1d) | P1 | 4 |
| B-438 | Push: university — moderation queue > SLA | P1 | 4 |
| B-439 | Do Not Disturb: user sets quiet hours | P3 | 5 |
| B-440 | Notification preference settings (per category, per channel) | P1 | 3 |
| B-441 | Weekly job match digest email (Tuesday 9am) | P2 | 4 |

---

## E28 — Partner Flexible Dashboard (M31)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-442 | 12-column widget grid layout | P2 | 4 |
| B-443 | Drag-to-reorder widgets (@dnd-kit sortable) | P2 | 4 |
| B-444 | Widget size selector (S/M/L) from widget menu | P2 | 4 |
| B-445 | Add/remove widgets from catalog | P2 | 4 |
| B-446 | Layout saved per user (backend + localStorage) | P2 | 4 |
| B-447 | Reset to default layout | P3 | 4 |
| B-448 | Pipeline Summary widget (Kanban mini-view) | P1 | 4 |
| B-449 | Quick Stats widget (today's numbers) | P1 | 4 |
| B-450 | Upcoming Interviews widget (next 7 days calendar) | P2 | 4 |
| B-451 | Quota Usage widget (with upgrade CTA when >80%) | P1 | 4 |

---

## E29 — AI Provider Hub Visual Management (M32)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-452 | Provider cards UI: name, status, response time, cost | P1 | 3 |
| B-453 | Add provider: form + API key (encrypted AES-256) | P0 | 3 |
| B-454 | Health check: auto-run every 60s, show indicator | P1 | 3 |
| B-455 | Priority mode: drag to reorder fallback chain | P1 | 3 |
| B-456 | Round-robin mode: weight sliders per provider | P2 | 4 |
| B-457 | Task-based routing: select provider per task_type | P1 | 3 |
| B-458 | Test provider button: send test prompt, show latency | P1 | 3 |
| B-459 | Cost cap per provider per day (auto-disable when exceeded) | P2 | 4 |
| B-460 | On unhealthy: auto-skip + email alert to admin | P1 | 3 |

---

## E30 — Document Knowledge Base / RAG (M33)

### E30a — Platform Knowledge Base (University)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-461 | University admin: `/admin/knowledge-base` — list all platform docs with status badge | P0 | 3 |
| B-462 | Upload PDF/DOCX/TXT (50 MB max) with drag-and-drop + file picker | P0 | 3 |
| B-463 | Virus scan on upload; reject with reason if threat detected | P0 | 3 |
| B-464 | Text extraction: pdfplumber for PDF (Tesseract OCR fallback), python-docx for DOCX | P0 | 3 |
| B-465 | Paragraph-aware chunking: ~512 tokens, 64-token overlap, max 500 chunks/doc | P0 | 3 |
| B-466 | Embedding via university-configured AI provider (text-embedding model) | P0 | 3 |
| B-467 | pgvector storage with IVFFlat index for cosine similarity search | P0 | 3 |
| B-468 | Document status badge: PROCESSING / READY / FAILED with error message | P0 | 3 |
| B-469 | Preview extracted text (first 500 chars) in admin UI for quality verification | P1 | 3 |
| B-470 | Chunk count display per document | P1 | 3 |
| B-471 | Storage quota bar: current usage / 5 GB with soft warning at 80% | P1 | 3 |
| B-472 | Delete document: soft delete, async storage cleanup, chunk cascade | P0 | 3 |
| B-473 | Bulk delete documents | P2 | 4 |
| B-474 | Doc count limit enforcement: max 200 docs for platform KB | P0 | 3 |

### E30b — Partner & Per-Job Knowledge Base

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-475 | Partner admin: `/partner/knowledge-base` with 2 tabs: Company Docs \| Per-Job Docs | P1 | 4 |
| B-476 | Partner: upload to Company KB (scope = partner, max 50 docs, 500 MB) | P1 | 4 |
| B-477 | Partner: create per-job KB scoped to a specific job posting (max 10 docs) | P1 | 4 |
| B-478 | Partner KB access: students who have applied to org OR are browsing company profile | P0 | 4 |
| B-479 | Per-job KB access: students with active application only (SUBMITTED → OFFER_EXTENDED) | P0 | 4 |
| B-480 | Partner storage quota enforcement: 500 MB hard limit, 400 MB soft warning | P0 | 4 |

### E30c — RAG Query Engine

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-481 | Scope resolution service: determine which KBs user may query in given context | P0 | 3 |
| B-482 | pgvector cosine similarity search with minimum threshold 0.60 | P0 | 3 |
| B-483 | Top-K retrieval (K=5 default, max 10) filtered by permitted KB IDs | P0 | 3 |
| B-484 | Context assembly: inject chunks into AI prompt with document metadata | P0 | 3 |
| B-485 | Mandatory source citation in answer: document name + section heading | P0 | 3 |
| B-486 | No-result response: graceful fallback message (no hallucination) | P0 | 3 |
| B-487 | Chatbot on company profile page auto-scopes to Partner KB | P1 | 4 |
| B-488 | Chatbot on job detail page auto-scopes to Per-Job KB (active applicants only) | P1 | 4 |
| B-489 | Platform chatbot: auto-include Platform KB in context for policy questions | P0 | 3 |

### E30d — Operations & Quality

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-490 | Ingestion retry: embedding failures retry 3× with exponential backoff | P1 | 3 |
| B-491 | Alert admin when >5 docs in FAILED state simultaneously | P2 | 4 |
| B-492 | Truncation warning: docs exceeding 500 chunks show admin warning | P1 | 3 |
| B-493 | Audit log: all upload, delete, and failed-scan events | P0 | 3 |
| B-494 | Provider leakage test: embedding model name never exposed in API response | P0 | 3 |
| B-495 | Eval dataset: 10 happy-path Q&A pairs per KB type, 5 adversarial, 5 no-result | P1 | 4 |

---

## E31 — Account, Device, Locale, Notifications (M34)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-496 | Account settings shell: language, timezone, theme, profile preferences | P0 | 1 |
| B-497 | Browser/coarse-location locale detection with explicit user override | P0 | 1 |
| B-498 | Active sessions/device list with safe device hint and last activity | P0 | 1 |
| B-499 | Remote logout device/session and security event log | P0 | 1 |
| B-500 | Notification preferences by category/channel/digest/quiet hours | P0 | 1 |
| B-501 | Notification outbox with idempotent dispatch worker | P0 | 1 |
| B-502 | Local email renderer using Mailpit/console, no real outbound email in tests | P0 | 1 |
| B-503 | University admin notification template builder with variable chips | P1 | 2 |
| B-504 | Template preview with sample data and required-variable validation | P1 | 2 |
| B-505 | Versioned active/draft/archive template lifecycle | P1 | 2 |
| B-506 | Security alerts mandatory category cannot be disabled | P0 | 1 |
| B-507 | Push/PWA subscription gated by explicit browser permission | P2 | 4 |

---

## E32 — Local-First AI/OCR And Lightweight Runtime (M35)

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-508 | Local-first app run commands; Docker optional infra only | P0 | 0 |
| B-509 | Backend inline worker mode behind queue adapter | P0 | 0 |
| B-510 | PDF extraction with pdfplumber before OCR fallback | P0 | 1 |
| B-511 | DOCX extraction with python-docx | P0 | 1 |
| B-512 | Tesseract fallback configured for `vie+eng` | P0 | 1 |
| B-513 | CV extraction tiny fixtures for Vietnamese and English | P0 | 1 |
| B-514 | Offline/fake AI provider for CI and unit tests | P0 | 0 |
| B-515 | OpenRouter/DeepSeek-compatible low-cost smoke test path capped by env | P1 | 1 |
| B-516 | AI communication draft assistant for admin-reviewed templates | P2 | 3 |
| B-517 | Skill gap map and learning plan AI feature with eval dataset | P2 | 3 |

---

## E33 — Partner RBAC & Recruiting Intelligence

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-518 | Partner Admin owns wildcard org capabilities, then grants feature access by role, user, and department | P0 | 2 |
| B-519 | Permission catalog includes analytics, job click/view metrics, CV access, exports, billing, pipeline actions, scorecards, offers, and AI recruiting tools | P0 | 2 |
| B-520 | Department-scoped permissions restrict jobs, applications, analytics, pipeline, and exports to the member's assigned scope | P0 | 2 |
| B-521 | Job analytics projection tracks impressions, detail views, CTA clicks, apply starts, submitted applications, source mix, and conversion | P0 | 3 |
| B-522 | Partner dashboard V2 shows real todos, job performance, conversion, team activity, package limits, and permission-aware locked states | P0 | 3 |
| B-523 | Candidate access audit logs application open, CV preview/download, reveal request, and revealed-identity view | P0 | 2 |
| B-524 | Partner activity feed shows who created/submitted jobs, reviewed candidates, viewed CVs, changed roles, and managed billing | P1 | 3 |
| B-525 | Analytics and exports only include rows/fields the actor has permission to access | P0 | 3 |
| B-526 | AI recruiting actions respect RBAC and remain advisory or confirmation-required with audit rows | P0 | 3 |
| B-527 | Dashboard and analytics widgets degrade honestly when a projection or permission is missing; no fake click/view metrics | P0 | 3 |

---

## E34 — Visual CV Studio & Template Operations

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-528 | ~~CV Studio visual canvas editor~~ — superseded by B-528.1–B-528.5 per `docs/adr/ADR-0015-cv-studio-visual-canvas-editor.md` (04/07/2026 audit: backend `canvas_json`/photo-crop already exist and are unused by the frontend; 3 divergent render paths must unify into one) | P0 | 1 |
| B-528.1 | CV Studio data model: `content_binding_schema` on templates, `CvTemplateVersion`, migration/default-canvas synthesis for existing CVs (no data loss) | P0 | 1 |
| B-528.2 | CV Studio render unification: single `render_cv()`/`RenderDocument` pipeline consumed by on-screen canvas, PDF export, and template `preview_image` generation; read-only canvas shell replacing the drifting A4 mirror | P0 | 1 |
| B-528.3 | ✅ **Implemented (04/07/2026, sign-off bypassed — see note)** CV Studio canvas editing: inline text editing + block selection + drag/drop, built on the existing (working) autosave/version-restore/AI-diff infrastructure | P0 | 1 |
| B-528.4 | ✅ **Implemented (04/07/2026, sign-off bypassed — see note)** CV Studio photo + style controls: photo crop/replace wired into the canvas UI; style controls limited to a constrained token set (align/font size/emphasis), not free CSS | P0 | 2 |
| B-528.5 | Still open. CV Studio template admin publish/archive/preview wired to real `CvTemplateVersion` rows and real `preview_image` generation remain unimplemented — `CvTemplateVersion` does not exist in code (confirmed 04/07/2026); current `cv_templates.is_active` toggle is the only archive-like lever. Mobile canvas review mode: read/accept-reject only, not full block editing (per B-533 scope). | P0 | 2 |
| B-529 | CV template marketplace: preview thumbnails generated from renderer, role/industry categories, language support, locked/premium states, and template switching that preserves bound content | P0 | 1 |
| B-530 | University CV template operations: create/upload/clone templates, validate binding schema, preview, publish/archive versions, and audit template changes | P0 | 2 |
| B-531 | AI natural-language CV edit command: user instruction -> structured patch/diff -> canvas preview -> explicit accept/edit/reject -> version + audit | P0 | 3 |
| B-532 | CV ingestion to canvas: uploaded CV preview, extraction review, import into selected template, no silent overwrite, failure recovery, and mobile review mode | P0 | 1 |
| B-533 | CV editor accessibility and mobile review: keyboard block movement, focus order, screen-reader labels, page navigation, and responsive inspector/review modes | P1 | 2 |
| B-534 | CV template seed packs by role family/industry with realistic sample content, safe assets, and clean data linked to role taxonomy | P1 | 2 |

---

## E35 — Student Job Fit & Competition Intelligence

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-535 | Student job intelligence endpoint combines best CV, CV-JD fit, evidence gaps, truthful CV improvement actions, learning gaps, and apply readiness | P0 | 2 |
| B-536 | Competition intelligence read model uses seats/hiring intent, application volume buckets, applicant quality buckets, student fit bucket, deadline freshness, and source mix | P0 | 3 |
| B-537 | Competition UI is login-only, privacy-safe, low-signal aware, and never exposes other applicants, exact ranks, raw AI confidence, or internal scoring internals | P0 | 3 |
| B-538 | Learning gap recommendations map missing JD requirements to skills, courses/resources, practice actions, and CV evidence suggestions | P1 | 3 |
| B-539 | Job detail page prioritizes student actions: select/use best CV, improve CV, apply, save, compare adjacent roles, and dismiss/reset preview state | P0 | 2 |
| B-540 | Fit/competition eval fixtures cover strong/good/possible/weak fit, low-signal jobs, stale CVs, no CV, closed jobs, and privacy edge cases | P0 | 3 |

---

## E36 — Platform Reality Hardening & Data Quality

| ID | Story | Priority | Phase |
|----|-------|----------|-------|
| B-541 | Product reality audit: reconcile current backend/frontend with `PRODUCT_REALITY_REBUILD_SPEC.md`, mark demo-like flows, and produce module owners before broad implementation | P0 | 1 |
| B-542 | Auth identity hardening: duplicate email, pending verification resume, OAuth account linking, OTP/link verification, reset rate limits, resend cooldown, and non-enumerating copy | P0 | 1 |
| B-543 | Onboarding state machine: draft/resume/completed states, audit/support history, no name dependency before onboarding, and role-specific next actions | P0 | 1 |
| B-544 | Structured job requirement model: salary modes, experience modes, level, education, nationality, gender, age range, marital status, work authorization, multiple locations, and screening questions | P0 | 2 |
| B-545 | Location and industry taxonomy quality: linked province/district/ward and 3-level industry/job/specialization filters with post-2025 Vietnam location support | P0 | 2 |
| B-546 | Seed/crawl data pipeline: verified company profiles, accurate logos, cleaned job/event data, linked taxonomy/location/salary/experience, varied edge cases, and sponsored/banner inventory | P0 | 2 |
| B-547 | Async operations hardening: notification outbox retry/backoff/dead-letter, scheduled job auto-close, reveal expiry, event reminders, and worker health checks | P0 | 2 |
| B-548 | Product analytics event contract: impressions, clicks, saves, apply starts, submissions, CV exports, AI suggestions, workflow executions, notifications, ad attribution, and privacy-safe metadata only | P0 | 2 |
| B-549 | Frontend reality QA pass: remove demo dashboards, fake metrics, placeholder forms, harsh focus states, missing empty/error/permission states, and inconsistent vi/en copy across public/student/partner/university | P0 | 2 |
| B-550 | System acceptance evidence report: backend/frontend/AI/data/security/browser gates, visual-design verification, E2E status, known gaps, and release blockers per slice | P0 | 1–5 |
| B-551 | Application journey hardening: CV/application snapshots, duplicate-apply prevention/resume, screening-answer storage, student application workspace, interview/offer milestones, withdrawal/archive policy, and truthful status copy | P0 | 2 |
| B-552 | Partner job creation workflow: structured JD capture, JD quality check, preview as guest/student, quota/plan gate, moderation submit, clone-from-performing-job, post-publication amendment policy, and audit | P0 | 2 |
| B-553 | Employer CRM and trust operations: company profile quality, identity verification, recruiter seats, campus relationship owner, event/campaign history, hiring outcomes, risk flags, and university-visible notes | P1 | 3 |
| B-554 | University career-services workspace: counselor cohorts, at-risk students, CV review queues, appointments, employer relationship notes, intervention history, and outcomes reporting | P1 | 3 |
| B-555 | Platform admin/support console: tenant/account lookup, verification state, outbox health, failed async recovery, moderation escalation, package override, safe support view, and audited support actions | P0 | 3 |
| B-556 | Privacy/compliance controls: consent capture, data export, retention/deletion policy, CV/application snapshot retention, notification preferences, and student-visible security history | P0 | 3 |
| B-557 | Abuse/fraud controls: suspicious companies/jobs, spam applications, abusive messages, risky ad creatives, fraud-signal queues, manual escalation, and safe appeal/override paths | P1 | 4 |
| B-558 | Read-model governance: source events, refresh strategy, stale-data behavior, fallback UI, and reconciliation checks for dashboards, recommendations, analytics, and competition intelligence | P0 | 2 |
| B-559 | Fix RBAC permission-catalog/resource-string mismatch: extend catalog with `analytics`, `candidate_identity`, `pipeline`, `scorecards`, `interviews`, `offers`, `ai_recruiting` nouns (with correct actions) and repoint `interview_service`/`offer_service`/`scorecard_service`/`scorecard_ai_service`/`screening_brief_service`/`apply_service`/`reveal_service` off the ungranted `"recruitment"`/`applications:update` resource strings so non-Admin custom roles can actually be granted these capabilities (extends B-519) | P0 | 2 |
| B-560 | Workflow builder real node execution: implement `action` node subtypes (assign_owner, send_notification, create_task, move_candidate, webhook) instead of the current no-op stub, and add a human-review resume/approve endpoint so paused executions are not stuck forever (extends B-391/B-395) | P0 | 4 |
| B-561 | CV ingestion field-level review gate: replace the auto-import path (which hardcodes `fact_confirmation: true` and skips straight to the CV builder) with a real diff/review screen showing original preview beside extracted fields before any import call (extends B-532) | P0 | 1 |
| B-562 | Typed screening-answer validation: validate `screening_answers` against each `ScreeningQuestion.q_type` (yes/no, single/multi-select, numeric, free text) at the API schema layer instead of accepting an unvalidated dict (extends B-544) | P1 | 2 |
| B-563 | AI output-guard hardening: extend `output_guard.py` to scrub internal status codes (`QUEUED`/`FAILED`/`RUNNING`/`PENDING`) and bare latency/timing figures from free-text model output, with adversarial eval cases for both (extends B-494) | P1 | 3 |
| B-564 | Extend `applications:review`/`reject`/`bulk_review` action checks into `decision_service.review_application`/`reject_application` (currently gated only on `applications:read`); requires a backfill decision for existing org roles that only hold `read` today, route through `product-owner-system-planner` before flipping the gate (extends B-559, fixed 04/07/2026) | P0 | 2 |
| B-565 | Extend permission catalog with `notifications:send`, `workflow:create_task`, `workflow:request_approval`, `workflow:webhook` — `workflow/domain/graph.py`'s `DEFAULT_NODE_CAPABILITY` already references these resource/action pairs for node activation but they are not in the catalog, so non-Admin roles can never activate those workflow node types (same root-cause class as B-559) | P0 | 4 |
| B-566 | Deploy a dedicated Celery worker process for the `ai` queue (`--include=app.ai.agents.worker_tasks`) so `bulk_screening_brief` actually executes outside tests in any real environment; add a "workforce backlog stuck" health signal for University Admin | P0 | 3 |
| B-567 | Move CV ingestion's OCR/LLM-structuring fallback off the synchronous HTTP request path (`cv_ingestion_cascade.run_cascade` called inline from `upload_service.upload_cv`) into an async job with a polling status contract, or formally re-confirm sync-in-request as the accepted V1 shape with a documented p95 latency SLO | P0 | 1 |
| B-568 | Reconcile AI request-quota tiers: `AI_PRODUCT_SPEC.md` §9.1 specifies per-role hourly limits (student 30/partner 60/university 100) but `usage_service.py`/`config.py` enforce a flat day/week limit for every persona — align code to doc or amend the doc | P1 | 3 |
| B-569 | Add a second workforce-pattern (multi-agent) consumer beyond `bulk_screening_brief` — deep interview-question batch generation is the best-fit candidate already named in `AI_PRODUCT_SPEC.md` §4.2 — so the coordinator/executor framework isn't validated by a single feature | P2 | 3 |
| B-570 | Add the platform's first scheduled/proactive AI job (nightly fraud-signal sweep across newly published jobs, or weekly stale-CV nudge draft) — today every AI action is reactive to a user click; zero `celery beat`/cron scheduling exists anywhere in the backend | P1 | 3 |
| B-571 | Add a short-TTL dedup/cache layer for repeated identical CV-rewrite/JD-bias-check completion prompts (embeddings are already cached; full completions are not) to cut redundant token spend | P2 | 3 |
| B-572 | Post-Claude backend gate restore: make `uv run ruff check app tests` and `uv run mypy app --ignore-missing-imports` green, starting with `SPONSORED_SURFACES`, onboarding document-verification/session-factory, nullable principal guards, salary/experience presenter typing, workflow graph typing, and analytics/moderation rowcount typing | P0 | 1 |
| B-573 | Workflow builder production UX: sync React Flow state from API graph, emit/persist node and edge changes, add workflow name/trigger config, selector-based inspector fields, validation/dry-run, immutable activation, execution history, and recoverable failed-node tasks | P0 | 4 |
| B-574 | Auth contract and i18n cleanup: register request is email/password/confirm-only, `full_name` removed from register API/UI, names collected in onboarding/profile, verify/reset OTP/link screens fully localized, email templates avoid `Chào {name}` until name is confirmed | P0 | 1 |
| B-575 | Public jobs regression hardening: fix hook dependency warnings, add E2E/API tests for category root/branch/leaf filters, location multi-select, salary/experience modes, sort/grid/list, preview close, pagination, sponsored banners, and no-selected-job ad state | P0 | 2 |
| B-576 | CV Studio production closure: implement `CvTemplateVersion`/assets/binding schema, unify canvas/PDF/template-preview render pipeline, add template admin publish/archive/version audit, browser-verify canvas/photo/AI-diff/import review, and fix known accessibility gaps | P0 | 1 |
| B-577 | AI product evidence gate: add per-feature offline evals and adversarial cases for CV edit, JD matching, competition, recommendation, workflow AI nodes, and output-guard leakage; add user-facing unavailable/low-signal states without provider/model/token leakage | P0 | 3 |
| B-578 | Status/doc truth maintenance: remove or supersede stale "clean/complete" claims after every blocker pass; every status update must include command output tier (`implemented`, `API wired`, `browser verified`, `visual-design verified`, `E2E verified`) and remaining owner | P0 | 1–5 |
| B-579 | University operations control-plane depth: extend moderation/approval queue items with true assign-to-department/user (beyond self-claim), department-scoped queues, holiday/business-hours-aware SLA pause and per-type escalation chains per `BUSINESS_LOGIC.md` §11, and wire the AI human-review queue (`moderation.human_review_queue`) into the operations surface with its own assignment/SLA/escalation and a moderator queue UI (extends the 2026-07-08 operations command center; human-review-queue frontend still absent) | P1 | 3 |
| B-580 | Browser/E2E-verify the university operations command center (`/university/operations`), the request-changes decision on job + event moderation, and the event attendee CSV export (SLA traffic-light thresholds, breach banner, empty/permission states, vi/en, email-masking on the non-organizer export). Authoring-time verification was blocked by a pre-existing broken-import WIP state at HEAD; the endpoints/screens are backend-tested + `API wired` only | P0 | 3 |
