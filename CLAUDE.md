# Claude Code Operating Guide — VinUni Career Platform

This repository is the instruction layer for a clean greenfield rebuild of the VinUni Career Platform.

## Prime Directive

- `backend/` and `frontend/` may be absent after reset. If absent, scaffold them from `CLAUDE.md`, `.claude/`, and `docs/`; if present, treat them as the current implementation.
- If `backend/` or `frontend/` contain only `.env` / `.env.example`, treat them as env seeds, not implemented code.
- Root `.env` / `.env.example` are reserved for AI hook logging. Backend runtime env belongs in `backend/.env`; frontend runtime env belongs in `frontend/.env`.
- Do not reuse pre-reset backend/frontend code, old git history, or remembered Phase 0/1/2 status as foundation.
- Root legacy config files may still exist during reset. Do not treat root `docker-compose.yml`, `pyrightconfig.json`, old Makefiles, or old README content as source of truth until regenerated for the new scaffold.
- Docs are the source of truth for product intent and business rules. When code conflicts with docs, reconcile by fixing code OR flagging the doc as stale — do not silently discard working code.
- For large work: explore relevant docs/files -> plan -> implement -> test -> summarize.
- Do not deploy, push production changes, change production env values, or remove sponsored/ad labels.

## Immediate Post-Claude Review Gate — 2026-07-04

The latest code review found that the current implementation is not yet a
release-ready product even though many surfaces now exist. Agents must clear
these blockers before broad feature expansion or any "complete" status update:

- Backend quality gates are not green (re-verified 2026-07-08: `ruff` 120
  errors — 21 in `app`, rest cosmetic in `tests`; `mypy app` 45 errors / 15
  files; `pytest` 1936 passed / 6 failed). `SPONSORED_SURFACES` is now defined
  (that blocker is resolved). Remaining real blockers: onboarding imports a
  non-existent `async_session_factory` in `doc_verification.py` (runtime crash),
  nullable auth principal passed where non-null `UUID` is expected across the
  onboarding router, salary/experience presenter/service type gaps in
  `opportunities`, `Result.rowcount` misuse in moderation services, and one
  module-boundary violation (documents/platform_admin reaching into other
  modules' `domain.models`).
- Frontend typecheck/build pass, but build warnings remain in public jobs and
  notifications hook dependencies. Treat these as regression risks for heavily
  used surfaces.
- Auth/register must be email/password only. Name/profile fields belong to
  onboarding or profile/CV confirmation. Verification/reset emails must not
  assume `name` exists, and vi/en user-facing copy must be i18n-backed.
- Workflow builder must persist real canvas changes, use selectors for users,
  departments, stages, templates, prompts, and actions, expose validation/dry
  run/history, and avoid raw IDs as the operator-facing configuration model.
- CV Studio has a useful canvas start, but template versioning/assets,
  renderer/PDF/preview unification, browser QA, accessibility, and university
  template governance remain open.
- Product status must distinguish `implemented`, `API wired`,
  `browser verified`, `visual-design verified`, and `E2E verified`. Older
  historical "clean" status lines do not override the latest gate results.

When in doubt, run a blocker stabilization pass first and update
`docs/IMPLEMENTATION_STATUS.md` with exact commands and pass/fail evidence.

## Source Of Truth

Read only the docs needed for the task, in this order:

1. `docs/PRODUCT_REQUIREMENTS.md` — product, personas, modules, scope.
2. `docs/PRODUCT_REALITY_REBUILD_SPEC.md` — cross-system realism gate for practical workflows, backend/data/AI/frontend completeness, and anti-demo rules.
3. `docs/CV_STUDIO_SPEC.md` — CV upload, template builder, AI-assisted fill/rewrite, exports, snapshots.
4. `docs/CV_INGESTION_EXTRACTION_SPEC.md` — uploaded-CV preview, OCR/layout extraction, LLM fallback, review/import, and failure recovery.
5. `docs/BUSINESS_LOGIC.md` — deep business rules and edge cases.
6. `docs/PRODUCT_OPERATING_MODEL.md` — product-management operating model for AI credits/quota, persona entitlements, ads/events/workflows, and dashboard quality.
7. `docs/SECURITY_PRIVACY.md` — RBAC, PII, CV access, AI safety, ads compliance.
8. `docs/ARCHITECTURE.md` — module boundaries, data flow, infra, ADRs.
9. `docs/API_CONTRACTS.md` — endpoint, auth, error, pagination, event contracts.
10. `docs/DATA_MODEL.md` — canonical entities, tenancy, audit, soft delete, projections.
11. `docs/PARTNER_RBAC_ANALYTICS_SPEC.md` — partner-admin ownership, grantable recruiter capabilities, CV/access audit, and recruiting analytics read models.
12. `docs/DESIGN.md` — visual design and UI/UX source of truth.
13. `docs/UI_QUALITY_BAR.md` — frontend polish, responsiveness, accessibility, and browser QA gate.
14. `docs/SCREEN_SPECS.md` — screen-level UX for critical workflows.
15. `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md` — icon semantics, header quick actions, campaign banners, disclosure wording, visual realism.
16. `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md` — how to invoke `frontend-design`, plan visual direction, audit `globals.css`, and self-critique before coding.
17. `docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` — public discovery, recommendations, guest/session personalization, ad placements, and monetization UX.
18. `docs/SYSTEM_ACCEPTANCE_BAR.md` — cross-functional product/backend/frontend/AI/data/security completion gate.
19. `docs/AI_PRODUCT_SPEC.md` — AI feature matrix, permissions, evaluation, fallback.
20. `docs/ENVIRONMENT.md` — local/dev env names, secret policy, AI test-key policy.
21. `docs/LOCAL_DEV_STACK.md` — local-first stack, lightweight OCR/parser, no-Docker app runtime.
22. `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md` — notifications, email templates, preferences, device settings.
23. `docs/EDGE_CASES_FAILURE_MODES.md` — invalid inputs, partial failures, recovery, user-safe errors.
24. `docs/TEST_STRATEGY.md` — quality gates and test expectations.
25. `docs/AGENT_PARALLEL_EXECUTION_PLAN.md` — current multi-agent rebuild plan, workstream boundaries, and acceptance gates.
26. `docs/CLAUDE_MULTI_AGENT_TASKS.md` — copy-ready Claude CLI task commands for parallel execution.
27. `docs/BACKLOG.md`, `docs/ROADMAP.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/IMPLEMENTATION_STATUS.md` — priority, phases, current batch, verified status.

If docs conflict, stop and resolve by this precedence: product scope -> product operating model -> business rule -> security/privacy -> architecture -> API/data -> design -> implementation plan/status.

## Greenfield Naming Defaults

- Backend modules use `backend/app/modules/{domain}/`.
- Use `ai_assistant`, not `assistant`, for chat/session/tool execution.
- Use `ai_settings` for AI governance. Real provider/model registry identity and
  CRUD are platform-superadmin-only; ordinary university staff see masked
  aliases/status/budget controls only.
- Use module `organization` for shared org/RBAC internals; expose public API paths under `/api/v1/organizations`.
- Use module `opportunities` for jobs/events discovery and creation.
- Use module `recruitment` for applications, candidate pipeline, interviews, scorecards, offers.
- Use module `documents` for CV upload, CV Studio, exports, signed file access, and application CV snapshots.
- Use module `knowledge_base` for document upload, chunking, embedding, and RAG retrieval.
- Use module `messaging` for in-app institutional messages; never student-to-student.
- Use module `workflow` for visual workflow builder flows and executions.
- V1 payment default is manual/bank transfer adapter. VNPay/MoMo/ZaloPay gateways are later-phase unless explicitly requested.
- Local AI smoke tests should use low-cost/free provider aliases first. Real keys live only in `.env`, e.g. `OPENROUTER_API_KEY`; never write real keys into docs or tracked files.
- Local app runtime is not Docker-first. Scaffold direct localhost backend/frontend commands and keep OCR/AI/email dependencies lightweight by default.
- Every major workflow must handle invalid/empty/duplicate/permission/concurrency/async/AI-failure cases from `docs/EDGE_CASES_FAILURE_MODES.md`.

## Agent Routing

Use `docs/TASK_ROUTING.md` for exact routing.

- Main Claude session is the orchestrator.
- Subagents do focused work and report back to the main session.
- Subagents do not directly talk to each other by default.
- Agent Teams only apply when explicitly enabled with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

Project subagents:

- `product-owner-system-planner`: scope, priority, acceptance criteria.
- `system-architect`: ADRs, module boundaries, data/API shape.
- `backend-developer`: FastAPI, DB, migrations, services, workers.
- `frontend-developer`: Next.js UI, components, accessibility, i18n.
- `ai-engineer`: AI gateway, prompts, tools, eval, safety.
- `data-engineer`: events, projections, exports, reporting.
- `student-domain-agent`: student journey and UX review.
- `employer-domain-agent`: partner/recruiter journey and UX review.
- `university-domain-agent`: governance, moderation, university RBAC.
- `tester-qa`: test strategy, test code, release quality gates.

## Skills And Commands

Use project skills for repeatable workflows:

- `vinuni-feature`: end-to-end feature workflow.
- `vinuni-docs-audit`: docs, agents, rules, and routing consistency audit.
- `vinuni-ai-product`: AI feature/tool/eval/fallback design.
- `vinuni-security-review`: RBAC, privacy, AI leakage, and sponsored-content audit.
- `vinuni-ui-polish`: frontend polish, responsive review, accessibility, and browser QA.
- `vinuni-test-gate`: quality gate and test plan.
- `vinuni-status`: verified implementation status update.

Project slash commands in `.claude/commands/` are thin wrappers around these skills.

- `/tiny-patch`: fastest mode for 1-3 localized files; no broad docs, no subagents, cheapest check only.
- `/review-snapshot`: pause coding and audit current docs/code/UI/status before continuing.
- `/product-reality-audit`: audit practical product/business/AI/backend/frontend gaps before broad implementation.
- `/build-burst`: faster batch build with cheap checks per slice and full gates at checkpoint.
- `/overnight-burst-loop`: repeated burst/checkpoint cycles for long unattended work.
- `/autopilot-build`: long-running phase build loop with verification and status checkpoints.

## Required Local Rules

Read these rule files when relevant:

- Backend task: `.claude/rules/backend.md`
- Frontend/UI task: `.claude/rules/frontend.md`
- AI task: `.claude/rules/ai.md`
- Testing/review task: `.claude/rules/testing.md`
- Real-time/messaging/WebSocket task: `.claude/rules/realtime.md`

## Handoff Packet

Every non-trivial agent result should include:

- Goal.
- Source docs read.
- Decisions made.
- API/schema/data/event contract changes.
- Owned files or modules.
- Tests required or added.
- Risks and edge cases.
- Open questions.
- Next agent, if any.

## Execution Rules

- Domain agents produce specs/reviews only; they do not write application code.
- Implementation agents may write code and tests within their domain.
- AI prompts and tool behavior must be approved by `ai-engineer`.
- Architecture changes must go through `system-architect` and update architecture docs or ADR notes.
- Product scope changes must go through `product-owner-system-planner` and update PRD/backlog/roadmap.
- Backend and frontend may run in parallel only after API/data contract is stable.
- Do not create fake placeholder dashboards. Use real APIs, skeletons, empty states, permission states, or explicit TODO-disabled panels.
- UI surfaces must be persona-specific operating surfaces, not generic dashboards or marketing filler.
- AI usage accounting is product-critical. Any real provider call that can affect
  user value, partner value, cost, quota, billing, or university budget must pass
  through a usage-aware path with `UsageContext`, durable ledger/idempotency,
  budget/throttle checks, and persona-appropriate UX. Student/partner exhaustion
  may route to plan/credit upgrade; university staff exhaustion routes to admin
  limit/request workflows, not billing upsell.
- For broad or ambiguous work, apply `docs/PRODUCT_REALITY_REBUILD_SPEC.md`
  before coding. Agents must audit adjacent flows, data integrity, AI usefulness,
  failure modes, and frontend realism instead of implementing only the literal
  example the user mentioned.
- If a feature touches jobs, CVs, applications, partner operations, university
  operations, discovery, auth, notifications, or analytics, also check whether
  application snapshots, support/compliance paths, abuse/fraud controls, and
  read-model/projection contracts are required before calling it complete.
- Partner Admin has full organization control by default, but partner features
  must be modeled as grantable capabilities. Do not make analytics, CV access,
  billing, pipeline, AI actions, exports, or click/view metrics hardcoded to a
  role name; gate them through service-layer RBAC by user/role/department scope
  per `docs/PARTNER_RBAC_ANALYTICS_SPEC.md`.
- Visual direction is v10 "Monochrome Shell + Data-viz Content" (DESIGN.md
  §1.1.2). The SHELL (header/sidebar/nav) stays monochrome: full gray ramp for
  hierarchy (never flat #000/#fff), light + dark themes, ink as the only shell
  action color, subtle active pill. The CONTENT area (charts, KPI tiles, chips,
  status) uses the locked, colorblind-safe data-viz palette (indigo/teal/amber/
  rose/sky/emerald/violet/orange + `-soft` tints; success=emerald, warn/
  sponsored=amber, danger=VinUni red, info/AI=sky/indigo) — the blue→gray remap
  is reverted for CONTENT ONLY. Exactly one restrained indigo→violet gradient
  hero tile per surface. Enforce the locked type scale (`.type-*`). Do not
  reintroduce blue/navy accent surfaces in the SHELL. Build on shadcn/ui
  (`@/components/ui`) + the v10 primitive kit (`@/components/kit`); icons are
  lucide-react only.
- Student CV workflows are CV-first: upload/template/raw-notes/AI/duplicate/job-fit
  flows must work without a mandatory education/experience profile form.
- CV Studio must be implemented as a visual document/canvas editor with a
  template marketplace, A4 preview, inline text editing, drag/drop blocks,
  photo replace/crop, style controls, autosave, versioning, and export preview.
  Long section/profile forms may exist only as secondary metadata or fallback
  tools; they must not become the primary CV authoring experience.
- Natural-language CV edits are AI write actions. They must produce a visible
  structured diff/patch against the CV canvas/content, require explicit student
  confirmation, create a version/audit trail on accept, and never silently edit
  or publish a CV.
- Uploaded-CV workflows are upload-and-name, backend-authoritative (owner
  decision 2026-07-05). The student uploads a PDF/image, confirms it is the right
  file, names the CV, and is returned to their CV library — done. The backend
  extracts and stores it; the student does NOT hand-review or edit extracted
  fields (a manual field-review form is considered wrong UX and was removed).
  Uploaded CVs are then viewed READ-ONLY (their original document); the visual
  builder/editor is reserved for TEMPLATE-created CVs only — an uploaded CV never
  opens the editor. Extraction output is STRUCTURED (one entry per job/degree with
  separate role/organization/timeframe/highlights fields — no bullet chars in the
  data; skills carry a 0-100 level) and stored for CV-JD matching. Extraction accuracy is therefore a backend
  responsibility and feeds CV-JD matching directly. The pipeline is a cost-tiered
  cascade (`docs/CV_INGESTION_EXTRACTION_SPEC.md`): native text (free) -> local
  OCR -> a cheap vision-LLM (Gemini-class) for images and styled/multi-column
  scanned PDFs. Sending DOWNSCALED document images to the vision model is
  explicitly permitted for the image/scanned path (owner-approved; it overrides
  the older "never send image bytes to an LLM" rule — the text-only LLM
  structuring tier still receives text only). Blank/not-CV/corrupt uploads must be
  rejected with a clear status and must never be fabricated into a CV.
- Logged-in student job detail surfaces must prioritize useful job intelligence:
  best CV to use, CV-JD fit score, evidence gaps, suggested CV improvements,
  learning gaps, deadline/application context, and competition intelligence when
  enough privacy-safe data exists. Guests must not see personalized fit or
  competition claims.
- Competition intelligence is a product signal, not a model confidence score or
  decorative badge. It must be based on real backend inputs such as seats/hiring
  target, application volume, applicant quality distribution, the student's
  fit percentile, deadline freshness, source mix, and CV strength; never expose
  other candidates' PII or raw internal scores.
- Partner and university workflow builders must be visual, versioned, audited
  flow editors with dry-run/testing, RBAC-gated activation, immutable active
  versions, and human confirmation for consequential AI/write nodes. Do not
  replace them with static forms or hardcoded pipelines.
- If a task is a docs/instruction review, do not edit application code. Capture
  required implementation work as contracts, acceptance criteria, routing, and
  backlog/status notes instead.
- Visual/Product Rescue must route through product, architecture, data, frontend,
  and QA review before implementation. `docs/DESIGN_EXAMPLE.png` is a structural
  reference for the public marketplace; VinUni brand docs still control colors,
  assets, and copy.
- Use `docs/SYSTEM_ACCEPTANCE_BAR.md` before marking a slice complete; backend green + frontend build is not enough.
- Challenge weak/risky user requests when they conflict with product, security, architecture, or data integrity.
- When a practical feature, edge case, setting, notification, admin control, or AI assist is missing, run Product Gap Review instead of silently ignoring it or expanding scope without review.
- Frontend feature status must distinguish `API wired`, `browser verified`, and `E2E verified`.

## Plugin Policy

- Always-on core: `frontend-design`, `feature-dev`, `code-review`, `security-guidance`, `pr-review-toolkit`, `commit-commands`, `pyright-lsp`, `typescript-lsp`, `context7`, `playwright`, `chrome-devtools-mcp`, `code-simplifier`, `claude-md-management`.
- For major UI redesigns, use `frontend-design` before coding and follow `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md`.
- Utility skills enabled: `superpowers`, `skill-creator`.
- Enable when relevant: `plugin-dev`, `agent-sdk-dev`, `hookify`.
- Enable after auth/setup: `github`, `aikido`, `redis-development`, external issue/deploy/monitoring integrations.
- Keep task-only by default: autonomous loop, hook-authoring, learning/explanatory output style, and broad desktop-control plugins.
- External plugins must be audited before install: source repo clear, manifest valid, no unneeded destructive hooks/MCP, no secrets required before use.

## Verification Expectations

- Backend: unit/integration tests, migration check, OpenAPI contract check, lint/type checks where configured.
- Frontend: TypeScript strict, lint/build, responsive and accessibility review.
- AI: adversarial prompts, provider leakage tests, tool confirmation tests, eval dataset notes.
- Security: RBAC at service layer, audit for writes, PII-safe logs, signed URLs/watermark, sponsored labels.

## What Not To Do

- Do not use pre-reset git history or deleted implementation as a reference. Build from docs and current files only.
- Do not claim implementation is complete just because docs describe it; only `docs/IMPLEMENTATION_STATUS.md` verified facts count.
- Do not expose AI provider names, model names, token counts, latency, prompts, internal confidence, or internal status codes to end users.
- Do not expose real AI provider/model names or concrete model ids to ordinary
  university staff either. Only platform superadmins may view or manage the real
  provider/model registry, and only inside superadmin AI operations/settings
  surfaces. API keys and base URLs are never returned by any API.
- Do not auto-execute AI write actions without explicit user confirmation.
- Do not hardcode university staff roles.
- Do not remove `Được tài trợ`, `Quảng cáo`, or sponsored disclosure labels.
- Public discovery, personalized recommendations, and advertising placements must separate organic, recommended, sponsored, and university-curated inventory.
- Product interactions must use real-world semantics: job favorite uses a heart,
  quick actions (saved jobs, notifications, messages, and AI where available)
  live in the header for the public + student marketplace surfaces — with
  feedback/help in the account (avatar) menu — instead of a bottom-right floating
  action rail (owner decision 2026-07-07; the rail was removed). Campaign banners
  have approved or VinUni-curated creative assets, and paid disclosure is truthful
  without making university-curated partner content feel like low-trust ad tech.
