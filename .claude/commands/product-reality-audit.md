---
description: Audit VinUni product realism, business logic, AI usefulness, data/backend contracts, and persona UX before implementation
argument-hint: [focus, e.g. CV-first student experience + job-fit scoring + AI usefulness]
allowed-tools: Read, Bash, Glob, Grep, TodoWrite, Task, Edit, MultiEdit
---

# VinUni Product Reality Audit

Focus:

`$ARGUMENTS`

Use this before a broad build slice or whenever the implementation feels
technically present but product/business/AI/UX quality is weak.

## Operating Mode

- Do **not** implement application code in `backend/` or `frontend/`.
- You may edit `docs/`, `.claude/`, and root `CLAUDE.md` only when the audit
  reveals missing or stale instructions.
- Act as product owner + BA + tester + architect + AI product reviewer.
- Challenge weak user requests, generic SaaS screens, fake metrics, AI
  decoration, missing edge cases, and backend shortcuts.
- End with exact continuation prompts for `/autopilot-build` or
  `/feature-vinuni`.

## Must Read

- `CLAUDE.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/PRODUCT_REALITY_REBUILD_SPEC.md`
- `docs/BUSINESS_LOGIC.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/DATA_MODEL.md`
- `docs/AI_PRODUCT_SPEC.md`
- `docs/CV_STUDIO_SPEC.md`
- `docs/CV_INGESTION_EXTRACTION_SPEC.md`
- `docs/SCREEN_SPECS.md`
- `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`
- `docs/DESIGN.md`
- `docs/UI_QUALITY_BAR.md`
- `docs/EDGE_CASES_FAILURE_MODES.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/TASK_ROUTING.md`
- Relevant `.claude/rules/*.md` and agents for the focus.

## Audit Lenses

1. Real workflow: what does the persona need to accomplish today?
2. Product friction: where is the flow forcing unnecessary forms, clicks, or
   admin-style UI?
3. Business logic: quota, moderation, ads, events, notifications, packages,
   RBAC, audit, and recovery states.
4. Backend contract: API shape, error semantics, idempotency, concurrency,
   async jobs, projections, and tenant isolation.
5. Data model: ownership, soft delete/archive, snapshots, derived reports,
   privacy, retention, and read-model strategy.
6. AI usefulness: whether AI saves real work, has permission class, eval,
   fallback, rollback, cost control, and provider secrecy.
7. Student CV-first flow: upload/template/AI/raw-notes/drag-drop/job-fit should
   work without forcing a profile form.
8. UI/UX realism: compare public/student surfaces to a large recruiting
   marketplace and partner/university surfaces to real ops products.
9. Discovery/recommendation realism: check whether public/session/student
   recommendations are genuine, explainable, privacy-safe, and clearly separated
   from sponsored inventory.
10. Edge cases: blank/not-CV files, stale CVs, duplicate upload, quota reached,
   low confidence extraction, offline, permission denied, and async failure.
11. Verification: what tests/screenshots/browser checks prove this is real?
12. Adjacent-flow audit: what related auth, onboarding, notification, analytics,
    admin, seed-data, billing/quota, workflow, or support behavior must change
    so this feature is usable in production rather than isolated demo UI?
13. Application lifecycle: are CV/application snapshots, duplicate-apply rules,
    screening answers, interview/offer milestones, withdrawal/archive behavior,
    and truthful status copy backed by canonical events?
14. Support/compliance/abuse: are support actions audited, privacy controls
    defined, consent/retention/export/delete covered, and abuse/fraud paths
    realistic enough for a university recruiting platform?
15. Read-model integrity: which dashboards, recommendations, analytics, or
    competition views need projections, source events, stale-data handling, and
    reconciliation instead of constants or ad hoc queries?

## Output Contract

Return:

- Severity-ordered product/logic/AI/backend/frontend findings.
- Missing or weak features Claude should propose before coding.
- Adjacent flows and backend/data/AI/frontend contracts that must be updated
  even if the user only named one visible UI problem.
- Specific docs/rules/agents that need updates, if any.
- Concrete acceptance criteria for the next implementation slice.
- Agent routing plan.
- Fast-slice build prompts in priority order.
- "Do not build yet" blockers, if any.
