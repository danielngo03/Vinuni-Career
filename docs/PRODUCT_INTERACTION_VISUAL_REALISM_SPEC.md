# Product Interaction And Visual Realism Spec

> Source of truth for interaction polish, icon semantics, floating actions,
> campaign/banner surfaces, disclosure language, and "real recruiting platform"
> visual acceptance.

## 1. Product Principle

The platform must feel like a serious university recruiting marketplace and
career operating system, not a demo SaaS dashboard.

Green tests and working APIs are not enough. A user should immediately
understand:

- what is organic, recommended, university-curated, partner spotlight, or paid;
- what action they can take now;
- where saved jobs, messages, notifications, and AI help live;
- why a banner or spotlight appears without feeling that the university is
  "selling" trust cheaply.

## 2. Icon Semantics

Use consistent Phosphor icons. Avoid random icon choices.

Required mappings:

- Save/favorite a job: `Heart` / `HeartStraight`, not bookmark/star.
- Saved collection/library: bookmark is acceptable only for a saved-list entry,
  not the job favorite action itself.
- Featured by VinUni: `SealCheck`, `Certificate`, or curated badge, not a star
  unless the product copy says "featured".
- Paid/partner campaign: `Megaphone` only in admin/partner controls. On public
  cards, use soft label/chip rather than loud ad icon unless required.
- AI assistant: VinUni-branded assistant entry with VinUni mark + small sparkle
  or robot only in admin/technical AI settings.
- Messaging: chat/envelope icon, not notification bell.
- Notifications: bell icon.

Job cards and job detail must include a heart save action in the top-right
corner. Guests clicking it open login with preserved intent. Students get
optimistic save/unsave once the saved-jobs backend exists. Until then, show an
honest login/coming-soon state without fake saved data.

## 3. Floating Action Rail

Public and student surfaces should have a fixed, bottom-right quick-action rail
that remains visible without covering content.

Desktop order:

1. Saved jobs / shortlist (`Heart`)
2. Career opportunity invitations (`EnvelopeSimple` or `Briefcase`) when the
   product has invitation/outreach inventory
3. Messages (`ChatCircleText`) for authenticated users
4. Feedback / help (`ChatCenteredDots` or `Question`) for public product
   feedback and support
5. VinUni AI career assistant (`VinUni mark + sparkle`) when the assistant is
   implemented or honest-disabled

Mobile:

- Use one compact floating launcher above the safe-area/bottom nav.
- Expands into the same actions.
- Must not overlap cookie/privacy notes, forms, sticky apply bars, or chat
  composer.

Rules:

- The rail is a navigation affordance, not a decoration.
- Hide or collapse actions that are not available for the persona.
- Never duplicate an action so aggressively that header and floating controls
  compete visually.
- Keyboard and screen-reader labels are required.
- Desktop buttons must expose a hover/focus label, not only `title`.
- The rail should use strong VinUni blue/teal action treatment, not inactive
  grey-outline buttons. The AI entry may use a restrained pulse/glow/ring to
  attract attention, but must respect `prefers-reduced-motion`.
- Honest-disabled is allowed only when the backend contract is missing. If an
  action is strategically important but blocked, the disabled label must explain
  "coming soon" without looking broken.

## 4. Campaign And Banner System

The public marketplace needs polished campaign placements. These are not just
"ads" in tone. Most are university-reviewed partner/community content.

Inventory classes:

- `organic`: normal jobs/events/companies.
- `recommended`: personalized by search/session/profile/CV signals.
- `university_curated`: selected by VinUni Career Center.
- `strategic_partner`: approved partner spotlight or employer brand placement.
- `paid_sponsored`: paid campaign/placement that requires disclosure.
- `featured`: editorial or package-based prominence; must explain source.

Public labels should be truthful but polished:

- Paid: "Đối tác tài trợ" / "Partner-sponsored".
- University curated: "VinUni tuyển chọn" / "Curated by VinUni".
- Strategic partner: "Đối tác chiến lược" / "Strategic partner".
- Featured: "Nổi bật" / "Featured".

Avoid blunt wording such as "Cơ hội được tài trợ" everywhere. Keep compliance
visible, but do not make the marketplace feel like a pay-to-win billboard.

## 5. Banner Creative Requirements

Partner/university campaign creatives must be uploaded, validated, and approved.
Do not rely only on text job cards for campaign surfaces.

Required creative slots:

| Slot | Desktop asset | Mobile asset | Use |
|---|---:|---:|---|
| Homepage hero campaign | 1440x360 or 4:1 | 720x720 or 1:1 | top campaign carousel |
| Right rail banner | 640x800 or 4:5 | 720x720 or 1:1 | homepage/job detail rail |
| Inline card banner | 1200x630 or 1.91:1 | 720x900 or 4:5 | between job/event rails |
| Event/career-day banner | 1440x480 or 3:1 | 720x900 or 4:5 | events/career explore |
| Email/newsletter banner | 1200x400 or 3:1 | n/a | later email campaigns |

Each creative needs:

- alt text in vi/en or localized title fallback;
- focal point for responsive crop;
- safe area for logos/text;
- file size limit and image type allowlist;
- moderation status;
- start/end window;
- click target;
- disclosure class;
- analytics source surface.

If no partner creative exists, use a VinUni-curated fallback asset from
`frontend/public` and label it as university content, not paid inventory.

## 6. Campaign Workflow

Partner flow:

1. choose target: job, event, company profile, or approved campaign slot;
2. upload required creative sizes or use a university-approved template;
3. preview exact desktop/mobile placements;
4. submit for university approval;
5. university reviews creative, copy, target, disclosure, payment/package;
6. approved campaigns appear in eligible slots;
7. partner sees impressions/clicks/apply-start/register-start.

University flow:

- approve/reject/pause campaign;
- edit label class only within compliance rules;
- upload or replace university-curated banners;
- inspect missing/broken creative assets;
- see spend/performance/policy complaints.

## 7. Layout And Visual Bar

Public marketplace:

- first viewport: marketplace nav, search hero, public inventory, campaign or
  curated right rail, metric strip, trust modules;
- job cards use heart save, company logo, deadline, location, skills, and clear
  apply intent;
- banner/carousel must feel editorial and institutional, not noisy ads.
- homepage must include at least one strong visual merchandising surface when
  assets exist: campaign carousel, VinUni-curated career-day banner, strategic
  partner banner, or employer spotlight with real logo/media. A large empty navy
  block plus white metric cards is not sufficient.
- hero/search must feel like a recruiting marketplace: search should be the
  dominant task, with visual energy from media, campaign modules, logo rails, or
  curated editorial surfaces. It should not look like a static landing page.
- public job boards should balance card and dense-list views. For real
  recruitment browsing, users need fast scanning: salary/location/deadline/fit,
  company logo, source label, save heart, and clear apply intent.

Student:

- inherits marketplace top nav;
- has floating quick actions;
- dashboards have wide operating surfaces, not a cramped `max-w-5xl` generic
  card grid when the workflow is data-heavy;
- recommended jobs show reason + recommended CV + fit score where available.

Partner:

- advertising/campaign surface shows creative preview, placement preview, asset
  requirements, status, moderation notes, and analytics.

University:

- campaign moderation queue includes creative preview, disclosure class, target,
  payment state, risk flags, and approve/reject/pause actions.

## 8. Verification Gate

Before claiming visual/product complete:

- screenshot/browser pass at 375, 768, 1024, 1440;
- inspect public homepage, jobs board/detail, student dashboard, CV Studio,
  partner advertising, university advertising moderation;
- verify heart save affordance and login-gated intent;
- verify floating action rail does not overlap sticky bars or footer;
- verify campaign labels are truthful and polished;
- verify paid disclosure is non-removable only for paid placements;
- verify university-curated/strategic partner content is not mislabeled as paid;
- verify no raw "ad tech" wording leaks to end users.
- reviewer must compare the screenshot against `docs/DESIGN_EXAMPLE.png` and
  at least one real recruiting-marketplace reference pattern: saved jobs,
  opportunity invitations, support/feedback, banner/spotlight merchandising,
  recommendation rails, and dense scan-friendly job inventory. Do not copy a
  competitor brand; copy the product maturity.

## 9. Product-Reality Failure Signals

A screenshot fails this spec even if build/tests pass when:

- first viewport has no meaningful banner/carousel/right-rail campaign surface;
- most of the screen is blank navy, white cards, or generic metrics;
- floating actions are grey, unlabeled, hidden, or missing saved jobs,
  invitations, feedback/help, and AI affordances where those products exist;
- AI assistant is present but visually dead; it should feel intentionally
  available or intentionally coming soon;
- public labels repeatedly say blunt "sponsored/ad" wording for curated or
  strategic-partner content;
- job cards look like generic SaaS tiles rather than recruitment inventory;
- company logos/media are absent when data/assets exist;
- a module is technically correct but does not teach the user what to do next.
