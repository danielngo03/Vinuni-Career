---
description: Audit the current VinUni implementation against docs, product intent, persona UX, UI/UX bar, and verified status before continuing the build
argument-hint: [optional focus, e.g. all persona workspaces + UI/product drift + Phase 1 gaps]
allowed-tools: Read, Bash, Glob, Grep, TodoWrite, Task, Edit, MultiEdit
---

# VinUni Review Snapshot

Focus:

`$ARGUMENTS`

Run this when the build has been paused, the UI/product direction feels wrong,
or `docs/IMPLEMENTATION_STATUS.md` may be over-claiming completion.

## Operating Mode

- Do **not** implement application code in `backend/` or `frontend/` during this command.
- You may edit docs/status/Claude instruction files only when the review exposes stale or missing guidance.
- Treat `docs/IMPLEMENTATION_STATUS.md` as claims to verify, not as truth by itself.
- Compare current code against source docs and the user's latest product intent.
- Lead with findings, then give the exact continuation plan for Claude Code.

## Must Read

- `CLAUDE.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/ROADMAP.md`
- `docs/BACKLOG.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/BUSINESS_LOGIC.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACTS.md`
- `docs/DATA_MODEL.md`
- `docs/SECURITY_PRIVACY.md`
- `docs/DESIGN.md`
- `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` when reviewing public/jobs/events,
  recommendations, sponsored inventory, or monetization UX
- `docs/DESIGN_EXAMPLE.png` when reviewing public marketplace/header/homepage
  visual direction
- `docs/UI_QUALITY_BAR.md`
- `docs/SCREEN_SPECS.md`
- `docs/SYSTEM_ACCEPTANCE_BAR.md`
- `docs/EDGE_CASES_FAILURE_MODES.md`
- `docs/TEST_STRATEGY.md`
- `.claude/rules/frontend.md`
- `.claude/skills/vinuni-ui-polish/SKILL.md`
- `.claude/skills/vinuni-docs-audit/SKILL.md`

Read feature-specific docs as needed.

## Review Lenses

1. Product fit: does the implemented workflow solve the actual VinUni Career use case?
2. Persona UX: do public, student, partner, and university surfaces each feel like real working products for that user?
3. Public discovery: does the public surface show real public jobs, events, companies, search, and clearly labelled sponsored inventory?
4. Recommendations and monetization: are organic, recommended, sponsored, and
   university-curated rails separated; do guest/session and student signals
   produce useful recommendations; are ad placements realistic and tracked?
5. Student experience: CV Studio, job discovery, apply flow, applications, events, AI, settings, and next actions.
6. Partner experience: jobs, company profile, team/RBAC, pipeline, candidates, events, ads, analytics, and daily recruiter work.
7. University experience: moderation queues, partner governance, templates, AI settings, reports, outcomes, audit, and operational health.
8. UI/UX quality: does it feel like a modern, practical career marketplace and operational SaaS, not placeholder marketing?
9. Architecture: are module boundaries, API/data contracts, RBAC, audit, and tenancy consistent with docs?
10. AI product: are AI actions useful, permissioned, confirmation-gated, evaluated, and provider-hidden?
11. Data and edge cases: are invalid files, empty records, duplicates, stale state, async failures, and permission failures handled?
12. Verification truth: do status claims match tests, browser checks, E2E evidence, and observed code?
13. System acceptance: would the slice pass `docs/SYSTEM_ACCEPTANCE_BAR.md`, or is it only locally green?

## Output Contract

Return:

1. Severity-ordered findings with file/line references where possible.
2. Status corrections needed in `docs/IMPLEMENTATION_STATUS.md`.
3. Missing docs/instructions that caused Claude to build the wrong thing.
4. Exact next prompt to continue the build.
5. Agent routing plan for the continuation.
6. Test/browser verification checklist.
7. Per-persona surface score: Public, Student, Partner, University, AI, Data/Security.
8. Product gap list: missing practical features, settings, notifications,
   admin controls, edge cases, AI assists, or data projections Claude should
   propose before continuing.
9. Challenge log: questionable user/task assumptions and recommended product/architecture corrections.

Do not mark a phase complete unless the real workflow is implemented, tested, and verified at the correct level.
