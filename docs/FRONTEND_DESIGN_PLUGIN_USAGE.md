# Frontend Design Plugin Usage

> How to use the official `frontend-design` skill for VinUni UI work.

`frontend-design` is not a visual QA checklist. It is the upstream design-lead
step that must happen before major UI code changes. It should create a
distinctive design direction, then critique that direction before implementation.

Use it together with:

- `docs/DESIGN.md`
- `docs/UI_QUALITY_BAR.md`
- `docs/SCREEN_SPECS.md`
- `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`
- `.claude/skills/vinuni-ui-polish/SKILL.md`

## When It Is Required

Invoke `frontend-design` before coding when:

- rebuilding the public marketplace, homepage, jobs board, company profile, or
  student dashboard;
- changing `frontend/src/app/globals.css`, theme tokens, typography, radii,
  shadows, or light/dark/system theme behavior;
- a screenshot feels generic, flat, dated, demo-like, one-note blue/grey, or
  unlike a real recruiting marketplace;
- adding campaign/banner, floating action, AI assistant, CV Studio, dashboard, or
  marketplace surfaces that need strong visual direction.

Do not use it as a late "make it prettier" pass after code is already written.
Use it before implementation.

## Required Frontend-Design Output Contract

Before writing app code, Claude must produce or keep internally and follow this
design plan:

1. **Subject, audience, single job**
   - Subject: VinUni Career Platform as a university-backed recruiting
     marketplace and career operating system.
   - Audience: public guests, VinUni students, partner recruiters, university
     career-center staff.
   - Current screen job: state the one job for the route being redesigned.

2. **Screenshot diagnosis**
   - What currently feels generic, weak, confusing, visually stale, or
     commercially unrealistic?
   - Which part fails against `docs/DESIGN_EXAMPLE.png` and
     `docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`?

3. **Compact token system**
   - 4-6 named hex colors, not every VinUni color.
   - VinUni blue/red are brand anchors; they do not have to dominate every
     surface.
   - Include modern neutrals, a trusted blue action scale, a restrained red CTA,
     a teal/cyan AI/success accent, and a warm amber disclosure/status accent.
   - Define light, dark, and system-theme semantics, not only raw colors.

4. **Typography roles**
   - Body/UI: Plus Jakarta Sans unless a route-specific design plan justifies a
     restrained display face.
   - Data/caption/utility role: define weight/size/letter spacing.
   - Do not use typography as a default template; use it to create hierarchy.

5. **Layout concept**
   - One-sentence concept plus 1-2 ASCII wireframes for desktop/mobile.
   - Structure must encode real marketplace information: search, inventory,
     campaigns, trust, next actions, saved/invitations/messages/AI.

6. **Signature element**
   - Define one memorable VinUni-specific element for the page.
   - Examples: institutional campaign ribbon, campus/career-day editorial
     carousel, AI pulse launcher, employer trust rail, or CV-fit decision rail.
   - Spend boldness in one place; keep the rest disciplined.

7. **Motion plan**
   - Where motion helps the product: AI launcher pulse, carousel transitions,
     hover affordances, loading skeletons, or panel enter.
   - Must respect `prefers-reduced-motion`.

8. **Self-critique before build**
   - Identify anything that looks like generic AI output.
   - Revise palette/layout/copy before coding if it could fit any SaaS product.

9. **Implementation plan**
   - Routes/components to change.
   - Token changes in `globals.css`.
   - Risks: contrast, responsive overflow, data availability, i18n, reduced
     motion, accessibility, and test/browser gates.

10. **Post-build critique**
    - Compare screenshots at 375/768/1024/1440 against the design plan.
    - Record whether the result is `functional-only`, `visual-design verified`,
      or `E2E verified`.

## Globals.css Theme Audit

Before changing global tokens, audit:

- `:root`, `[data-theme="dark"]`, and system theme behavior;
- semantic tokens: background, surface, text, border, action, success, warning,
  error, info, focus, shadow, motion;
- whether the UI is becoming too navy/grey, too low-contrast, too red-heavy, or
  too muted;
- whether paid/curated/strategic/success/AI states are visually distinct;
- whether dark mode feels intentionally designed, not a direct inversion;
- whether all major colors meet WCAG contrast for text and controls.

The palette should feel like a modern institutional recruiting product:

- **Deep institutional navy** for trust and selected hero/ops surfaces.
- **Smart VinUni blue** for primary actions and links.
- **Teal/cyan** for AI, verified, success, and optimistic guidance.
- **Restrained VinUni red** for important CTA/accent, not broad backgrounds.
- **Warm amber** for disclosure, warning, sponsored, or time-sensitive status.
- **Clean neutrals** for most surfaces so content, logos, and banners can breathe.

## How To Prompt Claude Code

Use wording like:

```text
Use the official frontend-design skill first. Do not write app code until you
produce a design plan with subject/audience/job, screenshot diagnosis, 4-6 color
tokens, typography roles, layout concept, signature element, motion plan,
self-critique, globals.css theme audit, and implementation plan. Then build from
that plan exactly, run browser screenshots, critique again, and revise until the
UI is visual-design verified.
```

## Failure Signals

Reject the output and rerun `frontend-design` when:

- the plan starts from component names instead of product meaning;
- the palette simply uses all VinUni colors everywhere;
- the design is still one-note navy/grey or generic white cards;
- the "signature element" is just a gradient or bigger hero text;
- screenshots show no banner/carousel/rail/floating-action improvement;
- `globals.css` changes do not cover light/dark/system semantics;
- hover/focus labels, reduced motion, and mobile behavior are missing.
