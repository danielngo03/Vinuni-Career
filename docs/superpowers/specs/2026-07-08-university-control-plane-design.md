# University Control Plane — Design Spec

- Date: 2026-07-08
- Owner: danielngo0302 — approved to build ("làm ngay, làm hết", UI/UX must be genuinely good)
- Branch: `feat/university-ai-control-plane` (based on shared metering foundation commit `e83b325`)
- Related: `docs/superpowers/specs/2026-07-08-student-ai-overhaul-design.md` (shared foundation), `2026-07-07-platform-admin-console-design.md`; memory `platform-admin-console`, `university-operations`, `partner-ai-overhaul`, `student-ai-overhaul`, `project-context`
- Rules: `.claude/rules/{ai,backend,frontend}.md`; source docs: `AI_PRODUCT_SPEC`, `PRODUCT_OPERATING_MODEL`, `SECURITY_PRIVACY`, `PARTNER_RBAC_ANALYTICS_SPEC`, `BUSINESS_LOGIC`, `ARCHITECTURE`, `DATA_MODEL`, `API_CONTRACTS`, `EDGE_CASES_FAILURE_MODES`.

## 1. Vision — university is the platform's control plane

VinUni is the single institution (not SaaS/multi-tenant, memory `project-context`). The university persona is the platform's **control plane** in three layers, superadmin on top and able to do everything:

1. **Platform/System** (superadmin): AI operations, system health, logs, feature flags, alerts, cross-org, **distribute AI energy**, **own the whole RBAC graph**. Exempt from all AI limits.
2. **University Operations** (staff, gated by grants scoped to role/department): moderate partner jobs/events/ads; govern students; manage partners, events, knowledge base.
3. **Cross-persona governance** (superadmin + granted staff): act on students & partners directly (verify/suspend/override, support/compliance, fraud/bias). Human final say; fully audited.

Non-negotiable: never expose provider/model/token/USD/latency/prompt/embedding internals to end users **or ordinary university staff** (superadmin-only, admin surfaces only); every write audited; RBAC in the service layer; AI advisory with human final say; never fabricate.

## 2. Locked owner decisions (2026-07-08)

1. Scope = everything, phased. University controls the system + student + partner. Real, powerful, intuitive UI/UX — not token surfaces.
2. AI unit = **AI energy %**, cost-weighted, masked — the **shared** `ai_billable_usage` + `app/ai/energy` substrate (do not fork).
3. Windows = **weekly HARD + 3h rolling SOFT; daily REMOVED**.
4. **University = distribution, not billing.** No self-serve upgrade, no top-up wallet, no billing CTA. **Superadmin distributes** energy down org → department → user. Exhaustion → **admin capacity-request workflow**. **Superadmin exempt.**
5. University **chatbot is its own assistant** (own tools, per-user/role/department tool-RBAC, RAG over university data, multi-agent, file/image upload + tables/charts).
6. **Split** the Platform Admin console from the University Operations workspace (frontend reorganization; backend `/admin/*` reused).

## 3. Verified foundation (this worktree, commit `e83b325`)

The shared AI-energy foundation is BUILT and already covers the mechanism university needs:
- `app/ai/energy/models.py::AiEnergyAccount` (migration `0084`) — `scope_type ∈ {org,department,user}`, `scope_id`, `org_id`, `weekly_allowance_units` (ceiling; NULL = inherit), `wallet_units`, `updated_by`, audit. **This is the distribution table** (a department/user ceiling set by an admin).
- `app/ai/energy/service.py` — `snapshot()`, `enforce_energy()`, `build_usage_context()`, `charge_units()`. Consumption summed on demand from `ai_billable_usage` (no drift). Weekly hard + 3h soft; degrades OPEN on infra error.
- `constants.py` — cost-weighted `FEATURE_UNIT_COST`, `DEFAULT_WEEKLY_UNITS_UNIVERSITY = 2000`, reason codes.
- Wired into: partner JD/scorecard/screening/market-intel + chat (`usage_service.enforce_quota`→energy).

**Foundation gaps university must close (P1):**
- `service.py` meters university on the **USER scope only**; `SCOPE_DEPARTMENT` is defined but **never resolved** (true for partner too). No org→department→user chain for university.
- **Superadmin is NOT exempt** in `enforce_energy`/`snapshot` (only `PermissionChecker.can` exempts).
- Block copy says "nâng gói / mua thêm" (upgrade/buy) — **wrong for university** (no billing).
- No **capacity-request** workflow; no **superadmin distribution API/UI**.
- `org_reporting_facade.department_ids_for_user_in_org(...)` is the clean read-model to resolve a user's departments (no cross-module model import).

RBAC / chatbot / IA gaps: as in the master audit (department not an enforced permission scope; `/university/team` missing; chatbot is student/partner-only, no university tools/RBAC-at-dispatch/university-RAG/multi-agent/file-analysis; platform-ops mixed into the university shell; `/university/ai-settings` missing `SuperadminGuard` — a security bug).

## 4. Workstreams by phase

### P1 — AI governance for university (extend the shared foundation)
- **WS1.1 Superadmin exemption** — `snapshot()` returns an unlimited state and `enforce_energy()` no-ops when `principal.is_superadmin`. USD cost still recorded to the ledger for visibility; energy never blocks/charges.
- **WS1.2 Department→user distribution resolution** — extend `service.py` so a university member's effective weekly allowance = most-specific applicable `AiEnergyAccount` ceiling (user > department(min) > org pool > persona default 2000); a call blocks if the member's own ceiling OR the org pool is exhausted. Use `org_reporting_facade.department_ids_for_user_in_org`. Implemented generally (also fixes partner's department gap) but only tightens when an account row exists → no regression.
- **WS1.3 University block/warn messaging** — persona-aware copy + reason `AI_UNIVERSITY_ALLOCATION_EXCEEDED`; the public snapshot carries `action = "request_capacity"` for university (vs `"upgrade"` for student/partner). No provider/model/USD.
- **WS1.4 Capacity-request workflow** — new `ai_capacity_requests` table + service + `/university/ai/capacity-requests` (staff submit) + superadmin queue (approve → set/raise the target's `AiEnergyAccount` ceiling; deny). Audited; notification via outbox.
- **WS1.5 Superadmin distribution API** — superadmin CRUD `AiEnergyAccount` allocations for the university org's departments/users, with a live usage read-model (used vs allowance per department/user, from `ai_billable_usage`). Under the admin AI-ops surface.
- **WS1.6 Ledger department attribution** — add `ai_billable_usage.department_id` (nullable) + index so department consumption is attributable; `build_usage_context` sets it from the caller's primary department.

### P2 — University RBAC control plane
- **WS2.1** Department-scoped permission enforcement: optional `department_id` on grants; `PermissionChecker.can()` consults `MembershipDepartment` (shared with partner; absence = org-wide, no regression).
- **WS2.2** `/university/team` RBAC UI (reuse `team-screen.tsx`, org-type-aware): superadmin creates departments, invites/assigns staff, grants roles/permissions per user/role/department.
- **WS2.3** Cross-org superadmin management (resolve org context by explicit `org_id` when `is_superadmin`).
- **WS2.4** Replace coarse `persona=="university_staff"` gates with catalog grants at the service layer; seed starter university roles.

### P3 — University AI Assistant
- **WS3.1** `assistant_university` prompt + university tool set (moderation, approvals, cohort/outcomes analytics, partner governance, events, student governance, KB curation, dept/staff analytics, confirmation-gated cross-persona actions); `persona=[UNIVERSITY_STAFF]` used.
- **WS3.2** Central tool-RBAC gate at dispatch: enforce `spec.required_permissions` via `PermissionChecker` (user/role/department) for all personas.
- **WS3.3** RAG over university data: new `university` KB scope + tenancy-scoped query tools; deterministic-first; charge energy only for the paid narrative tier.
- **WS3.4** Multi-agent: extend `app/ai/agents/workforce.py` planner→router→sub-agents for university analysis; idempotent Celery; metered; human confirmation for writes.
- **WS3.5** File/image upload + analysis + charts: `chat_message_attachments` + `chat_sessions.org_id/department_id`; signed/type-checked upload; reuse CV cascade ingestion scoped to university context; render tables/charts (no PII/raw counts/model internals). Metered.

### P4 — IA split + surfacing (frontend)
- **WS4.1** Split the Platform Admin console (own shell/nav, superadmin-only) from University Operations. Backend `/admin/*` unchanged.
- **WS4.2** University operations IA: career-office model (Overview • Moderation • Partners • Students/Career Services • Events • Knowledge/Comms • Analytics/Outcomes • Team & RBAC • AI Governance • Trust/Compliance); merge double user-management; add `/university/team`; surface energy meter + distribution UI; route orphaned screens; **add `SuperadminGuard` to `/university/ai-settings` + gate the provider registry to superadmin (security fix)**.
- **WS4.3** University assistant surface: file/image upload, table/chart rendering, tool-confirmation cards, energy meter; distinct from the student bot; v9 Monochrome + a11y.

### P5 — Cross-persona governance + realism
- Cross-persona actions (verify/suspend/override/restore/support/compliance) with confirmation + audit + reason; AI human-review queue moderator UI (B-579); curriculum-intelligence / fraud / JD-bias governance; career-outcomes depth + faculty placement stats; notifications/communications governance; audited PII-masked exports; (optional, security-gated) impersonation; SIS/IdP/academic-calendar hooks.

## 5. Data model (additive; upgrade+downgrade; permission/tenant/failure tests)
- `ai_billable_usage.department_id` (nullable + index).
- New `ai_capacity_requests` (org_id, requested_by, scope_type, scope_id, reason, requested_units?, status, decided_by?, decided_at?, decision_note?, audit).
- P2: optional `permission_grants.department_id` (or `permissions.department_id`).
- P3: `chat_message_attachments`; `chat_sessions.org_id/department_id`; `knowledge_bases.scope += university`.
- P2/P5: `departments.updated_at/deleted_at/description/manager_membership_id`; soft-delete on `roles`.
- Reuse `AiEnergyAccount` for all distribution (no new allocation table).

## 6. Phasing, rollout, risk
One draft PR per phase; each ends green (ruff/mypy/pytest; tsc/lint/build), tests/evals added, `docs/IMPLEMENTATION_STATUS.md` updated (`implemented`/`API wired`/`browser verified`/`E2E verified`). Energy behind a flag, shadow-first; university distribution starts permissive (persona default) so nobody is falsely blocked pre-distribution. Department-scoped RBAC ships behind org-wide grants (absence = org-wide). Provider-registry gate (WS4.2) is a security fix — ship early. Economical real-model testing (offline/fake bulk; few cheap-alias smokes). Pre-existing baselines: FE `tsc` ~37 errors, backend pytest ~3–6 failures (memory `university-operations`) — new code adds zero. Shared-foundation edits stay persona-agnostic to merge cleanly with the parallel student/partner overhauls.

## 7. Open questions (non-blocking)
Energy weights + default allocations (calibrate from shadow); Platform Admin split as `(admin)/admin/*` route group vs separated section (recommend route group; confirm in P4); chatbot chart lib (Recharts code-split vs CSS primitives — decide in P3/P4); SIS/IdP depth (P5 vs later spec).
