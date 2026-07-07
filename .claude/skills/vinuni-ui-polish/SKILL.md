---
name: vinuni-ui-polish
description: Use for frontend visual polish, responsive review, accessibility checks, browser QA, and UI release readiness.
---

# VinUni UI Polish Workflow

Use this skill when building or reviewing UI, dashboards, CV Studio, application flows, partner workflows, admin screens, public pages, or mobile responsiveness.

## Must Read

- `CLAUDE.md`
- `.claude/rules/frontend.md`
- `docs/FRONTEND_DESIGN_PLUGIN_USAGE.md`
- `docs/DESIGN.md`
- `docs/UI_QUALITY_BAR.md`
- `docs/SCREEN_SPECS.md`
- `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`
- `docs/CV_INGESTION_EXTRACTION_SPEC.md` when reviewing CV upload/import or CV
  Studio.
- Relevant product/business/API/security docs for the touched workflow.
- `docs/DESIGN_EXAMPLE.png` when reviewing or rebuilding the public marketplace
  homepage/header. Treat it as structural reference only; VinUni brand tokens
  still win for color and typography.

## Review Steps

1. Identify the user workflow and persona.
2. Check that the screen uses a real product surface, not placeholder or decorative filler.
   If the screen looks like a demo/card grid despite compiling, switch into
   Frontend Realism Rescue: compare against `docs/UI_QUALITY_BAR.md §4.1`, then
   redesign the composition before adding more feature breadth.
   For a major redesign, `frontend-design` must run first and produce the
   subject/audience/job, token system, layout concept, signature element,
   motion plan, self-critique, and `globals.css` theme audit. This skill then
   verifies the implementation against that plan.
3. For public pages, verify that jobs/events/companies/search and sponsored
   inventory are real discovery surfaces, not generic marketing blocks.
   For the homepage, compare the layout against `docs/DESIGN_EXAMPLE.png`:
   recruiting nav, company discovery/mega-menu affordance, split hero with real
   media, overlay search, metric strip, job list, employer/event/sponsored right
   rail, and trust rail.
   Verify job favorite uses a heart, campaign/banner content has real creative
   requirements, paid vs curated/strategic labels are truthful, and public copy
   does not make every promoted item feel like blunt ad inventory.
   Also verify marketplace maturity: banner/carousel or curated campaign
   surface, right-rail merchandising, saved jobs, opportunity invitations,
   feedback/help, and AI assistant affordances. If the screenshot looks like a
   static navy hero plus white cards, it fails even when typecheck/build pass.
4. For student pages, verify CV-first readiness, active CV quota, next action,
   applications, interviews/offers, recommendations, AI review actions, and
   settings nudges. Student profile forms are secondary settings/confirmed-facts
   surfaces, not the primary CV onboarding path.
   Verify the signed-in student shell inherits the public marketplace top nav
   with student-specific items, not the partner/university ops sidebar by default.
   For CV upload, verify preview-first flow: original document preview, confirm
   file, name the CV, backend processing states, landing on the resulting draft,
   template action, quota handling, and recovery for blank/not-CV/low-quality/
   password/corrupt/duplicate. (Updated 2026-07-05: upload-and-name; no manual
   field-review/side-by-side step — backend-authoritative extraction.)
5. For partner pages, verify recruiting queues, candidate pipeline, job health,
   team/RBAC, quota/package, ads/events, and recent activity.
6. For university pages, verify moderation queues, SLA risk, governance,
   outcomes, AI/cost/admin health, templates, audit, and security states.
7. Verify loading, empty, error, permission, success, and disabled states.
8. Check mobile and desktop layouts at 375px, 768px, 1024px, and 1440px.
9. Inspect keyboard/focus behavior, modal/drawer behavior, labels, and contrast.
10. Confirm API write payloads match backend contracts.
11. Run frontend gates and browser/Playwright QA when available.

## Hard Rules

- No fake stats, fake dashboards, or "implemented later" panels marked complete.
- No random icon semantics: job favorite is heart; messages, notifications,
  AI assistant, featured, sponsored, and curated states use distinct icons/copy.
- Public/student surfaces put quick actions (saved jobs, notifications,
  messages, and AI where available) in the TOP HEADER, with feedback/help in the
  account (avatar) menu — not a bottom-right floating rail (removed, owner
  decision 2026-07-07). Job favorite uses a heart. Desktop header actions need
  visible hover/focus labels; AI may use restrained motion/glow and must respect
  `prefers-reduced-motion`.
- Public gateway is not complete unless it exposes public jobs, events,
  companies, search, login-gated actions, and sponsored/ad disclosure.
- Public gateway is not visually complete unless it also has real
  merchandising energy: campaign/banner/carousel/spotlight modules, local
  VinUni media assets, company logos where available, and dense scan-friendly
  job inventory.
- Public marketplace/header redesign is not complete until screenshot/browser
  evidence exists at 375px, 768px, 1024px, and 1440px and status distinguishes
  functional verification from visual-design verification.
- Persona dashboards are not complete unless they include the persona's real
  queue, next action, risk/alert state, and deep links into the workflow.
- No `alert()` or `confirm()` in product workflows.
- No clipped text, overlapping UI, layout-shifting hover states, or unreachable mobile navigation.
- CV Studio must support CV library/template marketplace, upload/import, active
  CV quota, editor + preview + AI diff review, and job-fit recommendation before
  it is considered complete.
- CV Studio must visually feel like a serious document builder/template
  marketplace: template/library shelf, editor/canvas, A4 preview, AI diff drawer,
  fit rail, export controls, and version history. A list of cards plus a simple
  form is functional-only, not visual/product complete.
- Uploaded-CV flow is not complete unless the user can preview the original,
  confirm the file, name the CV, land on the resulting draft, and recover from
  failure states without seeing parser/AI internals. (Updated 2026-07-05:
  uploaded-CV flow is upload-and-name; there is NO manual field-review step —
  backend-authoritative extraction produces the draft directly.)
- Use Plus Jakarta Sans as the app UI typeface. Montserrat is legacy/asset-only
  unless a brand image already contains it.
- Do not accept `globals.css` token changes unless light, dark, and system theme
  semantics are all considered. VinUni colors are anchors; the palette may add
  modern neutrals and restrained accents when needed for hierarchy and beauty.
- Use status labels: `API wired`, `browser verified`, `E2E verified`; do not collapse them into a single ✅.

## Output

Return findings by severity, per-persona score, screenshots/browser checks
performed, commands run, release-gate decision, and exact follow-up fixes.
